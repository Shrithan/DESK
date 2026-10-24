export type Gesture = "left" | "right" | "jump" | "duck";

export interface GestureThresholds {
  /** m/s a given axis must exceed to count as a deliberate move, not jitter. */
  velocityThreshold: number;
  /** Minimum ms between two gestures of the SAME type (per-axis debounce). */
  cooldownMs: number;
}

export const DEFAULT_GESTURE_THRESHOLDS: GestureThresholds = {
  velocityThreshold: 0.5,
  cooldownMs: 450,
};

/**
 * Turns a stream of (x, y, z) world positions into discrete left/right/jump/duck
 * gestures by watching per-axis velocity. Y (depth) is unused for now — Subway-
 * Surfers-style controls only need lane (X) and height (Z).
 */
export class GestureDetector {
  private lastX: number | null = null;
  private lastZ: number | null = null;
  private lastTimeMs: number | null = null;
  private lastFiredAt: Partial<Record<Gesture, number>> = {};
  private thresholds: GestureThresholds;

  constructor(thresholds: GestureThresholds = DEFAULT_GESTURE_THRESHOLDS) {
    this.thresholds = thresholds;
  }

  reset() {
    this.lastX = null;
    this.lastZ = null;
    this.lastTimeMs = null;
  }

  /** Feed the latest position; returns a gesture if one just triggered, else null. */
  feed(x: number, z: number, timeMs: number): Gesture | null {
    if (this.lastX === null || this.lastZ === null || this.lastTimeMs === null) {
      this.lastX = x;
      this.lastZ = z;
      this.lastTimeMs = timeMs;
      return null;
    }

    const dt = (timeMs - this.lastTimeMs) / 1000;
    if (dt <= 0) return null;

    const vx = (x - this.lastX) / dt;
    const vz = (z - this.lastZ) / dt;
    this.lastX = x;
    this.lastZ = z;
    this.lastTimeMs = timeMs;

    // Height changes take priority over lane changes when both exceed threshold
    // (a jump mid-swipe shouldn't get swallowed by a lane-change reading).
    const candidates: Array<{ gesture: Gesture; magnitude: number }> = [];
    if (Math.abs(vz) >= this.thresholds.velocityThreshold) {
      candidates.push({ gesture: vz > 0 ? "jump" : "duck", magnitude: Math.abs(vz) });
    }
    if (Math.abs(vx) >= this.thresholds.velocityThreshold) {
      candidates.push({ gesture: vx > 0 ? "right" : "left", magnitude: Math.abs(vx) });
    }
    if (candidates.length === 0) return null;

    candidates.sort((a, b) => b.magnitude - a.magnitude);
    const best = candidates[0].gesture;

    const last = this.lastFiredAt[best] ?? -Infinity;
    if (timeMs - last < this.thresholds.cooldownMs) return null;

    this.lastFiredAt[best] = timeMs;
    return best;
  }
}

export const GESTURE_KEY_MAP: Record<Gesture, string> = {
  left: "ArrowLeft",
  right: "ArrowRight",
  jump: "ArrowUp",
  duck: "ArrowDown",
};
