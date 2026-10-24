"""Synthetic camera fixtures with exact ground truth.

A small ray caster renders the tabletop, a checkerboard and moving spheres through cameras with
known intrinsics, distortion and poses (based on the rig design). Used by the tests and by
`python -m calibration synth-fixtures`, which writes clips that agents 2 and 3 can use without
any hardware. Everything rendered here is labelled synthetic: it validates the pipeline, not
real-world accuracy.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from camera.rig import RigConfig, load_rig

from .board import R_WORLD_FROM_BOARD, Checkerboard
from .extrinsics import world_from_board
from .geometry import undistort_points_cv
from .models import CameraCalibration, CameraExtrinsics, CameraIntrinsics, RigCalibration


@dataclass
class Sphere:
    center: np.ndarray
    radius: float
    color_bgr: tuple[int, int, int] = (40, 90, 230)


@dataclass
class Scene:
    board: Checkerboard | None = None
    R_world_from_board: np.ndarray = field(default_factory=lambda: R_WORLD_FROM_BOARD.copy())
    t_world_from_board: np.ndarray = field(default_factory=lambda: np.zeros(3))
    board_margin_squares: float = 0.6
    table: bool = True
    spheres: list[Sphere] = field(default_factory=list)
    background: int = 90


def _table_texture(seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = rng.normal(0, 1, (256, 256)).astype(np.float32)
    t = cv2.GaussianBlur(t, (0, 0), 2.0) * 6 + cv2.GaussianBlur(rng.normal(0, 1, (256, 256)).astype(np.float32), (0, 0), 9) * 25
    base = np.array([120, 160, 195], np.float32)  # warm wood tone, BGR
    return np.clip(base[None, None, :] + t[..., None], 0, 255).astype(np.uint8)


_TEX = _table_texture()
_RAY_CACHE: dict = {}


def _camera_rays(cam: CameraCalibration, ss: int) -> np.ndarray:
    """Normalised (undistorted) ray directions in the camera frame for every supersample."""
    intr = cam.intrinsics
    key = (intr.image_width, intr.image_height, ss, intr.K.tobytes(), intr.dist.tobytes())
    if key not in _RAY_CACHE:
        w, h = intr.image_width, intr.image_height
        off = (np.arange(ss) + 0.5) / ss - 0.5
        us = (np.arange(w)[:, None] + off[None, :]).ravel()
        vs = (np.arange(h)[:, None] + off[None, :]).ravel()
        U, V = np.meshgrid(us, vs)
        pts = np.stack([U.ravel(), V.ravel()], axis=1).reshape(-1, 1, 2)
        n = undistort_points_cv(pts, intr.K, intr.dist)
        if len(_RAY_CACHE) >= 6:
            _RAY_CACHE.pop(next(iter(_RAY_CACHE)))
        _RAY_CACHE[key] = np.concatenate([n, np.ones((n.shape[0], 1))], axis=1)
    return _RAY_CACHE[key]


def render(cam: CameraCalibration, scene: Scene, ss: int = 2) -> np.ndarray:
    """BGR uint8 image of the scene as seen by `cam` (with its lens distortion)."""
    e = cam.extrinsics
    if e is None:
        raise ValueError("render needs extrinsics")
    w, h = cam.intrinsics.image_width, cam.intrinsics.image_height
    rays = _camera_rays(cam, ss)
    D = rays @ e.R_camera_to_world.T
    C = e.camera_center_world_m
    n = D.shape[0]
    t_best = np.full(n, np.inf)
    color = np.full((n, 3), scene.background, np.float32)

    if scene.table:
        with np.errstate(divide="ignore", invalid="ignore"):
            t = -C[2] / D[:, 2]
        hit = (t > 0) & np.isfinite(t)
        P = C + t[hit, None] * D[hit]
        tx = (np.floor(P[:, 0] / 0.002).astype(int)) % _TEX.shape[1]
        ty = (np.floor(P[:, 1] / 0.002).astype(int)) % _TEX.shape[0]
        idx = np.flatnonzero(hit)
        t_best[idx] = t[hit]
        color[idx] = _TEX[ty, tx]

    if scene.board is not None:
        b = scene.board
        R, tb = scene.R_world_from_board, scene.t_world_from_board
        nrm = R[:, 2]
        denom = D @ nrm
        with np.errstate(divide="ignore", invalid="ignore"):
            t = ((tb - C) @ nrm) / denom
        t = t - 1e-6  # the board sits on top of a coplanar table
        ok = (t > 0) & np.isfinite(t) & (t <= t_best + 1e-5)
        idx = np.flatnonzero(ok)
        Pb = (C + t[idx, None] * D[idx] - tb) @ R  # world -> board coordinates
        s = b.square_size_m
        m = scene.board_margin_squares * s
        on_paper = (Pb[:, 0] >= -s - m) & (Pb[:, 0] <= b.cols * s + m) & (Pb[:, 1] >= -s - m) & (Pb[:, 1] <= b.rows * s + m)
        idx, Pb = idx[on_paper], Pb[on_paper]
        val = np.full(len(idx), 235.0, np.float32)
        sq = b.inside_squares(Pb[:, 0], Pb[:, 1])
        val[sq & b.square_is_black(Pb[:, 0], Pb[:, 1])] = 25.0
        t_best[idx] = t[idx]
        color[idx] = val[:, None]

    light = np.array([0.3, -0.4, 0.86])
    light /= np.linalg.norm(light)
    for sp in scene.spheres:
        oc = C - sp.center
        bq = D @ oc / np.sum(D * D, axis=1)
        cq = (oc @ oc - sp.radius**2) / np.sum(D * D, axis=1)
        disc = bq**2 - cq
        hit = disc >= 0
        t = np.full(n, np.inf)
        t[hit] = -bq[hit] - np.sqrt(disc[hit])
        ok = (t > 0) & (t < t_best)
        idx = np.flatnonzero(ok)
        P = C + t[idx, None] * D[idx]
        nn = (P - sp.center) / sp.radius
        shade = 0.25 + 0.75 * np.clip(nn @ light, 0, 1)
        t_best[idx] = t[idx]
        color[idx] = np.asarray(sp.color_bgr, np.float32)[None, :] * shade[:, None]

    img = color.reshape(h, ss, w, ss, 3).mean(axis=(1, 3))
    return np.clip(img + 0.5, 0, 255).astype(np.uint8)


# ---- ground-truth rig ----------------------------------------------------------------------

TRUE_DIST = np.array([-0.06, 0.09, 0.0004, -0.0003, 0.0])


def ground_truth_rig(rig: RigConfig | None = None, size: tuple[int, int] = (1280, 720), seed: int = 0) -> RigCalibration:
    """'True' calibration for synthetic tests: nominal design poses perturbed like a real build."""
    rig = rig or load_rig()
    rng = np.random.default_rng(seed)
    cams = {}
    for spec in rig.cameras:
        K = spec.nominal_K.copy()
        K[0, 0] *= 1 + rng.uniform(-0.03, 0.03)
        K[1, 1] = K[0, 0] * (1 + rng.uniform(-0.002, 0.002))
        K[0, 2] += rng.uniform(-8, 8)
        K[1, 2] += rng.uniform(-6, 6)
        intr = CameraIntrinsics(spec.width, spec.height, K, TRUE_DIST.copy(), method="synthetic_ground_truth")
        if (spec.width, spec.height) != size:
            intr = intr.scaled(*size)
        dR, _ = cv2.Rodrigues(rng.normal(0, np.radians(1.5), 3))
        R = dR @ spec.R_world_to_camera
        C = spec.lens_position_m + rng.normal(0, 0.01, 3)
        cams[spec.id] = CameraCalibration(spec.id, intr, CameraExtrinsics(R, -R @ C, method="synthetic_ground_truth"))
    return RigCalibration(cams, rig_name=rig.name + "_synthetic", notes=["SYNTHETIC ground truth, not a real calibration"])


def board_scene(board: Checkerboard, board_height_m: float = 0.0) -> Scene:
    R, t = world_from_board(board, board_height_m)
    return Scene(board=board, R_world_from_board=R, t_world_from_board=t)


def intrinsics_views(intr: CameraIntrinsics, board: Checkerboard, n: int, seed: int = 1, ss: int = 2) -> list[np.ndarray]:
    """Images of the board held at varied poses in front of a camera (no table)."""
    rng = np.random.default_rng(seed)
    cam = CameraCalibration("view", intr, CameraExtrinsics(np.eye(3), np.zeros(3)))
    obj = board.object_points()
    w, h = intr.image_width, intr.image_height
    images: list[np.ndarray] = []
    tries = 0
    while len(images) < n and tries < 50 * n:
        tries += 1
        dist = rng.uniform(0.3, 0.6)
        rvec = np.array([rng.uniform(-0.6, 0.6), rng.uniform(-0.6, 0.6), rng.uniform(-0.4, 0.4)])
        R_cb, _ = cv2.Rodrigues(rvec)
        R_cb = R_cb @ np.diag([1.0, 1.0, 1.0])
        center_dir = np.array([rng.uniform(-0.35, 0.35), rng.uniform(-0.2, 0.2), 1.0])
        t = center_dir / np.linalg.norm(center_dir) * dist - R_cb @ board.grid_center()
        if (R_cb[:, 2] @ (R_cb @ board.grid_center() + t)) < 0:
            continue  # looking at the back of the board: we want +z_board pointing away from the camera
        px, _ = cv2.projectPoints(obj, cv2.Rodrigues(R_cb)[0], t, intr.K, intr.dist)
        px = px.reshape(-1, 2)
        margin = 0.06 * w
        if px[:, 0].min() < margin or px[:, 0].max() > w - margin or px[:, 1].min() < margin or px[:, 1].max() > h - margin:
            continue
        scene = Scene(board=board, R_world_from_board=R_cb, t_world_from_board=t, table=False, background=110)
        images.append(render(cam, scene, ss))
    return images


def ball_trajectory(t_s: np.ndarray) -> np.ndarray:
    """Ground-truth 3D path of the synthetic ball (metres): moves in X, Y and Z."""
    return np.stack([0.12 * np.sin(2 * np.pi * t_s / 4.0),
                     0.06 * np.sin(2 * np.pi * t_s / 2.0),
                     0.06 + 0.035 * np.sin(2 * np.pi * t_s / 3.0)], axis=1)


def write_fixtures(out: Path, seconds: float = 4.0, fps: float = 15.0, clip_size: tuple[int, int] = (640, 360),
                   offsets_ms: dict[str, float] | None = None, board: Checkerboard | None = None) -> dict:
    """Write a complete offline fixture set (see the README written next to it)."""
    out.mkdir(parents=True, exist_ok=True)
    board = board or Checkerboard()
    rig = load_rig()
    offsets_ms = offsets_ms or {"cam_1": 0.0, "cam_2": 7.0, "cam_3": -11.0}
    truth_full = ground_truth_rig(rig)
    truth_full.save(out / "ground_truth_calibration_1280x720.json")
    truth = ground_truth_rig(rig, clip_size)
    truth.notes.append(f"intrinsics scaled to the {clip_size[0]}x{clip_size[1]} clips")
    truth.save(out / f"ground_truth_calibration_{clip_size[0]}x{clip_size[1]}.json")

    scene = board_scene(board)
    (out / "extrinsics_board").mkdir(exist_ok=True)
    (out / "intrinsics_1280x720").mkdir(exist_ok=True)
    for cid, cam in truth_full.cameras.items():
        cv2.imwrite(str(out / "extrinsics_board" / f"{cid}.png"), render(cam, scene))
        cam.intrinsics.save(out / "intrinsics_1280x720" / f"intrinsics_{cid}.json", cid)

    n = int(round(seconds * fps))
    t_true = np.arange(n) / fps
    path = ball_trajectory(t_true)
    for cid, cam in truth.cameras.items():
        vw = cv2.VideoWriter(str(out / f"{cid}.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), fps, clip_size)
        for p in path:
            vw.write(render(cam, Scene(spheres=[Sphere(p, 0.03)]), ss=2))
        vw.release()
        (out / f"{cid}.json").write_text(json.dumps({
            "camera_id": cid, "fps": fps, "frames": n,
            "capture_offset_ms": offsets_ms.get(cid, 0.0),
            "note": "SYNTHETIC: reported capture time = true time + capture_offset_ms (simulated latency mismatch)",
        }, indent=1))
    (out / "ball_trajectory.json").write_text(json.dumps({
        "note": "SYNTHETIC ground truth: sphere radius 0.03 m; position_m is the sphere centre at true time t_ms "
                "(clip frame i is rendered at t = i / fps)",
        "fps": fps, "radius_m": 0.03,
        "samples": [{"t_ms": round(float(t) * 1000, 3), "position_m": {"x": float(p[0]), "y": float(p[1]), "z": float(p[2])}}
                    for t, p in zip(t_true, path)],
    }, indent=1))
    return {"frames": n, "fps": fps, "offsets_ms": offsets_ms}
