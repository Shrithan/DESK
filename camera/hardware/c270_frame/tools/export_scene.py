"""Export frame tubes and nominal camera poses from the rig config as JSON for the three.js preview."""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from camera.rig import DEFAULT_RIG_CONFIG, load_rig  # noqa: E402


def frame_tubes(frame: dict) -> list[list[list[float]]]:
    w, d, h = frame["width_m"] / 2, frame["depth_m"] / 2, frame["height_m"]
    cy = frame["overhead_crossbar_y_m"]
    tubes = []
    for z in (0.0, h):
        tubes += [[[-w, -d, z], [w, -d, z]], [[-w, d, z], [w, d, z]], [[-w, -d, z], [-w, d, z]], [[w, -d, z], [w, d, z]]]
    tubes += [[[x, y, 0.0], [x, y, h]] for x in (-w, w) for y in (-d, d)]
    tubes.append([[-w, cy, h], [w, cy, h]])  # overhead crossbar
    return tubes


def main() -> None:
    rig = load_rig(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_RIG_CONFIG)
    cams = []
    for c in rig.cameras:
        K = c.nominal_K
        cams.append({
            "id": c.id, "role": c.role,
            "lens_m": c.lens_position_m.tolist(),
            "R_camera_to_world": c.R_world_to_camera.T.tolist(),
            "tube_point_m": c.mount["tube_point_m"],
            "stl": f"mount_{c.id}_{c.role}.stl",
            "hfov_deg": float(np.degrees(2 * np.arctan(c.width / 2 / K[0, 0]))),
            "vfov_deg": float(np.degrees(2 * np.arctan(c.height / 2 / K[1, 1]))),
        })
    out = {"frame": rig.frame, "tube_od_m": rig.frame["tube_od_mm"] / 1000, "tubes": frame_tubes(rig.frame),
           "body_mm": rig.camera_model["body_mm"], "cameras": cams}
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
