"""Versioned calibration data: per-camera intrinsics and the multi-camera rig calibration.

Conventions (also written into every saved file):
* World frame: right-handed, metres, +X right, +Y away from the viewer, +Z up. Origin = the
  centre of the checkerboard's inner-corner grid lying flat on the table during extrinsics.
* Camera frame: OpenCV, +X image right, +Y image down, +Z along the optical axis, metres.
* Extrinsics: x_cam = R_world_to_camera @ x_world + t_world_to_camera_m.
  camera_center_world_m = -R_world_to_camera.T @ t_world_to_camera_m.
* Pixels: OpenCV, (0, 0) is the centre of the top-left pixel, u right, v down.
* Distortion: OpenCV radial-tangential [k1, k2, p1, p2, k3] applied to normalised coordinates.
* Metric scale comes from the measured checkerboard square size.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

RIG_SCHEMA = "phantom.rig_calibration"
INTRINSICS_SCHEMA = "phantom.camera_intrinsics"
SCHEMA_VERSION = "1.0.0"

CONVENTIONS = {
    "world_frame": "right-handed, metres, +X right, +Y away from the viewer, +Z up; origin = centre of the "
                   "checkerboard inner-corner grid lying flat on the table during extrinsic calibration",
    "camera_frame": "OpenCV: +X image right, +Y image down, +Z optical axis (forward), metres",
    "extrinsics": "x_cam = R_world_to_camera @ x_world + t_world_to_camera_m; "
                  "camera_center_world_m = -R_world_to_camera^T @ t_world_to_camera_m",
    "pixels": "OpenCV: (0,0) = centre of top-left pixel, u right, v down",
    "distortion_model": "opencv_radtan [k1, k2, p1, p2, k3] on normalised coordinates",
    "units": "metres for all positions/translations; pixels for image quantities",
}


class CalibrationValidationError(ValueError):
    pass


def _arr(x: Any, shape: tuple[int, ...], name: str) -> np.ndarray:
    a = np.asarray(x, dtype=float)
    if a.shape != shape:
        raise CalibrationValidationError(f"{name}: expected shape {shape}, got {a.shape}")
    if not np.all(np.isfinite(a)):
        raise CalibrationValidationError(f"{name}: non-finite values")
    return a


@dataclass
class CameraIntrinsics:
    image_width: int
    image_height: int
    K: np.ndarray  # 3x3
    dist: np.ndarray  # (5,) k1 k2 p1 p2 k3
    rms_reprojection_px: float | None = None
    num_views: int | None = None
    per_view_rms_px: list[float] | None = None
    method: str = "opencv_calibrateCamera_checkerboard"
    calibrated_unix_ms: int | None = None

    def validate(self, name: str = "intrinsics") -> None:
        if self.image_width <= 0 or self.image_height <= 0:
            raise CalibrationValidationError(f"{name}: bad image size")
        K = _arr(self.K, (3, 3), f"{name}.K")
        _arr(self.dist, (5,), f"{name}.dist")
        fx, fy, cx, cy = K[0, 0], K[1, 1], K[0, 2], K[1, 2]
        if fx <= 0 or fy <= 0:
            raise CalibrationValidationError(f"{name}: focal lengths must be positive")
        if not (0 <= cx < self.image_width and 0 <= cy < self.image_height):
            raise CalibrationValidationError(f"{name}: principal point outside the image")
        if abs(K[1, 0]) + abs(K[2, 0]) + abs(K[2, 1]) > 1e-9 or abs(K[2, 2] - 1) > 1e-9:
            raise CalibrationValidationError(f"{name}: K must be upper-triangular with K[2,2] = 1")

    def scaled(self, width: int, height: int) -> "CameraIntrinsics":
        """Intrinsics for a resized image (same field of view, e.g. 1280x720 -> 640x360)."""
        sx, sy = width / self.image_width, height / self.image_height
        K = self.K.copy()
        K[0, 0] *= sx
        K[0, 2] = (K[0, 2] + 0.5) * sx - 0.5
        K[1, 1] *= sy
        K[1, 2] = (K[1, 2] + 0.5) * sy - 0.5
        return CameraIntrinsics(width, height, K, self.dist.copy(), self.rms_reprojection_px, self.num_views,
                                self.per_view_rms_px, self.method + f"+scaled_from_{self.image_width}x{self.image_height}",
                                self.calibrated_unix_ms)

    def to_dict(self) -> dict:
        return {
            "image_size": {"width": self.image_width, "height": self.image_height},
            "K": np.asarray(self.K).tolist(),
            "distortion_model": "opencv_radtan",
            "dist": np.asarray(self.dist).tolist(),
            "rms_reprojection_px": self.rms_reprojection_px,
            "num_views": self.num_views,
            "per_view_rms_px": self.per_view_rms_px,
            "method": self.method,
            "calibrated_unix_ms": self.calibrated_unix_ms,
        }

    @classmethod
    def from_dict(cls, d: dict, name: str = "intrinsics") -> "CameraIntrinsics":
        if d.get("distortion_model", "opencv_radtan") != "opencv_radtan":
            raise CalibrationValidationError(f"{name}: unsupported distortion model {d.get('distortion_model')}")
        obj = cls(
            image_width=int(d["image_size"]["width"]),
            image_height=int(d["image_size"]["height"]),
            K=_arr(d["K"], (3, 3), f"{name}.K"),
            dist=_arr(d["dist"], (5,), f"{name}.dist"),
            rms_reprojection_px=d.get("rms_reprojection_px"),
            num_views=d.get("num_views"),
            per_view_rms_px=d.get("per_view_rms_px"),
            method=d.get("method", "unknown"),
            calibrated_unix_ms=d.get("calibrated_unix_ms"),
        )
        obj.validate(name)
        return obj

    def save(self, path: str | Path, camera_id: str) -> None:
        self.validate(camera_id)
        doc = {"schema": INTRINSICS_SCHEMA, "schema_version": SCHEMA_VERSION, "camera_id": camera_id,
               "conventions": {k: CONVENTIONS[k] for k in ("pixels", "distortion_model")}, **self.to_dict()}
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(doc, indent=2))

    @classmethod
    def load(cls, path: str | Path) -> tuple[str, "CameraIntrinsics"]:
        d = json.loads(Path(path).read_text())
        if d.get("schema") != INTRINSICS_SCHEMA:
            raise CalibrationValidationError(f"{path}: not a {INTRINSICS_SCHEMA} file")
        _check_version(d, path)
        return d["camera_id"], cls.from_dict(d, d["camera_id"])


@dataclass
class CameraExtrinsics:
    R_world_to_camera: np.ndarray  # 3x3
    t_world_to_camera_m: np.ndarray  # (3,)
    rms_reprojection_px: float | None = None
    method: str = "solvePnP_checkerboard_on_table"
    calibrated_unix_ms: int | None = None

    @property
    def R_camera_to_world(self) -> np.ndarray:
        return self.R_world_to_camera.T

    @property
    def camera_center_world_m(self) -> np.ndarray:
        return -self.R_world_to_camera.T @ self.t_world_to_camera_m

    @property
    def T_world_to_camera(self) -> np.ndarray:
        T = np.eye(4)
        T[:3, :3], T[:3, 3] = self.R_world_to_camera, self.t_world_to_camera_m
        return T

    @property
    def optical_axis_world(self) -> np.ndarray:
        return self.R_world_to_camera[2]

    def validate(self, name: str = "extrinsics") -> None:
        R = _arr(self.R_world_to_camera, (3, 3), f"{name}.R_world_to_camera")
        _arr(self.t_world_to_camera_m, (3,), f"{name}.t_world_to_camera_m")
        if not np.allclose(R @ R.T, np.eye(3), atol=1e-6) or abs(np.linalg.det(R) - 1) > 1e-6:
            raise CalibrationValidationError(f"{name}: R_world_to_camera is not a proper rotation")

    def to_dict(self) -> dict:
        return {
            "R_world_to_camera": np.asarray(self.R_world_to_camera).tolist(),
            "t_world_to_camera_m": np.asarray(self.t_world_to_camera_m).tolist(),
            "R_camera_to_world": self.R_camera_to_world.tolist(),
            "camera_center_world_m": self.camera_center_world_m.tolist(),
            "optical_axis_world": self.optical_axis_world.tolist(),
            "rms_reprojection_px": self.rms_reprojection_px,
            "method": self.method,
            "calibrated_unix_ms": self.calibrated_unix_ms,
        }

    @classmethod
    def from_dict(cls, d: dict, name: str = "extrinsics") -> "CameraExtrinsics":
        obj = cls(
            R_world_to_camera=_arr(d["R_world_to_camera"], (3, 3), f"{name}.R_world_to_camera"),
            t_world_to_camera_m=_arr(d["t_world_to_camera_m"], (3,), f"{name}.t_world_to_camera_m"),
            rms_reprojection_px=d.get("rms_reprojection_px"),
            method=d.get("method", "unknown"),
            calibrated_unix_ms=d.get("calibrated_unix_ms"),
        )
        obj.validate(name)
        if "camera_center_world_m" in d and not np.allclose(obj.camera_center_world_m, d["camera_center_world_m"], atol=1e-6):
            raise CalibrationValidationError(f"{name}: camera_center_world_m inconsistent with R/t")
        return obj


@dataclass
class CameraCalibration:
    camera_id: str
    intrinsics: CameraIntrinsics
    extrinsics: CameraExtrinsics | None = None

    @property
    def K(self) -> np.ndarray:
        return self.intrinsics.K

    @property
    def dist(self) -> np.ndarray:
        return self.intrinsics.dist

    def projection_matrix(self) -> np.ndarray:
        """3x4 P = K [R | t] mapping world (metres) to *undistorted* pixels."""
        if self.extrinsics is None:
            raise ValueError(f"{self.camera_id} has no extrinsics")
        e = self.extrinsics
        return self.K @ np.hstack([e.R_world_to_camera, e.t_world_to_camera_m.reshape(3, 1)])

    def to_dict(self) -> dict:
        d = {"camera_id": self.camera_id, "intrinsics": self.intrinsics.to_dict(),
             "extrinsics": None if self.extrinsics is None else self.extrinsics.to_dict()}
        if self.extrinsics is not None:
            d["projection_matrix_undistorted"] = self.projection_matrix().tolist()
        return d


@dataclass
class RigCalibration:
    cameras: dict[str, CameraCalibration]
    calibration_id: str = ""
    created_unix_ms: int = 0
    rig_name: str = ""
    world_reference: dict = field(default_factory=dict)  # board spec + how the origin was set
    validation: dict = field(default_factory=dict)  # cross-camera checks (triangulation RMSE, ...)
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.created_unix_ms:
            self.created_unix_ms = int(time.time() * 1000)

    def validate(self) -> None:
        if not self.cameras:
            raise CalibrationValidationError("rig calibration has no cameras")
        for cid, c in self.cameras.items():
            if c.camera_id != cid:
                raise CalibrationValidationError(f"camera key {cid} != camera_id {c.camera_id}")
            c.intrinsics.validate(f"{cid}.intrinsics")
            if c.extrinsics is not None:
                c.extrinsics.validate(f"{cid}.extrinsics")

    def body_dict(self) -> dict:
        return {
            "schema": RIG_SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "rig_name": self.rig_name,
            "created_unix_ms": self.created_unix_ms,
            "conventions": CONVENTIONS,
            "world_reference": self.world_reference,
            "cameras": {cid: c.to_dict() for cid, c in sorted(self.cameras.items())},
            "validation": self.validation,
            "notes": self.notes,
        }

    def assign_id(self) -> str:
        digest = hashlib.sha256(json.dumps(self.body_dict(), sort_keys=True).encode()).hexdigest()[:8]
        stamp = datetime.fromtimestamp(self.created_unix_ms / 1000, tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.calibration_id = f"{stamp}-{digest}"
        return self.calibration_id

    def to_dict(self) -> dict:
        if not self.calibration_id:
            self.assign_id()
        return {"calibration_id": self.calibration_id, **self.body_dict()}

    def save(self, path: str | Path) -> str:
        self.validate()
        self.assign_id()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(self.to_dict(), indent=2))
        return self.calibration_id

    @classmethod
    def from_dict(cls, d: dict) -> "RigCalibration":
        if d.get("schema") != RIG_SCHEMA:
            raise CalibrationValidationError(f"not a {RIG_SCHEMA} document")
        _check_version(d, "rig calibration")
        cams = {}
        for cid, c in d["cameras"].items():
            cams[cid] = CameraCalibration(
                camera_id=c["camera_id"],
                intrinsics=CameraIntrinsics.from_dict(c["intrinsics"], f"{cid}.intrinsics"),
                extrinsics=None if c.get("extrinsics") is None else CameraExtrinsics.from_dict(c["extrinsics"], f"{cid}.extrinsics"),
            )
        obj = cls(cameras=cams, calibration_id=d.get("calibration_id", ""), created_unix_ms=d.get("created_unix_ms", 0),
                  rig_name=d.get("rig_name", ""), world_reference=d.get("world_reference", {}),
                  validation=d.get("validation", {}), notes=d.get("notes", []))
        obj.validate()
        return obj

    @classmethod
    def load(cls, path: str | Path) -> "RigCalibration":
        return cls.from_dict(json.loads(Path(path).read_text()))


def _check_version(d: dict, where: Any) -> None:
    v = str(d.get("schema_version", ""))
    if v.split(".")[0] != SCHEMA_VERSION.split(".")[0]:
        raise CalibrationValidationError(f"{where}: schema_version {v!r} incompatible with {SCHEMA_VERSION}")
