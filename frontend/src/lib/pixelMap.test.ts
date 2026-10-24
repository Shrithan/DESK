import { describe, expect, it } from "vitest";
import { cssClickToNativePixel } from "./pixelMap";

describe("cssClickToNativePixel", () => {
  it("maps a center click 1:1 when aspect ratios match", () => {
    const result = cssClickToNativePixel(640, 360, 1280, 720, 1280, 720);
    expect(result).toEqual({ x: 640, y: 360 });
  });

  it("accounts for top/bottom letterboxing when native is wider than display", () => {
    // Display is square (400x400), native is 16:9 (1280x720) -> letterboxed top/bottom.
    const result = cssClickToNativePixel(200, 200, 400, 400, 1280, 720);
    expect(result).not.toBeNull();
    expect(result!.x).toBeCloseTo(640, 0);
  });

  it("returns null for clicks inside the letterbox bars", () => {
    const result = cssClickToNativePixel(10, 10, 400, 400, 1280, 720);
    expect(result).toBeNull();
  });
});
