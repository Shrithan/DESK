import { parseWorldState } from "./contract";
import type { WorldState } from "./contract";

export type ConnectionStatus = "connecting" | "connected" | "disconnected" | "error";

export interface WorldSocketHandlers {
  onState: (state: WorldState, latencyMs: number) => void;
  onStatus: (status: ConnectionStatus) => void;
}

const RECONNECT_DELAY_MS = 1500;

/** Connects to the backend /ws/world feed with basic auto-reconnect. Returns a disposer. */
export function connectWorldSocket(url: string, handlers: WorldSocketHandlers): () => void {
  let socket: WebSocket | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let disposed = false;

  const connect = () => {
    if (disposed) return;
    handlers.onStatus("connecting");
    socket = new WebSocket(url);

    socket.onopen = () => handlers.onStatus("connected");

    socket.onmessage = (event) => {
      let raw: unknown;
      try {
        raw = JSON.parse(event.data);
      } catch {
        return;
      }
      const state = parseWorldState(raw);
      if (!state) return;
      // Clock skew between client/server is unaccounted for; this is a rough
      // transport-latency indicator, not a calibrated measurement.
      const latencyMs = Date.now() - state.timestamp_ms;
      handlers.onState(state, latencyMs);
    };

    socket.onclose = () => {
      if (disposed) return;
      handlers.onStatus("disconnected");
      reconnectTimer = setTimeout(connect, RECONNECT_DELAY_MS);
    };

    socket.onerror = () => {
      handlers.onStatus("error");
    };
  };

  connect();

  return () => {
    disposed = true;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    socket?.close();
  };
}
