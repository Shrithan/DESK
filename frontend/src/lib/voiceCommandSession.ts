import { startMicCapture } from "./micCapture";
import type { MicCaptureHandle } from "./micCapture";

export type VoiceStatus = "idle" | "listening" | "processing" | "error";

export interface VoiceCommandHandlers {
  onTranscript: (text: string, isFinal: boolean) => void;
  onError: (message: string) => void;
  onStatus: (status: VoiceStatus) => void;
}

interface SttMessage {
  type: "transcript" | "flush_done" | "done" | "error";
  text?: string;
  is_final?: boolean;
  message?: string;
}

const PROCESSING_TIMEOUT_MS = 6000;

/** One push-to-talk session: mic -> relay (/stt) -> Cartesia -> transcript back. */
export class VoiceCommandSession {
  private ws: WebSocket | null = null;
  private mic: MicCaptureHandle | null = null;
  private url: string;
  private handlers: VoiceCommandHandlers;
  // Set when stop() is called before the socket has finished connecting, so
  // the open handler can send 'finalize' as soon as it's actually possible
  // to — otherwise a fast press-and-release races the handshake and the
  // session gets stuck in "processing" forever with nothing left to send it.
  private finalizePending = false;
  private processingTimeout: ReturnType<typeof setTimeout> | null = null;

  constructor(url: string, handlers: VoiceCommandHandlers) {
    this.url = url;
    this.handlers = handlers;
  }

  private clearProcessingTimeout() {
    if (this.processingTimeout) {
      clearTimeout(this.processingTimeout);
      this.processingTimeout = null;
    }
  }

  private finishProcessing(status: "idle" | "error", error?: string) {
    this.clearProcessingTimeout();
    if (error) this.handlers.onError(error);
    this.handlers.onStatus(status);
  }

  async start(): Promise<void> {
    this.handlers.onStatus("listening");

    try {
      this.ws = new WebSocket(this.url);
      this.ws.binaryType = "arraybuffer";

      this.ws.onopen = () => {
        if (this.finalizePending) {
          this.finalizePending = false;
          this.ws?.send("finalize");
        }
      };

      this.ws.onmessage = (event) => {
        let msg: SttMessage;
        try {
          msg = JSON.parse(event.data as string);
        } catch {
          return;
        }
        if (msg.type === "transcript" && msg.text) {
          this.handlers.onTranscript(msg.text.trim(), Boolean(msg.is_final));
        } else if (msg.type === "flush_done") {
          this.ws?.send("close");
        } else if (msg.type === "done") {
          this.finishProcessing("idle");
          this.ws?.close();
        } else if (msg.type === "error") {
          this.finishProcessing("idle", msg.message ?? "STT error");
        }
      };

      this.ws.onerror = () => {
        this.finishProcessing("idle", "STT relay unreachable (is npm run proxy:cartesia running?)");
      };

      await new Promise<void>((resolve, reject) => {
        if (!this.ws) return reject(new Error("no socket"));
        this.ws.addEventListener("open", () => resolve(), { once: true });
      });

      this.mic = await startMicCapture((chunk) => {
        if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(chunk);
      });
    } catch (err) {
      this.handlers.onError(err instanceof Error ? err.message : "failed to start voice capture");
      this.handlers.onStatus("idle");
    }
  }

  /** Stop capturing and ask Cartesia for the final transcript of buffered audio. */
  stop(): void {
    this.mic?.stop();
    this.mic = null;
    this.handlers.onStatus("processing");

    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send("finalize");
    } else if (this.ws?.readyState === WebSocket.CONNECTING) {
      this.finalizePending = true;
    } else {
      this.finishProcessing("idle", "voice session closed before it could finish");
      return;
    }

    // Belt-and-suspenders: never leave the UI stuck on "Transcribing..."
    // even if the relay/Cartesia never responds for some unforeseen reason.
    this.processingTimeout = setTimeout(() => {
      this.finishProcessing("idle", "No response from Cartesia — try again");
      this.ws?.close();
    }, PROCESSING_TIMEOUT_MS);
  }
}
