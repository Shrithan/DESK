"""Calibrated overhead camera -> metric table X/Y, using agent-1 calibration and its synthetic ground truth."""
import json

import cv2
import numpy as np
import pytest

from calibration.geometry import project_points
from calibration.models import CameraCalibration, CameraExtrinsics, CameraIntrinsics, RigCalibration
from calibration.synthetic import ground_truth_rig
from vision.demo import fixture
from vision.live import LiveServer, LiveSession, configure_calibration
from vision.stereo import StereoCalibration
from vision.table_plane import TablePlane, to_stereo_payload

TRUTH = ground_truth_rig()  # cam_1 overhead, cam_2/cam_3 sides, with lens distortion
DOC = TRUTH.to_dict()


@pytest.mark.parametrize('cam', ['cam_1', 'cam_2', 'cam_3'])
def test_known_table_points_map_back_to_metres(cam):
    plane = TablePlane(DOC, cam)
    pts = np.array([[0.0, 0.0, 0.0], [0.12, -0.05, 0.0], [-0.1, 0.08, 0.0]])
    px = project_points(pts, TRUTH.cameras[cam])
    xy = plane.to_table(px, (720, 1280))
    assert np.abs(xy - pts[:, :2]).max() < 1e-5
    # same answer from a half-size frame (the browser analyses <= 800 px)
    assert np.abs(plane.to_table(px / 2 - 0.25, (360, 640)) - pts[:, :2]).max() < 1e-3


def test_points_above_the_table_use_their_height():
    plane = TablePlane(DOC, 'cam_1')
    X = np.array([[0.05, 0.03, 0.08]])
    px = project_points(X, TRUTH.cameras['cam_1'])
    assert np.abs(plane.to_table(px, (720, 1280), height_m=0.08)[0] - X[0, :2]).max() < 1e-5
    flat = plane.to_table(px, (720, 1280))[0]  # assuming z = 0 pushes the point outward (parallax)
    assert np.linalg.norm(flat) > np.linalg.norm(X[0, :2])


def test_agent1_calibration_converts_to_the_stereo_format():
    stereo = StereoCalibration(to_stereo_payload(DOC, 'cam_1', 'cam_2'))
    X = np.array([0.04, -0.02, 0.05])
    a = project_points(X, TRUTH.cameras['cam_2'])[0]
    b = project_points(X, TRUTH.cameras['cam_1'])[0]
    point = stereo.triangulate(a, b, (720, 1280), (720, 1280))
    assert point is not None


def test_rejects_wrong_aspect_and_missing_extrinsics():
    with pytest.raises(ValueError, match='aspect'):
        TablePlane(DOC, 'cam_1').to_table([[10, 10]], (480, 480))
    doc = json.loads(json.dumps(DOC))
    doc['cameras']['cam_1']['extrinsics'] = None
    with pytest.raises(ValueError, match='extrinsics'):
        TablePlane(doc, 'cam_1')


def overhead_rig(w=320, h=240, height=0.9):
    """Straight-down pinhole camera matching vision.demo fixture frames."""
    f = 300.0
    K = np.array([[f, 0, (w - 1) / 2], [0, f, (h - 1) / 2], [0, 0, 1.0]])
    R = np.diag([1.0, -1.0, -1.0])  # image x = +X, image down = -Y, looking down
    C = np.array([0.0, 0.0, height])
    cam = CameraCalibration('cam_1', CameraIntrinsics(w, h, K, np.zeros(5)), CameraExtrinsics(R, -R @ C))
    return RigCalibration({'cam_1': cam}, rig_name='test').to_dict(), cam


def jpeg(frame):
    ok, data = cv2.imencode('.jpg', frame)
    assert ok
    return data.tobytes()


def test_live_overhead_session_reports_metric_table_xy():
    doc, cam = overhead_rig()
    server = LiveServer(('127.0.0.1', 0))
    try:
        info = configure_calibration(server, doc, 'cam_1')
        assert info['method'] == 'table_plane_estimate' and abs(info['lens_height_m'] - 0.9) < 1e-6
        session: LiveSession = server.sessions['top']
        first = session.receive(jpeg(fixture()[0]))
        session.select(first['frame_id'], [80, 70, 160, 150])
        for i in range(1, 6):
            result = session.receive(jpeg(fixture(i)[0]))
        obj = result['objects'][0]
        assert obj['observation']['tracking_state'] == 'tracked'
        x, y = obj['table_xy_m']
        cx, cy = obj['motion']['center_px']  # bbox centre ~ mask centroid
        expected = np.array([(cx - 159.5) / 300 * 0.9, -(cy - 119.5) / 300 * 0.9])
        assert np.abs(np.array([x, y]) - expected).max() < 0.02
        assert result['table_plane']['calibration_version'] == doc['calibration_id']
        # the side camera never gets a table plane
        assert server.sessions['front'].table_plane is None
    finally:
        server.server_close()
