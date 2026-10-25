"""The stand must print in one job per part, assemble without collisions, and see the table straight down."""

import numpy as np
from generate_boom import (
    BORE,
    N_ARM,
    N_LEG,
    PIN_D,
    PIN_Z,
    SEG_LEN,
    SPIGOT_OD,
    Assembly,
    assembled,
    print_parts,
    to_trimesh,
)
from manifold3d import Manifold

BED = (220.0, 220.0, 220.0)  # Flashforge Adventurer 5M (the smaller of the two queue printers)
PARTS = assembled()
A = Assembly()


def test_every_print_is_one_watertight_piece_that_fits_the_5m():
    for name, (m, _) in print_parts().items():
        assert len(m.decompose()) == 1, name
        assert to_trimesh(m).is_watertight, name
        x0, y0, z0, x1, y1, z1 = m.bounding_box()
        assert x1 - x0 <= BED[0] - 10 and y1 - y0 <= BED[1] - 10 and z1 - z0 <= BED[2] - 5, name
        assert abs(z0) < 1e-6, f"{name} must sit on the bed"


def test_joints_slide_together():
    assert BORE - SPIGOT_OD >= 0.4  # radial clearance on each side >= 0.2 mm
    names = list(PARTS)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            v = (PARTS[a] ^ PARTS[b]).volume()
            assert v < 1.0, f"{a} collides with {b} ({v:.1f} mm^3)"


def rod(p, axis, length=90.0):
    r = Manifold.cylinder(length, PIN_D / 2 - 0.3, PIN_D / 2 - 0.3, 24).translate([0, 0, -length / 2])
    r = {"x": r.rotate([0, 90, 0]), "y": r.rotate([90, 0, 0])}[axis]
    return r.translate(list(p))


def test_bolts_pass_through_every_joint():
    pins = [((0, 0, A.base_top + i * SEG_LEN + PIN_Z), "x") for i in range(N_LEG + 1)]
    pins += [((A.arm_start_x + i * SEG_LEN + PIN_Z, 0, A.arm_axis_z), "y") for i in range(N_ARM + 1)]
    whole = Manifold()
    for m in PARTS.values():
        whole = whole + m
    for p, axis in pins:
        assert (whole ^ rod(p, axis)).volume() < 1e-3, f"pin at {p} blocked"


def test_camera_looks_straight_down_with_a_clear_view_of_the_table():
    lens = A.lens
    assert 0.85 < lens[2] / 1000 < 0.95 and 0.40 < lens[0] / 1000 < 0.52
    # view pyramid (60 deg diagonal, the wider spec) from 5 mm below the lens to the table
    tx, ty = np.tan(np.radians(26.5)), np.tan(np.radians(15.5))
    pts = []
    for sx, sy in ((1, 1), (1, -1), (-1, -1), (-1, 1)):
        pts.append([lens[0] + sx * ty * lens[2], lens[1] + sy * tx * lens[2], 0.0])  # image long axis = world Y
    pts.append([lens[0], lens[1], lens[2] - 5])
    pyramid = Manifold.hull_points(pts)
    for name, m in PARTS.items():
        assert (m ^ pyramid).volume() < 1e-3, f"{name} is in the camera's view"
