export type NarrationEvent = "tracking_started" | "object_lost" | "object_recovered" | "calibration_complete";

const EVENT_TEXT: Record<NarrationEvent, string> = {
  tracking_started: "Tracking started.",
  object_lost: "Object lost.",
  object_recovered: "Object recovered.",
  calibration_complete: "Calibration complete.",
};

const DEBOUNCE_MS = 4000;

export class CartesiaAdapter {
  private muted = false;
  private lastFiredAt = new Map<NarrationEvent, number>();
  private onText: (text: string) => void;
  private proxyUrl: string;

  constructor(
    proxyUrl: string = import.meta.env.VITE_CARTESIA_PROXY_URL ?? "http://localhost:8787/speak",
    onText: (text: string) => void = () => {},
  ) {
    this.proxyUrl = proxyUrl;
    this.onText = onText;
  }

  setMuted(muted: boolean) {
    this.muted = muted;
  }

  /** Rate-limited per event key so continuous object motion never spams narration. */
  async announce(event: NarrationEvent) {
    const now = performance.now();
    const last = this.lastFiredAt.get(event) ?? -Infinity;
    if (now - last < DEBOUNCE_MS) return;
    this.lastFiredAt.set(event, now);

    const text = EVENT_TEXT[event];
    this.onText(text);
    if (this.muted) return;

    try {
      const res = await fetch(this.proxyUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      const contentType = res.headers.get("content-type") ?? "";
      if (contentType.includes("audio")) {
        const blob = await res.blob();
        const audio = new Audio(URL.createObjectURL(blob));
        void audio.play();
      }
      // JSON {mocked:true} response: text-only fallback already fired via onText above.
    } catch (err) {
      console.warn("[CartesiaAdapter] proxy unreachable, text-only fallback:", err);
    }
  }
}
