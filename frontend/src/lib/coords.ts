/**
 * World frame: right-handed, meters, +X right, +Y away from viewer, +Z up.
 * Three.js is Y-up. Documented mapping per shared/contracts/README.md:
 * world(x, y, z) -> three(x, z, -y)
 */
export function worldToThree(x: number, y: number, z: number): [number, number, number] {
  return [x, z, -y];
}

export function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

export function lerpVec3(
  a: [number, number, number],
  b: [number, number, number],
  t: number,
): [number, number, number] {
  return [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)];
}
