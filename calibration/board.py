"""Checkerboard target: geometry, detection with a canonical corner order, printable image.

Board layout (default 9 x 6 inner corners = 10 x 7 squares of 20 mm, 200 x 140 mm):
* Board coordinates: inner corner 0 at (0, 0, 0); +x along the 9-corner direction (page
  right), +y along the 6-corner direction (page down), z = 0 on the board, so +z = x cross y
  points INTO the printed face.
* Square (i, j), i = 0..cols, j = 0..rows, spans x in [(i-1)s, i s], y in [(j-1)s, j s] and is
  black when (i + j) is even, so the square diagonally outside corner 0 is black and the one
  outside the last corner is white. That asymmetry fixes the 180 degree ambiguity of
  checkerboard detection: `detect` always returns corner 0 first.
* For extrinsics the page lies face-up on the table in normal reading orientation (labels
  readable from where you stand): board +x = world +X (right), board +y = world -Y (towards
  you), board +z = world -Z. Corner 0 is at the BACK-LEFT. See R_WORLD_FROM_BOARD.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import cv2
import numpy as np


R_WORLD_FROM_BOARD = np.diag([1.0, -1.0, -1.0])


@dataclass(frozen=True)
class Checkerboard:
    cols: int = 9  # inner corners along board x
    rows: int = 6  # inner corners along board y
    square_size_m: float = 0.020  # MEASURE the printed squares and put the real value here

    def __post_init__(self) -> None:
        if (self.cols + 1) % 2 == (self.rows + 1) % 2:
            raise ValueError("use an even x odd number of squares so the board orientation is unambiguous")

    @property
    def pattern_size(self) -> tuple[int, int]:
        return (self.cols, self.rows)

    @property
    def n_corners(self) -> int:
        return self.cols * self.rows

    def object_points(self) -> np.ndarray:
        """(N, 3) corner positions in board coordinates, metres, row-major from corner 0."""
        j, i = np.mgrid[0 : self.rows, 0 : self.cols]
        pts = np.stack([i.ravel(), j.ravel(), np.zeros(self.n_corners)], axis=1)
        return pts.astype(np.float64) * self.square_size_m

    def grid_center(self) -> np.ndarray:
        return np.array([(self.cols - 1) / 2, (self.rows - 1) / 2, 0.0]) * self.square_size_m

    def square_is_black(self, u: np.ndarray, v: np.ndarray) -> np.ndarray:
        """Colour at board coordinates (metres) inside the printed squares."""
        s = self.square_size_m
        i = np.floor(u / s).astype(np.int64) + 1
        j = np.floor(v / s).astype(np.int64) + 1
        return (i + j) % 2 == 0

    def inside_squares(self, u: np.ndarray, v: np.ndarray) -> np.ndarray:
        s = self.square_size_m
        return (u >= -s) & (u <= self.cols * s) & (v >= -s) & (v <= self.rows * s)

    def to_dict(self) -> dict:
        return {**asdict(self), "type": "checkerboard", "squares": [self.cols + 1, self.rows + 1],
                "corner0_outer_square": "black", "placement": "face-up on the table in reading orientation, "
                "corner 0 at back-left; board +x = world +X, board +y = world -Y, board +z = world -Z; "
                "world origin = centre of the inner-corner grid"}

    # ---- detection ---------------------------------------------------------------------
    def detect(self, image: np.ndarray) -> np.ndarray | None:
        """(N, 2) float64 sub-pixel corners in canonical order (corner 0 first), or None."""
        gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        corners = None
        if hasattr(cv2, "findChessboardCornersSB"):
            ok, c = cv2.findChessboardCornersSB(gray, self.pattern_size, flags=cv2.CALIB_CB_NORMALIZE_IMAGE | cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY)
            if ok:
                corners = c.reshape(-1, 2).astype(np.float64)
        if corners is None:
            ok, c = cv2.findChessboardCorners(gray, self.pattern_size, flags=cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE)
            if not ok:
                return None
            c = cv2.cornerSubPix(gray, c, (5, 5), (-1, -1), (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 1e-3))
            corners = c.reshape(-1, 2).astype(np.float64)
        return self.canonicalize(gray, corners)

    def quick_check(self, image: np.ndarray, max_width: int = 640) -> dict:
        """Fast "is the whole board visible?" check for aiming cameras (not for calibration)."""
        gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        scale = min(1.0, max_width / gray.shape[1])
        small = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else gray
        ok, c = cv2.findChessboardCorners(small, self.pattern_size, flags=cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_FAST_CHECK)
        if not ok:
            return {"detected": False}
        c = c.reshape(-1, 2) / scale
        h, w = gray.shape[:2]
        margin = float(min(c[:, 0].min(), c[:, 1].min(), w - c[:, 0].max(), h - c[:, 1].max()))
        return {"detected": True, "bbox_px": [float(c[:, 0].min()), float(c[:, 1].min()), float(c[:, 0].max()), float(c[:, 1].max())],
                "min_margin_px": round(margin, 1), "comfortable": margin > 0.05 * w}

    def canonicalize(self, gray: np.ndarray, corners: np.ndarray) -> np.ndarray | None:
        """Reverse the order if the detector started from the far corner (180 degree flip)."""
        g = corners.reshape(self.rows, self.cols, 2)

        def outer_square_level(c0, cx, cy) -> float | None:
            p = c0 + 0.5 * (c0 - cx) + 0.5 * (c0 - cy)
            x, y = int(round(p[0])), int(round(p[1]))
            r = max(1, int(0.15 * np.linalg.norm(c0 - cx)))
            if not (r <= x < gray.shape[1] - r and r <= y < gray.shape[0] - r):
                return None
            return float(gray[y - r : y + r + 1, x - r : x + r + 1].mean())

        first = outer_square_level(g[0, 0], g[0, 1], g[1, 0])
        last = outer_square_level(g[-1, -1], g[-1, -2], g[-2, -1])
        if first is None or last is None:
            return None  # board too close to the image edge to know its orientation
        return corners if first < last else corners[::-1].copy()

    # ---- printing ----------------------------------------------------------------------
    def render_printable(self, dpi: int = 300, margin_squares: float = 0.6) -> np.ndarray:
        """Grayscale image at `dpi` with labels; print at 100 % ("actual size") and measure."""
        px = self.square_size_m / 0.0254 * dpi
        m = margin_squares * px
        W = int(round((self.cols + 1) * px + 2 * m))
        H = int(round((self.rows + 1) * px + 2 * m + 0.8 * px))
        img = np.full((H, W), 255, np.uint8)
        top = m + 0.8 * px  # space for labels above the squares
        for j in range(self.rows + 1):
            for i in range(self.cols + 1):
                if (i + j) % 2 == 0:
                    x0, y0 = int(round(m + i * px)), int(round(top + j * px))
                    img[y0 : int(round(top + (j + 1) * px)), x0 : int(round(m + (i + 1) * px))] = 0
        f = px / 70
        cv2.putText(img, "BACK edge (away from you)   +X world ->", (int(m), int(0.55 * px)), cv2.FONT_HERSHEY_SIMPLEX, f, 0, max(1, int(f * 2)))
        cv2.putText(img, f"{self.cols}x{self.rows} inner corners, squares {self.square_size_m * 1000:.1f} mm: MEASURE after printing",
                    (int(m), H - int(0.15 * px)), cv2.FONT_HERSHEY_SIMPLEX, f * 0.55, 0, max(1, int(f)))
        return img
