"""Full calibration on rendered images with known ground truth (synthetic: no sensor noise, motion blur or lighting)."""

import numpy as np
import pytest

from calibration.board import Checkerboard
from calibration.extrinsics import board_world_points, calibrate_extrinsics, verify_board
from calibration.geometry import project_points
from calibration.intrinsics import calibrate_intrinsics, image_coverage
from calibration.models import CameraExtrinsics
from calibration.synthetic import Scene, board_scene, ground_truth_rig, intrinsics_views, render

BOARD = Checkerboard()


@pytest.fixture(scope="module")
def truth():
    return ground_truth_rig(seed=3)


@pytest.fixture(scope="module")
def board_images(truth):
    return {cid: render(c, board_scene(BOARD)) for cid, c in truth.cameras.items()}


def rot_err_deg(Ra, Rb):
    return float(np.degrees(np.arccos(np.clip((np.trace(Ra @ Rb.T) - 1) / 2, -1, 1))))


def test_detection_returns_canonical_corner_order_even_for_a_rotated_board(truth):
    cam = truth.cameras["cam_1"]
    for flip in (False, True):
        sc = board_scene(BOARD)
        if flip:  # board turned 180 degrees on the table about its grid centre
            Rz = np.diag([-1.0, -1.0, 1.0])
            c = sc.R_world_from_board @ BOARD.grid_center() + sc.t_world_from_board
            sc = Scene(board=BOARD, R_world_from_board=Rz @ sc.R_world_from_board, t_world_from_board=Rz @ (sc.t_world_from_board - c) + c)
        det = BOARD.detect(render(cam, sc))
        corner0_world = sc.R_world_from_board @ BOARD.object_points()[0] + sc.t_world_from_board
        assert np.linalg.norm(det[0] - project_points(corner0_world, cam)[0]) < 1.0


def test_intrinsics_recovered_from_rendered_views(truth):
    intr = truth.cameras["cam_3"].intrinsics.scaled(640, 360)
    views = intrinsics_views(intr, BOARD, 14, seed=5)
    dets = [d for d in (BOARD.detect(v) for v in views) if d is not None]
    assert len(dets) >= 12
    est = calibrate_intrinsics(dets, BOARD, (640, 360))
    assert est.rms_reprojection_px < 0.3
    assert abs(est.K[0, 0] / intr.K[0, 0] - 1) < 0.005
    assert np.linalg.norm(est.K[:2, 2] - intr.K[:2, 2]) < 3.0
    assert np.allclose(est.dist[:2], intr.dist[:2], atol=0.03)
    assert image_coverage(dets, (640, 360)) > 0.5


def test_extrinsics_match_ground_truth(truth, board_images):
    dets = {cid: BOARD.detect(im) for cid, im in board_images.items()}
    assert all(d is not None for d in dets.values())
    rig = calibrate_extrinsics(dets, {c: v.intrinsics for c, v in truth.cameras.items()}, BOARD, "test",
                               {c: v.extrinsics.camera_center_world_m for c, v in truth.cameras.items()})
    # The overhead camera sees the small flat board almost head-on through a narrow lens, where
    # tilt and shift are weakly separable: it is the least certain pose (~1 mm / ~0.1 deg here).
    for cid, c in rig.cameras.items():
        t = truth.cameras[cid].extrinsics
        assert np.linalg.norm(c.extrinsics.camera_center_world_m - t.camera_center_world_m) < 0.003, cid
        assert rot_err_deg(c.extrinsics.R_world_to_camera, t.R_world_to_camera) < 0.2, cid
    tri = rig.validation["board_triangulation"]
    assert tri["rmse_m"] < 0.001 and not rig.validation["warnings"]


def test_missing_camera_still_calibrates_the_rest(truth, board_images):
    dets = {cid: BOARD.detect(im) for cid, im in board_images.items()}
    dets["cam_1"] = None
    rig = calibrate_extrinsics(dets, {c: v.intrinsics for c, v in truth.cameras.items()}, BOARD)
    assert rig.cameras["cam_1"].extrinsics is None
    assert rig.validation["board_triangulation"]["views"] == ["cam_2", "cam_3"]
    assert any("cam_1" in w for w in rig.validation["warnings"])


def test_verify_measures_height_and_detects_a_bumped_camera(truth):
    raised = 0.05  # board on a 50 mm block: checks Z, not just the calibration plane
    imgs = {cid: render(c, board_scene(BOARD, raised)) for cid, c in truth.cameras.items()}
    dets = {cid: BOARD.detect(im) for cid, im in imgs.items()}
    rep = verify_board(truth, dets, BOARD, raised)
    assert rep["status"] == "ok" and abs(rep["height_error_m"]) < 0.001
    assert np.allclose(board_world_points(BOARD, raised)[:, 2], raised)

    import copy
    import cv2

    bumped = copy.deepcopy(truth)
    e = bumped.cameras["cam_2"].extrinsics
    dR, _ = cv2.Rodrigues(np.radians([1.0, 0, 0]))  # a 1 degree knock
    bumped.cameras["cam_2"].extrinsics = CameraExtrinsics(dR @ e.R_world_to_camera, dR @ e.t_world_to_camera_m)
    rep2 = verify_board(bumped, dets, BOARD, raised)
    assert rep2["status"] == "recalibrate" and rep2["per_camera_reprojection_px"]["cam_2"] > 10
