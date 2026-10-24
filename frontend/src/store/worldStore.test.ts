import { describe, expect, it } from "vitest";
import { useWorldStore } from "./worldStore";
import { startMockWorld } from "../lib/mockWorld";
import type { WorldState } from "../lib/contract";

describe("worldStore.applyWorldState", () => {
  it("stores a Y-up render position transformed from the Z-up world frame", () => {
    const state: WorldState = {
      type: "world_state",
      timestamp_ms: Date.now(),
      session_id: "s1",
      objects: [
        {
          id: "obj_1",
          position_m: { x: 0.1, y: 0.2, z: 0.3 },
          tracking_state: "tracked",
          confidence: 0.9,
          source_cameras: ["cam_1"],
        },
      ],
    };

    useWorldStore.getState().applyWorldState(state, 12);
    const obj = useWorldStore.getState().objects["obj_1"];
    expect(obj.nextPos).toEqual([0.1, 0.3, -0.2]);
    expect(obj.trackingState).toBe("tracked");
    expect(useWorldStore.getState().latencyMs).toBe(12);
  });
});

describe("mock world + store integration smoke test", () => {
  it("produces moving tracked objects that reach the store within a few ticks", async () => {
    useWorldStore.setState({ objects: {} });

    const stop = startMockWorld((state) => useWorldStore.getState().applyWorldState(state, 0), "smoke", 30);

    await new Promise((resolve) => setTimeout(resolve, 150));
    stop();

    const objects = useWorldStore.getState().objects;
    expect(Object.keys(objects).sort()).toEqual(["obj_1", "obj_2"]);
    expect(objects.obj_1.trail.length).toBeGreaterThan(1);
  });
});
