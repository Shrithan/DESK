import type { ConnectionStatus } from "../../lib/wsClient";
import type { KeyState } from "../../lib/keyState";

const KEY_LAYOUT: Array<{ key: string; label: string; col: number; row: number }> = [
  { key: "w", label: "W", col: 2, row: 1 },
  { key: "a", label: "A", col: 1, row: 2 },
  { key: "s", label: "S", col: 2, row: 2 },
  { key: "d", label: "D", col: 3, row: 2 },
];

const STATUS_COLOR: Record<ConnectionStatus, string> = {
  connected: "#4ade80",
  connecting: "#fbbf24",
  disconnected: "#8b98a5",
  error: "#f87171",
};

interface Props {
  connectionStatus: ConnectionStatus;
  keyState: KeyState | null;
}

export function HeldKeysPanel({ connectionStatus, keyState }: Props) {
  const held = new Set((keyState?.held ?? []).map((k) => k.toLowerCase()));

  return (
    <div className="hud-panel">
      <div className="hud-title">Held Keys (Agent 3: tilt-to-keys)</div>

      <div className="hud-row">
        <span>Connection</span>
        <span className="mono" style={{ color: STATUS_COLOR[connectionStatus] }}>
          {connectionStatus}
        </span>
      </div>

      {keyState && (
        <div className="hud-row">
          <span>Mode</span>
          <span className="mono">{keyState.mode}{keyState.enabled ? "" : " (disabled)"}</span>
        </div>
      )}

      <div className="keycap-grid">
        {KEY_LAYOUT.map(({ key, label, col, row }) => (
          <div
            key={key}
            className={`keycap ${held.has(key) ? "held" : ""}`}
            style={{ gridColumn: col, gridRow: row }}
          >
            {label}
          </div>
        ))}
      </div>

      {!keyState && <div className="hud-muted">Waiting for key_state — run Agent 3's tilt_keys backend on :8765</div>}
    </div>
  );
}
