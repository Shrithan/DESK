"""Metric table-plane mapping for a calibrated overhead camera.

One calibrated camera cannot measure depth. It *can* turn a pixel into metres on a known
plane: undistort it, cast the viewing ray and intersect it with the table (z = plane height).
For an object of height h whose image point is its top, the X/Y error is about
r * h / H (r = distance from the point under the lens, H = lens height), e.g. ~1 cm for a
5 cm tall object 20 cm off-centre under a 0.9 m camera. Results are labelled
'table_plane_estimate', never as triangulated 3D.

Accepts either calibration format:
* calibration/ (agent 1): {"schema": "phantom.rig_calibration", "cameras": {"cam_1": {...}}}
* vision/stereo.py: {"units": "meters", "axes": "x-right_y-forward_z-up", "cameras": {"top": {...}}}
Both use metres, +X right, +Y forward/away, +Z up and x_cam = R x_world + t.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np


def _array(value, shape, name):
    a = np.asarray(value, dtype=float)
    if a.shape != shape or not np.isfinite(a).all():
        raise ValueError(f'{name} must be finite with shape {shape}')
    return a


def camera_from_payload(payload: dict, camera: str) -> dict:
    """Normalise one camera from either calibration format to K, distortion, R, t, image size."""
    cams = payload.get('cameras', {})
    if camera not in cams:
        raise ValueError(f'calibration has no camera {camera!r} (has {sorted(cams)})')
    item = cams[camera]
    if payload.get('schema') == 'phantom.rig_calibration':
        if item.get('extrinsics') is None:
            raise ValueError(f'{camera} has intrinsics only; run `python -m calibration extrinsics` first')
        intr, ext = item['intrinsics'], item['extrinsics']
        K, dist = intr['K'], intr['dist']
        size = [intr['image_size']['width'], intr['image_size']['height']]
        R, t = ext['R_world_to_camera'], ext['t_world_to_camera_m']
    else:
        if payload.get('units') != 'meters' or payload.get('axes') != 'x-right_y-forward_z-up':
            raise ValueError('calibration requires meters and x-right_y-forward_z-up axes')
        K, dist, size = item.get('K'), item.get('distortion', [0, 0, 0, 0, 0]), item.get('image_size')
        R, t = item.get('R_world_to_camera'), item.get('t_world_to_camera_m')
    K = _array(K, (3, 3), f'{camera}.K')
    R = _array(R, (3, 3), f'{camera}.R_world_to_camera')
    t = _array(t, (3,), f'{camera}.t_world_to_camera_m')
    size = _array(size, (2,), f'{camera}.image_size')
    dist = np.asarray(dist, dtype=float).ravel()
    if (not np.allclose(R @ R.T, np.eye(3), atol=1e-4) or np.linalg.det(R) < .999 or K[0, 0] <= 0
            or K[1, 1] <= 0 or min(size) <= 0 or len(dist) not in (4, 5, 8, 12, 14)):
        raise ValueError(f'invalid calibration for {camera}')
    return dict(K=K, dist=dist, R=R, t=t, size=size)


def to_stereo_payload(payload: dict, top: str, front: str) -> dict:
    """Convert an agent-1 rig calibration into vision/stereo.py's {front, top} format."""
    version = payload.get('calibration_id') or payload.get('version') or 'converted'
    cams = {}
    for role, cid in (('top', top), ('front', front)):
        c = camera_from_payload(payload, cid)
        cams[role] = dict(K=c['K'].tolist(), distortion=c['dist'].tolist(), image_size=c['size'].tolist(),
                          R_world_to_camera=c['R'].tolist(), t_world_to_camera_m=c['t'].tolist())
    return dict(version=str(version), units='meters', axes='x-right_y-forward_z-up', cameras=cams)


class TablePlane:
    """Pixel in the overhead camera -> metres on the table plane z = plane_height_m."""

    def __init__(self, payload: dict, camera: str = 'top', plane_height_m: float = 0.0):
        self.camera = camera
        self.version = str(payload.get('calibration_id') or payload.get('version') or 'unknown')
        c = camera_from_payload(payload, camera)
        self.K, self.dist, self.R, self.t, self.size = c['K'], c['dist'], c['R'], c['t'], c['size']
        self.center = -self.R.T @ self.t
        self.plane_height_m = float(plane_height_m)
        if self.center[2] <= self.plane_height_m:
            raise ValueError('camera centre is not above the table plane; check the calibration axes')

    @classmethod
    def load(cls, path: str | Path, camera: str, plane_height_m: float = 0.0) -> 'TablePlane':
        return cls(json.loads(Path(path).read_text()), camera, plane_height_m)

    def scaled_K(self, frame_shape) -> np.ndarray:
        h, w = frame_shape[:2]
        ow, oh = self.size
        if abs(w / h - ow / oh) > .015:
            raise ValueError('camera aspect ratio differs from calibration; recalibrate at this resolution')
        sx, sy = w / ow, h / oh  # pixel-centre aware scaling, as in calibration.models.scaled
        K = self.K.copy()
        K[0, 0] *= sx
        K[0, 2] = (K[0, 2] + .5) * sx - .5
        K[1, 1] *= sy
        K[1, 2] = (K[1, 2] + .5) * sy - .5
        return K

    def to_table(self, pixels_xy, frame_shape, height_m: float | None = None) -> np.ndarray:
        """(N, 2) raw pixels in a frame of frame_shape -> (N, 2) metres on z = height (NaN if no hit)."""
        z = self.plane_height_m if height_m is None else float(height_m)
        pts = np.asarray(pixels_xy, dtype=np.float64).reshape(-1, 1, 2)
        n = cv2.undistortPoints(pts, self.scaled_K(frame_shape), self.dist).reshape(-1, 2)
        rays = np.column_stack([n, np.ones(len(n))]) @ self.R  # camera -> world directions (R^T d)
        with np.errstate(divide='ignore', invalid='ignore'):
            s = (z - self.center[2]) / rays[:, 2]
        out = self.center[:2] + s[:, None] * rays[:, :2]
        out[~(s > 0)] = np.nan
        return out

    def describe(self) -> dict:
        return dict(camera=self.camera, calibration_version=self.version, plane_height_m=self.plane_height_m,
                    lens_height_m=round(float(self.center[2] - self.plane_height_m), 4),
                    method='table_plane_estimate', note='metric X/Y on the table plane; height not measured')
