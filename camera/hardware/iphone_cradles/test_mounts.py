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


def test_edge_mount_nut_fits_and_bolt_hole_is_blind():
    from generate_mounts import EDGE_BLOCK, NUT_AF, NUT_FLOOR, NUT_T, WALL_T, LIP_T, PLATE_T, EDGE_BLOCK_BACK
    import math
    p = load_phones()["iphone_16_pro"]
    assert p.edge_mount
    cradle = build_cradle(p)
    h = p.height + 2 * CLEARANCE
    z_front = p.depth + CLEARANCE + LIP_T
    x_out = -WALL_T - EDGE_BLOCK[0]
    yc = h * 0.30 + EDGE_BLOCK[1] / 2
    zc = (-PLATE_T - EDGE_BLOCK_BACK + z_front) / 2
    # A real 7/16" nut (11.11 AF, 5.6 thick) sits in the pocket without touching plastic.
    r = 11.11 / 2 / math.cos(math.pi / 6)
    nut = Manifold.cylinder(5.6, r, r, 6).rotate([0, 90, 0]).translate([x_out + NUT_FLOOR + 0.65, yc, zc])
    assert (cradle ^ nut).volume() < 1e-6
    # The wall between the bolt hole and the phone is solid.
    wall_probe = Manifold.cube([WALL_T, 1, 1]).translate([-WALL_T, yc - 0.5, zc - 0.5])
    assert abs((cradle ^ wall_probe).volume() - WALL_T) < 1e-6
