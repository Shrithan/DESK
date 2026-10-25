"""Projection, undistortion and verification triangulation for calibrated cameras.

Agent 3 owns production multiview geometry; these utilities exist so every agent uses the same
conventions (see calibration/models.py) and so calibration can be verified end to end.
"""

from __future__ import annotations

import cv2
import numpy as np

from .models import CameraCalibration


def _require_extrinsics(cam: CameraCalibration):
    if cam.extrinsics is None:
        raise ValueError(f"{cam.camera_id} has no extrinsics; run extrinsic calibration")
    return cam.extrinsics


def world_to_camera(points_world: np.ndarray, cam: CameraCalibration) -> np.ndarray:
    e = _require_extrinsics(cam)
    P = np.asarray(points_world, float).reshape(-1, 3)
    return P @ e.R_world_to_camera.T + e.t_world_to_camera_m


def project_points(points_world: np.ndarray, cam: CameraCalibration) -> np.ndarray:
    """World points (N, 3) in metres -> distorted pixel coordinates (N, 2) as seen in raw frames.

    Points behind the camera come back as NaN.
    """
    e = _require_extrinsics(cam)
    P = np.asarray(points_world, float).reshape(-1, 3)
    rvec, _ = cv2.Rodrigues(e.R_world_to_camera)
    px, _ = cv2.projectPoints(P, rvec, e.t_world_to_camera_m.reshape(3, 1), cam.K, cam.dist)
    px = px.reshape(-1, 2)
    behind = world_to_camera(P, cam)[:, 2] <= 0
    px[behind] = np.nan
    return px


_CRITERIA = (cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS, 40, 1e-10)


def undistort_points_cv(pts: np.ndarray, K: np.ndarray, dist: np.ndarray, P: np.ndarray | None = None) -> np.ndarray:
    """Iterative undistortion working on OpenCV 4.x (undistortPointsIter) and 5.x (criteria argument)."""
    pts = np.asarray(pts, np.float64).reshape(-1, 1, 2)
    if hasattr(cv2, "undistortPointsIter"):
        out = cv2.undistortPointsIter(pts, K, dist, None, P, _CRITERIA)
    else:
        out = cv2.undistortPoints(pts, K, dist, R=None, P=P, criteria=_CRITERIA)
    return out.reshape(-1, 2)


def undistort_pixels(pixels: np.ndarray, cam: CameraCalibration, normalized: bool = False) -> np.ndarray:
    """Raw (distorted) pixels (N, 2) -> undistorted pixels, or normalised camera coordinates (x/z, y/z)."""
    return undistort_points_cv(pixels, cam.K, cam.dist, None if normalized else cam.K)


def undistort_image(image: np.ndarray, cam: CameraCalibration) -> np.ndarray:
    """Undistorted image with the same K (pixels map through projection_matrix())."""
    return cv2.undistort(image, cam.K, cam.dist)


def pixel_ray_world(pixel: np.ndarray, cam: CameraCalibration) -> tuple[np.ndarray, np.ndarray]:
    """(origin, unit direction) in world coordinates of the viewing ray through a raw pixel."""
    e = _require_extrinsics(cam)
    xn = undistort_pixels(np.asarray(pixel, float).reshape(1, 2), cam, normalized=True)[0]
    d = e.R_camera_to_world @ np.array([xn[0], xn[1], 1.0])
    return e.camera_center_world_m, d / np.linalg.norm(d)


def triangulate_point(observations: dict[str, np.ndarray], cams: dict[str, CameraCalibration], refine: bool = True) -> tuple[np.ndarray, dict[str, float]]:
    """Triangulate one world point from raw pixels in >= 2 cameras.

    Linear DLT on undistorted normalised coordinates, then (optionally) Gauss-Newton on raw-pixel
    reprojection error. Returns (X_world (3,), per-camera reprojection error in pixels).
    """
    if len(observations) < 2:
        raise ValueError("need at least two views to triangulate")
    rows = []
    for cid, px in observations.items():
        cam = cams[cid]
        e = _require_extrinsics(cam)
        x, y = undistort_pixels(np.asarray(px, float).reshape(1, 2), cam, normalized=True)[0]
        P = np.hstack([e.R_world_to_camera, e.t_world_to_camera_m.reshape(3, 1)])
        rows.append(x * P[2] - P[0])
        rows.append(y * P[2] - P[1])
    _, _, Vt = np.linalg.svd(np.asarray(rows))
    X = Vt[-1, :3] / Vt[-1, 3]
    if refine:
        X = _refine(X, observations, cams)
    errs = {cid: float(np.linalg.norm(project_points(X, cams[cid])[0] - np.asarray(px, float))) for cid, px in observations.items()}
    return X, errs


def _refine(X: np.ndarray, observations: dict[str, np.ndarray], cams: dict[str, CameraCalibration], iters: int = 10) -> np.ndarray:
    X = X.copy()
    for _ in range(iters):
        J, r = [], []
        for cid, px in observations.items():
            p0 = project_points(X, cams[cid])[0]
            if np.any(np.isnan(p0)):
                return X
            r.append(np.asarray(px, float) - p0)
            Jc = np.zeros((2, 3))
            for k in range(3):
                dX = np.zeros(3)
                dX[k] = 1e-6
                Jc[:, k] = (project_points(X + dX, cams[cid])[0] - p0) / 1e-6
            J.append(Jc)
        J, r = np.vstack(J), np.concatenate(r)
        step, *_ = np.linalg.lstsq(J, r, rcond=None)
        X += step
        if np.linalg.norm(step) < 1e-9:
            break
    return X


def reprojection_rms(points_world: np.ndarray, pixels: np.ndarray, cam: CameraCalibration) -> float:
    d = project_points(points_world, cam) - np.asarray(pixels, float).reshape(-1, 2)
    return float(np.sqrt(np.nanmean(np.sum(d**2, axis=1))))
