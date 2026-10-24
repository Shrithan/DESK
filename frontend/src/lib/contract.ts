export type {
  TrackingState,
  Position3D,
  TrackedObject,
  WorldState,
  Pixel,
  SelectionCommand,
} from "../../../shared/contracts/types";

import type { WorldState } from "../../../shared/contracts/types";

/**
 * Minimal structural validation against shared/contracts/world-state.v1.schema.json.
 * Not a full JSON-schema validator — fast-fails on shape drift from the backend
 * so a malformed message never silently renders as a false "tracked" object.
 */
export function parseWorldState(raw: unknown): WorldState | null {
  if (typeof raw !== "object" || raw === null) return null;
  const msg = raw as Record<string, unknown>;
  if (msg.type !== "world_state") return null;
  if (typeof msg.timestamp_ms !== "number") return null;
  if (typeof msg.session_id !== "string") return null;
  if (!Array.isArray(msg.objects)) return null;

  for (const obj of msg.objects) {
    if (typeof obj !== "object" || obj === null) return null;
    const o = obj as Record<string, unknown>;
    if (typeof o.id !== "string") return null;
    const pos = o.position_m as Record<string, unknown> | undefined;
    if (!pos || typeof pos.x !== "number" || typeof pos.y !== "number" || typeof pos.z !== "number") {
      return null;
    }
    if (!["tracked", "predicted", "lost"].includes(o.tracking_state as string)) return null;
    if (o.confidence !== null && typeof o.confidence !== "number") return null;
    if (!Array.isArray(o.source_cameras)) return null;
  }

  return msg as unknown as WorldState;
}
