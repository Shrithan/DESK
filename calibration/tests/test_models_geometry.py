import json

import numpy as np
import pytest

from calibration.geometry import pixel_ray_world, project_points, triangulate_point, undistort_pixels
from calibration.models import CalibrationValidationError, CameraExtrinsics, CameraIntrinsics, RigCalibration
from calibration.synthetic import ground_truth_rig

TRUTH = ground_truth_rig()


def test_rig_calibration_roundtrip_and_versioning(tmp_path):
    p = tmp_path / "cal.json"
    cid = TRUTH.save(p)
    back = RigCalibration.load(p)
    assert back.calibration_id == cid
    for k, c in TRUTH.cameras.items():
        assert np.allclose(back.cameras[k].K, c.K) and np.allclose(back.cameras[k].extrinsics.R_world_to_camera, c.extrinsics.R_world_to_camera)
    doc = json.loads(p.read_text())
    assert doc["schema"] == "phantom.rig_calibration" and doc["conventions"]["world_frame"].startswith("right-handed")
    doc["schema_version"] = "2.0.0"
    with pytest.raises(CalibrationValidationError):
        RigCalibration.from_dict(doc)


def test_validation_rejects_bad_geometry():
    with pytest.raises(CalibrationValidationError):
        CameraExtrinsics(np.diag([1.0, 1.0, -1.0]), np.zeros(3)).validate()  # reflection, not a rotation
    with pytest.raises(CalibrationValidationError):
        CameraIntrinsics(640, 360, np.array([[500, 0, 900], [0, 500, 180], [0, 0, 1.0]]), np.zeros(5)).validate()
    d = TRUTH.cameras["cam_1"].extrinsics.to_dict()
    d["camera_center_world_m"] = [9, 9, 9]
    with pytest.raises(CalibrationValidationError):
        CameraExtrinsics.from_dict(d)


def test_known_point_projects_into_every_view_and_triangulates_back():
    X = np.array([0.03, -0.02, 0.07])
    obs = {}
    for cid, cam in TRUTH.cameras.items():
        px = project_points(X, cam)[0]
        assert 0 <= px[0] < 1280 and 0 <= px[1] < 720, cid
        obs[cid] = px
    Xh, errs = triangulate_point(obs, TRUTH.cameras)
    assert np.linalg.norm(Xh - X) < 1e-6 and max(errs.values()) < 1e-4
    # any two views are enough (graceful degradation)
    Xh2, _ = triangulate_point({k: obs[k] for k in ("cam_2", "cam_3")}, TRUTH.cameras)
    assert np.linalg.norm(Xh2 - X) < 1e-6


def test_undistortion_inverts_projection_and_rays_hit_the_point():
    cam = TRUTH.cameras["cam_2"]
    X = np.array([[0.1, 0.05, 0.0], [-0.12, -0.07, 0.04]])
    px = project_points(X, cam)
    n = undistort_pixels(px, cam, normalized=True)
    Xc = X @ cam.extrinsics.R_world_to_camera.T + cam.extrinsics.t_world_to_camera_m
    assert np.allclose(n, Xc[:, :2] / Xc[:, 2:], atol=1e-9)
    o, d = pixel_ray_world(px[0], cam)
    assert np.linalg.norm(np.cross(X[0] - o, d)) < 1e-9


def test_intrinsics_scaling_matches_resized_images():
    intr = TRUTH.cameras["cam_1"].intrinsics
    half = intr.scaled(640, 360)
    assert np.isclose(half.K[0, 0], intr.K[0, 0] / 2) and np.isclose(half.K[0, 2], (intr.K[0, 2] + 0.5) / 2 - 0.5)
