"""Integration smoke test: recorded (synthetic) clips -> ingest service -> HTTP API -> frameset -> 3D.

Uses camera/fixtures/synthetic_rig (regenerate with `python -m calibration synth-fixtures`).
The ball is found with a colour threshold purely to close the loop in this test; object
detection/segmentation is agent 2's job.
"""

import json
import time

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from calibration.geometry import triangulate_point
from calibration.models import RigCalibration
from camera.ingest import CameraHub
from camera.rig import REPO_ROOT, load_rig
from camera.server import create_app

FIX = REPO_ROOT / "camera" / "fixtures" / "synthetic_rig"
IDS = ["cam_1", "cam_2", "cam_3"]


@pytest.fixture(scope="module")
def hub():
    rig = load_rig(overrides={c: {"kind": "video", "path": str(FIX / f"{c}.mp4")} for c in IDS})
    h = CameraHub(rig, calibration_version="synthetic-ground-truth").start()
    assert h.wait_until_streaming(10, min_frames=3)
    yield h
    h.stop()


def ball_pixel(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (0, 120, 60), (15, 255, 255))
    m = cv2.moments(mask, binaryImage=True)
    return None if m["m00"] < 20 else np.array([m["m10"] / m["m00"], m["m01"] / m["m00"]])


def test_http_api_inventory_snapshot_health(hub):
    c = TestClient(create_app(hub))
    inv = c.get("/api/cameras").json()
    assert inv["schema"] == "phantom.camera_inventory" and [x["camera_id"] for x in inv["cameras"]] == IDS
    assert all(x["frame_size"] == {"width": 640, "height": 360} for x in inv["cameras"])
    r = c.get("/api/cameras/cam_2/snapshot.jpg")
    assert r.status_code == 200 and r.headers["x-camera-id"] == "cam_2"
    assert int(r.headers["x-capture-time-monotonic-ns"]) > 0 and r.headers["x-calibration-version"] == "synthetic-ground-truth"
    assert c.get("/api/cameras/cam_9/snapshot.jpg").status_code == 404
    assert c.get("/api/health").json()["status"] == "ok"
    assert "Camera diagnostics" in c.get("/").text
    assert c.get("/api/cameras/cam_1/board_check").json()["detected"] is False


def test_frameset_reports_simulated_timestamp_offsets(hub):
    c = TestClient(create_app(hub))
    offs = {k: [] for k in IDS}
    for _ in range(12):
        fs = c.get("/api/frameset?max_width=64").json()
        assert fs["complete"], fs["missing"]
        for k, v in fs["offsets_ms"].items():
            offs[k].append(v)
        time.sleep(0.05)
    rel = {k: np.median(v) - np.median(offs["cam_1"]) for k, v in offs.items()}
    # sidecars stamp cam_2 7 ms late and cam_3 11 ms early: pairing must expose, not hide, that
    assert abs(rel["cam_2"] - 7) < 1.0 and abs(rel["cam_3"] + 11) < 1.0


def test_known_trajectory_is_recovered_in_3d(hub):
    cal = RigCalibration.load(FIX / "ground_truth_calibration_640x360.json")
    traj = json.loads((FIX / "ball_trajectory.json").read_text())
    fps = traj["fps"]
    truth = np.array([[s["position_m"]["x"], s["position_m"]["y"], s["position_m"]["z"]] for s in traj["samples"]])
    errs = []
    for _ in range(10):
        fs = hub.frameset(tolerance_ms=20)
        obs, idx = {}, None
        for cid, f in fs.frames.items():
            p = ball_pixel(f.image)
            if p is not None:
                obs[cid] = p
            if cid == "cam_1":  # cam_1 has no simulated offset: its clip time gives the true sample index
                idx = int(round((f.capture_time_monotonic_ns - hub.epoch_ns) / 1e9 * fps)) % len(truth)
        if len(obs) >= 2 and idx is not None and "cam_1" in obs:
            X, _ = triangulate_point(obs, cal.cameras)
            errs.append(np.linalg.norm(X - truth[idx]))
        time.sleep(0.07)
    assert len(errs) >= 5
    # sphere centroid != projected centre exactly, and cam_2/cam_3 frames are up to ~1 frame off in time
    assert np.median(errs) < 0.01, errs
