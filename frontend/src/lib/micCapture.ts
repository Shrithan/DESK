/**
 * Captures mic audio and downsamples to the 16kHz mono PCM16LE frames
 * Cartesia's STT websocket expects. Uses an AudioWorklet so resampling
 * happens off the main thread.
 */
const WORKLET_SOURCE = `
class PcmDownsampler extends AudioWorkletProcessor {
  constructor() {
    super();
    this.targetRate = 16000;
    this.ratio = sampleRate / this.targetRate;
    this.carry = 0;
  }
  process(inputs) {
    const input = inputs[0]?.[0];
    if (!input || input.length === 0) return true;

    const outLength = Math.floor(input.length / this.ratio);
    if (outLength <= 0) return true;

    const out = new Int16Array(outLength);
    let pos = this.carry;
    for (let i = 0; i < outLength; i++) {
      const sample = input[Math.min(Math.floor(pos), input.length - 1)];
      out[i] = Math.max(-32768, Math.min(32767, Math.round(sample * 32767)));
      pos += this.ratio;
    }
    this.carry = pos - input.length;

    this.port.postMessage(out.buffer, [out.buffer]);
    return true;
  }
}
registerProcessor("pcm-downsampler", PcmDownsampler);
`;

export interface MicCaptureHandle {
  stop: () => void;
}

export async function startMicCapture(onChunk: (pcm16: ArrayBuffer) => void): Promise<MicCaptureHandle> {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1 } });
  const audioCtx = new AudioContext();

  const blob = new Blob([WORKLET_SOURCE], { type: "application/javascript" });
  const workletUrl = URL.createObjectURL(blob);
  await audioCtx.audioWorklet.addModule(workletUrl);
  URL.revokeObjectURL(workletUrl);

  const source = audioCtx.createMediaStreamSource(stream);
  const node = new AudioWorkletNode(audioCtx, "pcm-downsampler");
  node.port.onmessage = (event: MessageEvent<ArrayBuffer>) => onChunk(event.data);
  source.connect(node);

  return {
    stop: () => {
      node.port.onmessage = null;
      source.disconnect();
      node.disconnect();
      stream.getTracks().forEach((t) => t.stop());
      void audioCtx.close();
    },
  };
}
