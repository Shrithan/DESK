"""How much of the work area do the cameras share? Reads the rig config (nominal poses).

Prints the largest centred rectangle on the table that every camera sees, for objects from the
table up to a given height, keeping 5 % away from the image edges. Uses the C270's published
diagonal field of view (sources disagree: 55 or 60 degrees, so both are reported).

    python camera/hardware/c270_frame/tools/coverage.py [--object-height-cm 15]
"""

from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from camera.rig import DEFAULT_RIG_CONFIG, load_rig, nominal_intrinsics  # noqa: E402

MARGIN = 0.05


def seen(P: np.ndarray, K: np.ndarray, size: tuple[int, int], cam) -> np.ndarray:
    q = (P - cam.lens_position_m) @ cam.R_world_to_camera.T
    z = q[:, 2]
    with np.errstate(divide="ignore", invalid="ignore"):
        u = K[0, 0] * q[:, 0] / z + K[0, 2]
        v = K[1, 1] * q[:, 1] / z + K[1, 2]
    w, h = size
    return (z > 0) & (u > MARGIN * w) & (u < (1 - MARGIN) * w) & (v > MARGIN * h) & (v < (1 - MARGIN) * h)


def shared_rect(cams, K, size, heights) -> tuple[float, float]:
    """Largest-area centred rectangle (width x depth, m) inside every camera's view at all heights."""
    best = (0.0, 0.0)
    for w in np.arange(0.05, 1.21, 0.01):
        lo, hi = 0.0, 1.0
        for _ in range(22):
            d = (lo + hi) / 2
            X, Y = np.meshgrid(np.linspace(-w / 2, w / 2, 21), np.linspace(-d / 2, d / 2, 21))
            P = np.concatenate([np.stack([X.ravel(), Y.ravel(), np.full(X.size, z)], 1) for z in heights])
            ok = np.ones(len(P), bool)
            for c in cams:
                ok &= seen(P, K, size, c)
            lo, hi = (d, hi) if ok.all() else (lo, d)
        if w * lo > best[0] * best[1]:
            best = (w, lo)
    return best


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rig", default=str(DEFAULT_RIG_CONFIG))
    ap.add_argument("--object-height-cm", type=float, default=15.0)
    args = ap.parse_args()
    rig = load_rig(args.rig)
    size = (rig.cameras[0].width, rig.cameras[0].height)
    heights = np.linspace(0, args.object_height_cm / 100, 3)
    print(f"rig {rig.name}: frame {rig.frame['width_m']} x {rig.frame['depth_m']} x {rig.frame['height_m']} m")
    for fov in (55.0, 60.0):
        K = nominal_intrinsics(*size, fov)
        w0, d0 = shared_rect(rig.cameras, K, size, [0.0])
        w1, d1 = shared_rect(rig.cameras, K, size, heights)
        print(f"  dFOV {fov:.0f} deg: all {len(rig.cameras)} see {w0 * 100:.0f} x {d0 * 100:.0f} cm at table level, "
              f"{w1 * 100:.0f} x {d1 * 100:.0f} cm for objects up to {args.object_height_cm:.0f} cm tall")
        for pair in itertools.combinations(rig.cameras, 2):
            w2, d2 = shared_rect(pair, K, size, heights)
            print(f"      if only {pair[0].id}+{pair[1].id}: {w2 * 100:.0f} x {d2 * 100:.0f} cm")
    for c in rig.cameras:
        dist = np.linalg.norm(c.lens_position_m)
        print(f"  {c.id}: lens {np.round(c.lens_position_m, 3).tolist()} m, {dist:.2f} m from the table centre, "
              f"{(c.lens_position_m[2] - args.object_height_cm / 100):.2f}-{c.lens_position_m[2]:.2f} m above objects/table")


if __name__ == "__main__":
    main()
