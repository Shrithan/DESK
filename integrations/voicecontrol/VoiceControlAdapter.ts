export interface KeyTransition {
  key: string;
  down: boolean;
}

/** Thin client for integrations/voicecontrol/server.mjs — sends held-key transitions, never injects itself. */
export class VoiceControlAdapter {
  private url: string;

  constructor(url: string = import.meta.env.VITE_VOICECONTROL_PROXY_URL ?? "http://localhost:8789/key-transition") {
    this.url = url;
  }

  async applyTransitions(transitions: KeyTransition[]): Promise<void> {
    for (const transition of transitions) {
      try {
        await fetch(this.url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(transition),
        });
      } catch (err) {
        console.warn("[VoiceControlAdapter] proxy unreachable:", err);
      }
    }
  }

  async releaseAll(): Promise<void> {
    const releaseUrl = this.url.replace(/\/key-transition$/, "/release-all");
    try {
      await fetch(releaseUrl, { method: "POST" });
    } catch (err) {
      console.warn("[VoiceControlAdapter] release-all failed:", err);
    }
  }
}
