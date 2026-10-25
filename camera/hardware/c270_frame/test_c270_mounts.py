"""Checks for the C270 mounts: printable, one piece, clear of the tube, the camera body and its view."""

import json

import numpy as np
from generate_c270_mounts import (
    RING_LEN,
    TUBE_CLEARANCE,
    build_mount,
    print_orientation,
    print_plate,
    sleeve,
    to_trimesh,
    transform,
    axis_basis,
)
from manifold3d import Manifold

from camera.rig import DEFAULT_RIG_CONFIG, load_rig

RIG = load_rig()
BODY = json.loads(DEFAULT_RIG_CONFIG.read_text())["camera_model"]["body_mm"]
TUBE_OD = RIG.frame["tube_od_mm"]


def test_mounts_are_single_watertight_parts():
    for cam in RIG.cameras:
        part = build_mount(cam, TUBE_OD, BODY)
        assert len(part.decompose()) == 1, cam.id
        assert to_trimesh(part).is_watertight, cam.id


def test_mounts_clear_tube_camera_body_and_view():
    for cam in RIG.cameras:
        part = build_mount(cam, TUBE_OD, BODY)
        tube = Manifold.cylinder(400, TUBE_OD / 2, TUBE_OD / 2, 96).translate([0, 0, -200])
        tube = transform(tube, axis_basis(cam.mount["tube_axis"]), [0, 0, 0])
        assert (part ^ tube).volume() < 1e-3, f"{cam.id} intersects the tube"
        _, keep = sleeve(BODY)
        keep = transform(keep, cam.R_world_to_camera.T, np.asarray(cam.mount["lens_offset_from_tube_mm"], float))
        assert (part ^ keep).volume() < 1e-3, f"{cam.id} blocks the camera body or view"


def test_ring_grips_tube_with_clearance():
    # A tube slightly bigger than the bore (+ clearance) must collide: the clamp actually grips.
    cam = RIG.cameras[0]
    part = build_mount(cam, TUBE_OD, BODY)
    fat = Manifold.cylinder(RING_LEN * 0.5, TUBE_OD / 2 + TUBE_CLEARANCE + 0.5, TUBE_OD / 2 + TUBE_CLEARANCE + 0.5, 96)
    fat = transform(fat.translate([0, 0, -RING_LEN * 0.25]), axis_basis(cam.mount["tube_axis"]), [0, 0, 0])
    assert (part ^ fat).volume() > 1.0


def test_individual_prints_fit_both_queue_printers():
    for cam in RIG.cameras:
        p = print_orientation(build_mount(cam, TUBE_OD, BODY), cam.mount["tube_axis"])
        x0, y0, z0, x1, y1, z1 = p.bounding_box()
        assert abs(z0) < 1e-6
        assert max(x1 - x0, y1 - y0) < 210 and z1 - z0 < 210, cam.id
    plate = print_plate([print_orientation(build_mount(c, TUBE_OD, BODY), c.mount["tube_axis"]) for c in RIG.cameras])
    x0, y0, _, x1, y1, _ = plate.bounding_box()
    assert max(x1 - x0, y1 - y0) < 220
