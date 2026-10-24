import { describe, expect, it } from "vitest";
import { GestureDetector } from "./gestureDetector";

describe("GestureDetector", () => {
  it("fires nothing on the first sample (no velocity yet)", () => {
    const d = new GestureDetector();
    expect(d.feed(0, 0, 0)).toBeNull();
  });

  it("ignores slow jitter below the velocity threshold", () => {
    const d = new GestureDetector({ velocityThreshold: 0.5, cooldownMs: 450 });
    d.feed(0, 0, 0);
    // 0.01m over 100ms = 0.1 m/s, well under threshold
    expect(d.feed(0.01, 0, 100)).toBeNull();
  });

  it("fires 'right' on a fast rightward (+x) move", () => {
    const d = new GestureDetector({ velocityThreshold: 0.5, cooldownMs: 450 });
    d.feed(0, 0, 0);
    // 0.2m over 100ms = 2 m/s
    expect(d.feed(0.2, 0, 100)).toBe("right");
  });

  it("fires 'left' on a fast leftward (-x) move", () => {
    const d = new GestureDetector({ velocityThreshold: 0.5, cooldownMs: 450 });
    d.feed(0, 0, 0);
    expect(d.feed(-0.2, 0, 100)).toBe("left");
  });

  it("fires 'jump' on a fast upward (+z) move", () => {
    const d = new GestureDetector({ velocityThreshold: 0.5, cooldownMs: 450 });
    d.feed(0, 0, 0);
    expect(d.feed(0, 0.2, 100)).toBe("jump");
  });

  it("fires 'duck' on a fast downward (-z) move", () => {
    const d = new GestureDetector({ velocityThreshold: 0.5, cooldownMs: 450 });
    d.feed(0, 0, 0);
    expect(d.feed(0, -0.2, 100)).toBe("duck");
  });

  it("prioritizes height over lane when both exceed threshold", () => {
    const d = new GestureDetector({ velocityThreshold: 0.5, cooldownMs: 450 });
    d.feed(0, 0, 0);
    expect(d.feed(0.2, 0.2, 100)).toBe("jump");
  });

  it("respects the per-gesture cooldown", () => {
    const d = new GestureDetector({ velocityThreshold: 0.5, cooldownMs: 450 });
    d.feed(0, 0, 0);
    expect(d.feed(0.2, 0, 100)).toBe("right");
    // Another fast rightward move immediately after — still in cooldown.
    expect(d.feed(0.4, 0, 150)).toBeNull();
    // Past the cooldown window, with velocity still above threshold, it fires again.
    expect(d.feed(0.8, 0, 600)).toBe("right");
  });

  it("does not fire on a non-positive time delta", () => {
    const d = new GestureDetector();
    d.feed(0, 0, 100);
    expect(d.feed(0.2, 0, 100)).toBeNull();
    expect(d.feed(0.2, 0, 50)).toBeNull();
  });
});
