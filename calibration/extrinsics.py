"""Multi-camera extrinsics: one checkerboard lying on the table defines the world frame.

Procedure: put the printed board face-up in the middle of the work area (reading orientation,
see calibration/board.py), make sure every camera sees the whole board, grab one
timestamp-matched frameset (the board is static, so sync does not matter), and solve each
camera's pose with solvePnP. Metric scale comes from the measured square size; the board
defines the origin (centre of its inner-corner grid) and axes. Remove the board afterwards:
it is an environment-only calibration aid and must never be attached to a tracked object.
"""

from __future__ import annotations

import time

import cv2
import numpy as np

from .board import R_WORLD_FROM_BOARD, Checkerboard
from .geometry import project_points, triangulate_point
from .models import CameraCalibration, CameraExtrinsics, CameraIntrinsics, RigCalibration


def world_from_board(board: Checkerboard, board_height_m: float = 0.0, origin_offset_m: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """(R, t) with x_world = R @ x_board + t. Origin = grid centre (+ optional offset); board raised by board_height_m."""
    R = R_WORLD_FROM_BOARD
    t = -R @ board.grid_center() + np.array([0.0, 0.0, board_height_m])
    if origin_offset_m is not None:
        t = t - np.asarray(origin_offset_m, float)
    return R, t


def board_world_points(board: Checkerboard, board_height_m: float = 0.0) -> np.ndarray:
    R, t = world_from_board(board, board_height_m)
    return board.object_points() @ R.T + t


def board_pose(detection: np.ndarray, board: Checkerboard, intr: CameraIntrinsics) -> tuple[np.ndarray, np.ndarray, float]:
    """(R_camera_from_board, t, rms_px) via planar IPPE + Levenberg-Marquardt refinement."""
    obj = board.object_points()
    img = detection.reshape(-1, 1, 2).astype(np.float64)
    ok, rvec, tvec = cv2.solvePnP(obj, img, intr.K, intr.dist, flags=cv2.SOLVEPNP_IPPE)
    if not ok:
        raise RuntimeError("solvePnP failed")
    rvec, tvec = cv2.solvePnPRefineLM(obj, img, intr.K, intr.dist, rvec, tvec)
    proj, _ = cv2.projectPoints(obj, rvec, tvec, intr.K, intr.dist)
    rms = float(np.sqrt(np.mean(np.sum((proj.reshape(-1, 2) - detection) ** 2, axis=1))))
    R, _ = cv2.Rodrigues(rvec)
    return R, tvec.ravel(), rms


def calibrate_extrinsics(
    detections: dict[str, np.ndarray | None],
    intrinsics: dict[str, CameraIntrinsics],
    board: Checkerboard,
    rig_name: str = "",
    nominal_centers: dict[str, np.ndarray] | None = None,
    board_height_m: float = 0.0,
    max_nominal_deviation_m: float = 0.15,
) -> RigCalibration:
    """Solve every camera that sees the board; cameras that don't are kept without extrinsics."""
    R_wb, t_wb = world_from_board(board, board_height_m)
    cams: dict[str, CameraCalibration] = {}
    warnings: list[str] = []
    per_cam: dict[str, dict] = {}
    now = int(time.time() * 1000)
    for cid, intr in intrinsics.items():
        det = detections.get(cid)
        if det is None:
            cams[cid] = CameraCalibration(cid, intr, None)
            warnings.append(f"{cid}: board not detected, no extrinsics (camera unusable for 3D until re-run)")
            continue
        R_cb, t_cb, rms = board_pose(det, board, intr)
        R = R_cb @ R_wb.T
        t = t_cb - R @ t_wb
        ext = CameraExtrinsics(R, t, rms_reprojection_px=rms, calibrated_unix_ms=now)
        cams[cid] = CameraCalibration(cid, intr, ext)
        c = ext.camera_center_world_m
        info = {"rms_reprojection_px": round(rms, 4), "camera_center_world_m": np.round(c, 4).tolist(),
                "distance_to_origin_m": round(float(np.linalg.norm(c)), 4)}
        if c[2] <= 0:
            warnings.append(f"{cid}: camera centre below the table (z = {c[2]:.3f} m): board orientation or intrinsics wrong")
        if nominal_centers and cid in nominal_centers:
            dev = float(np.linalg.norm(c - np.asarray(nominal_centers[cid])))
            info["deviation_from_nominal_m"] = round(dev, 4)
            if dev > max_nominal_deviation_m:
                warnings.append(f"{cid}: {dev:.2f} m from its nominal mount position: wrong camera id, board placement or mount")
        per_cam[cid] = info

    rig = RigCalibration(
        cameras=cams,
        rig_name=rig_name,
        world_reference={
            "method": "checkerboard face-up on the table; world origin = centre of its inner-corner grid",
            "board": board.to_dict(),
            "board_height_m": board_height_m,
            "metric_scale_source": f"measured checkerboard square size {board.square_size_m * 1000:.2f} mm",
            "R_world_from_board": R_wb.tolist(),
        },
    )
    rig.validation = {"per_camera": per_cam, "warnings": warnings,
                      **board_triangulation_check(rig, detections, board, board_height_m)}
    return rig


def board_triangulation_check(rig: RigCalibration, detections: dict[str, np.ndarray | None], board: Checkerboard,
                              board_height_m: float = 0.0) -> dict:
    """Triangulate every board corner from all calibrated cameras and compare with the known board."""
    usable = {cid: d for cid, d in detections.items() if d is not None and rig.cameras.get(cid) and rig.cameras[cid].extrinsics}
    if len(usable) < 2:
        return {"board_triangulation": None, "note": "fewer than two calibrated views: no multiview check"}
    truth = board_world_points(board, board_height_m)
    errs, reproj = [], []
    for k in range(board.n_corners):
        X, e = triangulate_point({cid: d[k] for cid, d in usable.items()}, rig.cameras)
        errs.append(np.linalg.norm(X - truth[k]))
        reproj.extend(e.values())
    errs = np.array(errs)
    return {"board_triangulation": {
        "views": sorted(usable),
        "rmse_m": round(float(np.sqrt(np.mean(errs**2))), 6),
        "max_error_m": round(float(errs.max()), 6),
        "mean_reprojection_px": round(float(np.mean(reproj)), 4),
        "note": "measured on the calibration board itself (optimistic); verify off-board with `python -m calibration verify`",
    }}


def verify_board(rig: RigCalibration, detections: dict[str, np.ndarray | None], board: Checkerboard,
                 board_height_m: float = 0.0) -> dict:
    """Independent check / drift monitor: board placed again (optionally raised on a known-height box).

    Reports reprojection error of the expected board pose in each camera (grows if a camera
    moved) and the triangulated corner error, including the error in height (Z).
    """
    truth = board_world_points(board, board_height_m)
    out: dict = {"per_camera_reprojection_px": {}, "board_height_m": board_height_m}
    for cid, d in detections.items():
        cam = rig.cameras.get(cid)
        if d is None or cam is None or cam.extrinsics is None:
            out["per_camera_reprojection_px"][cid] = None
            continue
        diff = project_points(truth, cam) - d
        out["per_camera_reprojection_px"][cid] = round(float(np.sqrt(np.mean(np.sum(diff**2, axis=1)))), 3)
    tri = board_triangulation_check(rig, detections, board, board_height_m)["board_triangulation"]
    out["triangulation"] = tri
    usable = {cid: d for cid, d in detections.items() if d is not None and rig.cameras.get(cid) and rig.cameras[cid].extrinsics}
    if len(usable) >= 2:
        zs = [triangulate_point({cid: d[k] for cid, d in usable.items()}, rig.cameras)[0][2] for k in range(board.n_corners)]
        out["mean_height_m"] = round(float(np.mean(zs)), 5)
        out["height_error_m"] = round(float(np.mean(zs) - board_height_m), 5)
    worst = max((v for v in out["per_camera_reprojection_px"].values() if v is not None), default=None)
    out["status"] = "ok" if worst is not None and worst < 2.0 else "recalibrate" if worst is not None else "no data"
    return out
