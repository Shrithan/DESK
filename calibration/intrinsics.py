"""Per-camera intrinsic calibration from checkerboard views.

Lens advice for the C270: it is fixed-focus (good: focus cannot drift), so calibrate at the
working resolution (1280x720) and never change resolution or digital zoom afterwards. Hold
the board 0.3-0.8 m away, tilt it up to ~40 degrees, and cover every part of the image,
especially the corners where distortion is strongest.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from .board import Checkerboard
from .models import CameraIntrinsics

log = logging.getLogger(__name__)


def calibrate_intrinsics(
    detections: list[np.ndarray], board: Checkerboard, image_size: tuple[int, int],
    fix_k3: bool = True, reject_factor: float = 3.0,
) -> CameraIntrinsics:
    """Run cv2.calibrateCamera; drop views whose RMS exceeds reject_factor x median, re-run once.

    image_size = (width, height). k3 is fixed to 0 by default: the C270's mild distortion does
    not need it and leaving it free overfits with few views.
    """
    if len(detections) < 6:
        raise ValueError(f"need at least 6 board views, got {len(detections)}")
    obj = board.object_points().astype(np.float32)
    flags = cv2.CALIB_FIX_K3 if fix_k3 else 0

    def run(dets):
        imgpts = [d.astype(np.float32).reshape(-1, 1, 2) for d in dets]
        rms, K, dist, rvecs, tvecs = cv2.calibrateCamera([obj] * len(dets), imgpts, image_size, None, None, flags=flags)
        per_view = []
        for d, rv, tv in zip(dets, rvecs, tvecs):
            proj, _ = cv2.projectPoints(obj.astype(np.float64), rv, tv, K, dist)
            per_view.append(float(np.sqrt(np.mean(np.sum((proj.reshape(-1, 2) - d) ** 2, axis=1)))))
        return rms, K, dist, per_view

    rms, K, dist, per_view = run(detections)
    med = float(np.median(per_view))
    keep = [d for d, e in zip(detections, per_view) if e <= max(reject_factor * med, 0.5)]
    if 6 <= len(keep) < len(detections):
        log.info("rejected %d/%d views with high error (median %.3f px)", len(detections) - len(keep), len(detections), med)
        rms, K, dist, per_view = run(keep)
    d5 = np.zeros(5)
    d5[: min(5, dist.size)] = dist.ravel()[:5]
    return CameraIntrinsics(
        image_width=image_size[0], image_height=image_size[1], K=K, dist=d5,
        rms_reprojection_px=float(rms), num_views=len(per_view), per_view_rms_px=[round(e, 4) for e in per_view],
        calibrated_unix_ms=int(time.time() * 1000),
    )


def image_coverage(detections: list[np.ndarray], image_size: tuple[int, int], grid: int = 4) -> float:
    """Fraction of a grid x grid tiling of the image touched by at least one detected corner."""
    w, h = image_size
    hit = np.zeros((grid, grid), bool)
    for d in detections:
        gx = np.clip((d[:, 0] / w * grid).astype(int), 0, grid - 1)
        gy = np.clip((d[:, 1] / h * grid).astype(int), 0, grid - 1)
        hit[gy, gx] = True
    return float(hit.mean())


def sharpness(gray: np.ndarray, corners: np.ndarray) -> float:
    x0, y0 = np.floor(corners.min(axis=0)).astype(int)
    x1, y1 = np.ceil(corners.max(axis=0)).astype(int)
    roi = gray[max(y0, 0) : y1, max(x0, 0) : x1]
    return float(cv2.Laplacian(roi, cv2.CV_64F).var()) if roi.size else 0.0


@dataclass
class ViewSelector:
    """Accepts a detection only if it differs enough from the views already kept."""

    image_size: tuple[int, int]
    min_distance: float = 0.08
    min_sharpness: float = 30.0
    kept: list[np.ndarray] = field(default_factory=list)
    _features: list[np.ndarray] = field(default_factory=list)

    def features(self, d: np.ndarray, board: Checkerboard) -> np.ndarray:
        w, h = self.image_size
        g = d.reshape(board.rows, board.cols, 2)
        c = d.mean(axis=0)
        top, bottom = np.linalg.norm(g[0, -1] - g[0, 0]), np.linalg.norm(g[-1, -1] - g[-1, 0])
        left, right = np.linalg.norm(g[-1, 0] - g[0, 0]), np.linalg.norm(g[-1, -1] - g[0, -1])
        area = cv2.contourArea(np.array([g[0, 0], g[0, -1], g[-1, -1], g[-1, 0]], np.float32))
        return np.array([c[0] / w, c[1] / h, np.sqrt(area) / np.hypot(w, h), (top - bottom) / (top + bottom), (left - right) / (left + right)])

    def offer(self, gray: np.ndarray, d: np.ndarray, board: Checkerboard) -> bool:
        if sharpness(gray, d) < self.min_sharpness:
            return False
        f = self.features(d, board)
        if self._features and min(np.linalg.norm(f - g) for g in self._features) < self.min_distance:
            return False
        self._features.append(f)
        self.kept.append(d)
        return True


def capture_views(
    get_image: Callable[[], np.ndarray | None], board: Checkerboard, n_views: int = 20,
    timeout_s: float = 300.0, save_dir: Path | None = None, on_progress: Callable[[str], None] = print,
) -> tuple[list[np.ndarray], tuple[int, int]]:
    """Pull frames until n_views varied, sharp board views are collected (or timeout)."""
    selector: ViewSelector | None = None
    size = None
    end = time.monotonic() + timeout_s
    last_msg = 0.0
    while len(selector.kept if selector else []) < n_views and time.monotonic() < end:
        img = get_image()
        if img is None:
            time.sleep(0.05)
            continue
        size = (img.shape[1], img.shape[0])
        selector = selector or ViewSelector(size)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
        d = board.detect(gray)
        if d is not None and selector.offer(gray, d, board):
            if save_dir is not None:
                save_dir.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(save_dir / f"view_{len(selector.kept):02d}.png"), img)
            on_progress(f"kept view {len(selector.kept)}/{n_views}, image coverage {image_coverage(selector.kept, size):.0%}")
        elif time.monotonic() - last_msg > 3:
            last_msg = time.monotonic()
            on_progress("board not found" if d is None else "move/tilt the board to a new position")
    if selector is None or size is None:
        raise RuntimeError("no frames received")
    return selector.kept, size


def detections_from_images(paths: list[Path], board: Checkerboard) -> tuple[list[np.ndarray], tuple[int, int]]:
    dets, size = [], None
    for p in paths:
        img = cv2.imread(str(p))
        if img is None:
            continue
        s = (img.shape[1], img.shape[0])
        if size is not None and s != size:
            raise ValueError(f"{p}: image size {s} differs from {size}; calibrate one resolution at a time")
        size = s
        d = board.detect(img)
        if d is not None:
            dets.append(d)
        else:
            log.info("no board in %s", p)
    if size is None:
        raise ValueError("no readable images")
    return dets, size
