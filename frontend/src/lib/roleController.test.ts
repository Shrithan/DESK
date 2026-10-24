import { describe, expect, it } from "vitest";
import { RoleController } from "./roleController";
import { ROLE_PROFILES } from "./roleProfiles";

const steeringWheel = ROLE_PROFILES.find((p) => p.id === "steering_wheel")!;
const jumpButton = ROLE_PROFILES.find((p) => p.id === "jump_button")!;

describe("RoleController", () => {
  it("engages the right key once displacement exceeds onThreshold", () => {
    const c = new RoleController();
    c.assign("obj_1", steeringWheel, { x: 0, y: 0, z: 0 });
    expect(c.update("obj_1", { x: 0.1, y: 0, z: 0 })).toEqual([{ key: "d", down: true }]);
  });

  it("engages the left key for negative displacement", () => {
    const c = new RoleController();
    c.assign("obj_1", steeringWheel, { x: 0, y: 0, z: 0 });
    expect(c.update("obj_1", { x: -0.1, y: 0, z: 0 })).toEqual([{ key: "a", down: true }]);
  });

  it("does not re-fire down while already active", () => {
    const c = new RoleController();
    c.assign("obj_1", steeringWheel, { x: 0, y: 0, z: 0 });
    c.update("obj_1", { x: 0.1, y: 0, z: 0 });
    expect(c.update("obj_1", { x: 0.12, y: 0, z: 0 })).toEqual([]);
  });

  it("does not release until displacement drops below offThreshold (hysteresis)", () => {
    const c = new RoleController();
    c.assign("obj_1", steeringWheel, { x: 0, y: 0, z: 0 });
    c.update("obj_1", { x: 0.1, y: 0, z: 0 }); // engages at on=0.08
    // Between off(0.04) and on(0.08) -- still held, no flicker.
    expect(c.update("obj_1", { x: 0.06, y: 0, z: 0 })).toEqual([]);
    expect(c.update("obj_1", { x: 0.03, y: 0, z: 0 })).toEqual([{ key: "d", down: false }]);
  });

  it("ignores movement within the deadzone", () => {
    const c = new RoleController();
    c.assign("obj_1", steeringWheel, { x: 0, y: 0, z: 0 });
    expect(c.update("obj_1", { x: 0.02, y: 0, z: -0.02 })).toEqual([]);
  });

  it("is relative to the calibrated center, not absolute position", () => {
    const c = new RoleController();
    c.assign("obj_1", steeringWheel, { x: 0.5, y: 0.5, z: 0.5 });
    expect(c.update("obj_1", { x: 0.5, y: 0.5, z: 0.5 })).toEqual([]);
    expect(c.update("obj_1", { x: 0.65, y: 0.5, z: 0.5 })).toEqual([{ key: "d", down: true }]);
  });

  it("releases held keys when unassigned", () => {
    const c = new RoleController();
    c.assign("obj_1", steeringWheel, { x: 0, y: 0, z: 0 });
    c.update("obj_1", { x: 0.1, y: 0, z: 0 });
    expect(c.unassign("obj_1")).toEqual([{ key: "d", down: false }]);
  });

  it("unassign is a no-op (empty transitions) when nothing was held", () => {
    const c = new RoleController();
    c.assign("obj_1", steeringWheel, { x: 0, y: 0, z: 0 });
    expect(c.unassign("obj_1")).toEqual([]);
  });

  it("tracks independent assignments for different objects simultaneously", () => {
    const c = new RoleController();
    c.assign("obj_1", steeringWheel, { x: 0, y: 0, z: 0 });
    c.assign("obj_2", jumpButton, { x: 0, y: 0, z: 0 });
    expect(c.update("obj_1", { x: 0.1, y: 0, z: 0 })).toEqual([{ key: "d", down: true }]);
    expect(c.update("obj_2", { x: 0, y: 0, z: 0.1 })).toEqual([{ key: "space", down: true }]);
  });

  it("re-assigning an object re-centers and releases its prior keys", () => {
    const c = new RoleController();
    c.assign("obj_1", steeringWheel, { x: 0, y: 0, z: 0 });
    c.update("obj_1", { x: 0.1, y: 0, z: 0 }); // 'd' held
    const transitions = c.assign("obj_1", steeringWheel, { x: 0.1, y: 0, z: 0 });
    expect(transitions).toContainEqual({ key: "d", down: false });
    expect(c.update("obj_1", { x: 0.1, y: 0, z: 0 })).toEqual([]); // new center, no displacement
  });

  it("ignores updates for an unassigned object", () => {
    const c = new RoleController();
    expect(c.update("obj_99", { x: 1, y: 1, z: 1 })).toEqual([]);
  });
});
