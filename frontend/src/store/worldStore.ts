import { create } from "zustand";
import { worldToThree } from "../lib/coords";
import type { ConnectionStatus } from "../lib/wsClient";
import type { TrackingState, WorldState } from "../lib/contract";

const TRAIL_MAX_POINTS = 150;

export interface RenderObject {
  id: string;
  prevPos: [number, number, number];
  nextPos: [number, number, number];
  prevTimeMs: number;
  nextTimeMs: number;
  trackingState: TrackingState;
  confidence: number | null;
  sourceCameras: string[];
  trail: [number, number, number][];
  lastSeenMs: number;
}

export interface CameraHealth {
  id: string;
  connected: boolean;
  fps: number | null;
}

interface WorldStore {
  mode: "mock" | "live";
  connectionStatus: ConnectionStatus;
  sessionId: string;
  objects: Record<string, RenderObject>;
  cameras: CameraHealth[];
  latencyMs: number | null;
  lastWorldStateAtMs: number | null;
  showTrails: boolean;
  selectedObjectId: string | null;

  setMode: (mode: "mock" | "live") => void;
  setConnectionStatus: (status: ConnectionStatus) => void;
  setCameras: (cameras: CameraHealth[]) => void;
  applyWorldState: (state: WorldState, latencyMs: number | null) => void;
  toggleTrails: () => void;
  selectObject: (id: string | null) => void;
  markStaleObjects: (nowMs: number, staleAfterMs: number) => void;
}

export const useWorldStore = create<WorldStore>((set, get) => ({
  mode: "mock",
  connectionStatus: "disconnected",
  sessionId: "",
  objects: {},
  cameras: [],
  latencyMs: null,
  lastWorldStateAtMs: null,
  showTrails: true,
  selectedObjectId: null,

  setMode: (mode) => set({ mode }),
  setConnectionStatus: (status) => set({ connectionStatus: status }),
  setCameras: (cameras) => set({ cameras }),

  applyWorldState: (state, latencyMs) => {
    const now = performance.now();
    const existing = get().objects;
    const next: Record<string, RenderObject> = { ...existing };

    for (const obj of state.objects) {
      const pos = worldToThree(obj.position_m.x, obj.position_m.y, obj.position_m.z);
      const prior = existing[obj.id];
      const trail = prior ? [...prior.trail, pos] : [pos];
      if (trail.length > TRAIL_MAX_POINTS) trail.shift();

      next[obj.id] = {
        id: obj.id,
        prevPos: prior ? prior.nextPos : pos,
        nextPos: pos,
        prevTimeMs: prior ? prior.nextTimeMs : now,
        nextTimeMs: now,
        trackingState: obj.tracking_state,
        confidence: obj.confidence,
        sourceCameras: obj.source_cameras,
        trail,
        lastSeenMs: now,
      };
    }

    set({
      objects: next,
      sessionId: state.session_id,
      latencyMs,
      lastWorldStateAtMs: now,
    });
  },

  toggleTrails: () => set((s) => ({ showTrails: !s.showTrails })),
  selectObject: (id) => set({ selectedObjectId: id }),

  markStaleObjects: (nowMs, staleAfterMs) => {
    const objects = get().objects;
    let changed = false;
    const next: Record<string, RenderObject> = { ...objects };
    for (const [id, obj] of Object.entries(objects)) {
      if (obj.trackingState !== "lost" && nowMs - obj.lastSeenMs > staleAfterMs) {
        next[id] = { ...obj, trackingState: "lost" };
        changed = true;
      }
    }
    if (changed) set({ objects: next });
  },
}));
