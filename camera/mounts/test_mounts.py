"""Smoke tests for the cradle generator: printable meshes, phone fits, camera stays uncovered."""

from generate_mounts import CLEARANCE, build_cradle, load_phones, to_trimesh
from manifold3d import Manifold


def phone_body(p, case_t=0.0):
    # Phone sits inside the clearance envelope, back on z = 0.
    return Manifold.cube([p.width + 2 * case_t, p.height + 2 * case_t, p.depth + 2 * case_t]).translate(
        [CLEARANCE, CLEARANCE, 0.0]
    )


def test_cradles_are_watertight_and_phone_fits():
    for p in load_phones().values():
        for case_t in (0.0, 1.5):
            cradle = build_cradle(p, case_t)
            mesh = to_trimesh(cradle)
            assert mesh.is_watertight, p.name
            assert (cradle ^ phone_body(p, case_t)).volume() < 1e-6, f"{p.name} collides with cradle"


def test_camera_corner_is_open():
    for p in load_phones().values():
        cradle = build_cradle(p)
        # Keep-out over the camera corner, from far behind the plate to beyond the bump.
        w, h = p.width + 2 * CLEARANCE, p.height + 2 * CLEARANCE
        keep_out = Manifold.cube([p.notch_w - 1, p.notch_h - 1, 40]).translate([w - p.notch_w + 1, h - p.notch_h + 1, -30])
        assert (cradle ^ keep_out).volume() < 1e-6, p.name
