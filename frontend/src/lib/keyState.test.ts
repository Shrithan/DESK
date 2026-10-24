import { describe, expect, it } from "vitest";
import { parseKeyState } from "./keyState";

// Matches shared/contracts/fixtures/tilt/key_state_forward_left.json from Agent 3's contract.
const VALID = { type: "key_state", schema_version: "1.0.0", timestamp_ms: 1792820000233, held: ["a", "w"], enabled: true, mode: "active" };

describe("parseKeyState", () => {
  it("accepts a well-formed key_state message", () => {
    expect(parseKeyState(VALID)).toEqual(VALID);
  });

  it("rejects the wrong message type", () => {
    expect(parseKeyState({ ...VALID, type: "tilt_update" })).toBeNull();
  });

  it("rejects a missing held array", () => {
    const { held: _held, ...rest } = VALID;
    expect(parseKeyState(rest)).toBeNull();
  });

  it("rejects a non-string held entry", () => {
    expect(parseKeyState({ ...VALID, held: ["w", 2] })).toBeNull();
  });

  it("rejects an unsupported major schema version", () => {
    expect(parseKeyState({ ...VALID, schema_version: "2.0.0" })).toBeNull();
  });

  it("defaults mode and enabled when omitted, per the optional-field contract", () => {
    const { mode: _mode, enabled: _enabled, ...rest } = VALID;
    expect(parseKeyState(rest)).toEqual({ ...VALID, mode: "active", enabled: true });
  });

  it("rejects non-object input", () => {
    expect(parseKeyState("nope")).toBeNull();
    expect(parseKeyState(null)).toBeNull();
  });
});
