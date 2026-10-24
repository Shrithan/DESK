import { describe, expect, it } from "vitest";
import { lerp, lerpVec3, worldToThree } from "./coords";

describe("worldToThree", () => {
  it("maps world(x,y,z) to three(x,z,-y)", () => {
    expect(worldToThree(1, 2, 3)).toEqual([1, 3, -2]);
  });

  it("keeps +Z up as +Y up in three space", () => {
    const [, threeY] = worldToThree(0, 0, 0.5);
    expect(threeY).toBe(0.5);
  });
});

describe("lerp / lerpVec3", () => {
  it("interpolates scalars", () => {
    expect(lerp(0, 10, 0.5)).toBe(5);
  });

  it("interpolates vectors component-wise", () => {
    expect(lerpVec3([0, 0, 0], [2, 4, 6], 0.5)).toEqual([1, 2, 3]);
  });
});
