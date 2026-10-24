/**
 * Mirrors shared/contracts/tilt.py KeyState (schema v1.0.0), broadcast by
 * Agent 3's backend/tilt_keys websocket hub on /ws/keys. This module owns
 * the real tilt->keys mapping and OS keystroke injection (via pynput) —
 * the frontend only visualizes the held-key state, it never injects.
 */
export interface KeyState {
  type: "key_state";
  schema_version: string;
  timestamp_ms: number;
  held: string[];
  enabled: boolean;
  mode: "calibrating" | "active" | "disabled";
}

const VALID_MODES = new Set(["calibrating", "active", "disabled"]);

export function parseKeyState(raw: unknown): KeyState | null {
  if (typeof raw !== "object" || raw === null) return null;
  const msg = raw as Record<string, unknown>;
  if (msg.type !== "key_state") return null;
  if (typeof msg.timestamp_ms !== "number") return null;
  if (!Array.isArray(msg.held) || !msg.held.every((k) => typeof k === "string")) return null;

  const mode = typeof msg.mode === "string" && VALID_MODES.has(msg.mode) ? msg.mode : "active";
  const enabled = typeof msg.enabled === "boolean" ? msg.enabled : true;
  const schemaVersion = typeof msg.schema_version === "string" ? msg.schema_version : "1.0.0";

  if (!schemaVersion.startsWith("1.")) return null;

  return {
    type: "key_state",
    schema_version: schemaVersion,
    timestamp_ms: msg.timestamp_ms,
    held: msg.held as string[],
    enabled,
    mode: mode as KeyState["mode"],
  };
}
