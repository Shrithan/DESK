import { describe, expect, it } from "vitest";
import { matchRoleProfile } from "./roleProfiles";

describe("matchRoleProfile", () => {
  it("matches a full natural-language sentence by substring", () => {
    expect(matchRoleProfile("okay this is a steering wheel for this game")?.id).toBe("steering_wheel");
  });

  it("prefers the longest matching phrase across profiles, not just the first found", () => {
    // Contains "wheel" (steering_wheel) and "jump button" (jump_button, longer match wins).
    expect(matchRoleProfile("jump button near the wheel")?.id).toBe("jump_button");
  });

  it("matches brake distinctly from gas", () => {
    expect(matchRoleProfile("use this as the brake")?.id).toBe("brake");
  });

  it("matches jump button", () => {
    expect(matchRoleProfile("this is a jump button")?.id).toBe("jump_button");
  });

  it("is case-insensitive", () => {
    expect(matchRoleProfile("THIS IS A STEERING WHEEL")?.id).toBe("steering_wheel");
  });

  it("returns null for unrecognized phrases", () => {
    expect(matchRoleProfile("what time is it")).toBeNull();
  });
});
