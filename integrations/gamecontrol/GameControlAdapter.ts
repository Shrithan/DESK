export interface KeyPressResult {
  key: string;
  mocked: boolean;
}

/**
 * Sends a mapped gesture key to the local gamecontrol proxy (server.mjs),
 * which is the only thing that can actually touch the OS keyboard. Armed is
 * OFF by default — fire() is a no-op until the UI explicitly arms it, on top
 * of the proxy's own GAME_CONTROL_ALLOW_INJECT gate.
 */
export class GameControlAdapter {
  private armed = false;
  private proxyUrl: string;

  constructor(proxyUrl: string = import.meta.env.VITE_GAME_CONTROL_PROXY_URL ?? "http://localhost:8788/press") {
    this.proxyUrl = proxyUrl;
  }

  setArmed(armed: boolean) {
    this.armed = armed;
  }

  isArmed(): boolean {
    return this.armed;
  }

  async fire(key: string): Promise<KeyPressResult | null> {
    if (!this.armed) return null;

    try {
      const res = await fetch(this.proxyUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key }),
      });
      const data = (await res.json()) as { mocked?: boolean };
      return { key, mocked: data.mocked !== false };
    } catch (err) {
      console.warn("[GameControlAdapter] proxy unreachable, treating as mock:", err);
      return { key, mocked: true };
    }
  }
}
