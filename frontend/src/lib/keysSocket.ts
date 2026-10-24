import { parseKeyState } from "./keyState";
import type { KeyState } from "./keyState";
import type { ConnectionStatus } from "./wsClient";

export interface KeysSocketHandlers {
  onState: (state: KeyState) => void;
  onStatus: (status: ConnectionStatus) => void;
}

const RECONNECT_DELAY_MS = 1500;

/** Connects to Agent 3's tilt_keys hub (/ws/keys) for held-key visualization only — never injects. */
export function connectKeysSocket(url: string, handlers: KeysSocketHandlers): () => void {
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
      const state = parseKeyState(raw);
      if (state) handlers.onState(state);
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
