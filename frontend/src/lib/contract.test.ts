import { describe, expect, it } from "vitest";
import { parseWorldState } from "./contract";

const VALID = {
  type: "world_state",
  timestamp_ms: 1792820000000,
  session_id: "demo",
  objects: [
    {
      id: "obj_1",
      position_m: { x: 0.12, y: 0.23, z: 0.18 },
      tracking_state: "tracked",
      confidence: null,
      source_cameras: ["cam_1", "cam_2"],
    },
  ],
};

describe("parseWorldState", () => {
  it("accepts a well-formed world_state message", () => {
    expect(parseWorldState(VALID)).not.toBeNull();
  });

  it("rejects the wrong message type", () => {
    expect(parseWorldState({ ...VALID, type: "selection_command" })).toBeNull();
  });

  it("rejects an invalid tracking_state", () => {
    const bad = { ...VALID, objects: [{ ...VALID.objects[0], tracking_state: "flying" }] };
    expect(parseWorldState(bad)).toBeNull();
  });

  it("rejects a missing position field", () => {
    const bad = { ...VALID, objects: [{ ...VALID.objects[0], position_m: { x: 0, y: 0 } }] };
    expect(parseWorldState(bad)).toBeNull();
  });

  it("rejects non-object input", () => {
    expect(parseWorldState("not json")).toBeNull();
    expect(parseWorldState(null)).toBeNull();
  });
});
