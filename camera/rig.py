"""Rig configuration: which cameras exist, how to open them, and where they nominally sit.

The nominal poses come from the physical frame design (camera/config/rig_c270.json) and are
only a prior: they seed synthetic fixtures, sanity-check calibration results and resolve
checkerboard orientation. Measured geometry always comes from calibration/.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RIG_CONFIG = REPO_ROOT / "camera" / "config" / "rig_c270.json"
WORLD_UP = np.array([0.0, 0.0, 1.0])


@dataclass(frozen=True)
class SourceSpec:
    """How to open one camera. kind: uvc | video | synthetic."""

    kind: str
    unique_id: str | None = None  # macOS AVFoundation uniqueID (encodes the USB port)
    linux_by_path: str | None = None  # /dev/v4l/by-path/... (stable per USB port)
    index: int | None = None  # OpenCV index: last resort, can reorder between boots
    name_contains: str | None = None
    path: str | None = None  # video file for kind == "video"
    loop: bool = True
    realtime: bool = True
    pattern: str | None = None  # synthetic pattern name

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SourceSpec":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass(frozen=True)
class CameraSpec:
    id: str
    role: str
    source: SourceSpec
    width: int
    height: int
    fps: float
    fourcc: str | None
    lens_position_m: np.ndarray = field(repr=False)
    R_world_to_camera: np.ndarray = field(repr=False)  # nominal, OpenCV camera axes
    mount: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def nominal_K(self) -> np.ndarray:
        return nominal_intrinsics(self.width, self.height, self._dfov)

    _dfov: float = 55.0


@dataclass(frozen=True)
class RigConfig:
    name: str
    cameras: tuple[CameraSpec, ...]
    pair_tolerance_ms: float
    calibration_file: Path
    frame: dict[str, Any]
    camera_model: dict[str, Any]
    path: Path | None = None

    def camera(self, cam_id: str) -> CameraSpec:
        for c in self.cameras:
            if c.id == cam_id:
                return c
        raise KeyError(cam_id)

    @property
    def camera_ids(self) -> list[str]:
        return [c.id for c in self.cameras]


def look_rotation(direction: np.ndarray, up: np.ndarray = WORLD_UP) -> np.ndarray:
    """R_world_to_camera for an OpenCV camera (+x right, +y down, +z forward) looking along `direction`.

    Image x stays horizontal. When looking straight down, image x is world +X and image
    "up" points to world +Y (away from the viewer).
    """
    z = np.asarray(direction, float)
    z = z / np.linalg.norm(z)
    x = np.cross(z, up)
    if np.linalg.norm(x) < 1e-6:
        x = np.array([1.0, 0.0, 0.0])
    x = x / np.linalg.norm(x)
    y = np.cross(z, x)
    return np.stack([x, y, z])  # rows = camera axes expressed in world


def nominal_intrinsics(width: int, height: int, diagonal_fov_deg: float) -> np.ndarray:
    f = math.hypot(width, height) / 2 / math.tan(math.radians(diagonal_fov_deg) / 2)
    return np.array([[f, 0, (width - 1) / 2], [0, f, (height - 1) / 2], [0, 0, 1.0]])


def load_rig(path: str | Path = DEFAULT_RIG_CONFIG, overrides: dict[str, dict[str, Any]] | None = None) -> RigConfig:
    """Load a rig config. `overrides` maps camera id -> source fields to replace (e.g. video fixtures)."""
    path = Path(path)
    data = json.loads(path.read_text())
    if data.get("schema") != "phantom.camera_rig":
        raise ValueError(f"{path}: not a phantom.camera_rig file")
    model = data["camera_model"]
    cams = []
    seen: set[str] = set()
    for c in data["cameras"]:
        if c["id"] in seen:
            raise ValueError(f"{path}: duplicate camera id {c['id']}")
        seen.add(c["id"])
        src = dict(c["source"])
        if overrides and c["id"] in overrides:
            src = {**src, **overrides[c["id"]]}
        m = c["mount"]
        lens = np.asarray(m["tube_point_m"], float) + np.asarray(m["lens_offset_from_tube_mm"], float) / 1000
        if c.get("look_at_m") is not None:
            direction = np.asarray(c["look_at_m"], float) - lens
        else:
            direction = np.asarray(c["look_direction"], float)
        cams.append(
            CameraSpec(
                id=c["id"],
                role=c["role"],
                source=SourceSpec.from_dict(src),
                width=int(c.get("image_width", model["image_width"])),
                height=int(c.get("image_height", model["image_height"])),
                fps=float(c.get("fps", model["fps"])),
                fourcc=c.get("fourcc", model.get("fourcc")),
                lens_position_m=lens,
                R_world_to_camera=look_rotation(direction),
                mount=m,
                _dfov=float(model.get("diagonal_fov_deg", 55.0)),
            )
        )
    cal = Path(data.get("calibration_file", "calibration/data/rig_calibration.json"))
    return RigConfig(
        name=data["rig_name"],
        cameras=tuple(cams),
        pair_tolerance_ms=float(data.get("sync", {}).get("pair_tolerance_ms", 20.0)),
        calibration_file=cal if cal.is_absolute() else REPO_ROOT / cal,
        frame=data["frame"],
        camera_model=model,
        path=path,
    )


def ground_coverage_m(spec: CameraSpec, plane_z: float = 0.0) -> tuple[float, float] | None:
    """Approximate width x depth of the table seen by a straight-down camera (None if not looking down)."""
    z_axis = spec.R_world_to_camera[2]
    if z_axis[2] > -0.99:
        return None
    K = spec.nominal_K
    dist = spec.lens_position_m[2] - plane_z
    return spec.width / K[0, 0] * dist, spec.height / K[1, 1] * dist
