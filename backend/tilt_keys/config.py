"""All tunables for tilt-to-keys live here. The logic modules take values from
this dataclass and contain no magic numbers of their own."""

from __future__ import annotations

import json
import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path


@dataclass(frozen=True)
class KeyBindings:
    forward: str = "w"  # +forward_deg (top leans away from user)
    back: str = "s"  # -forward_deg
    left: str = "a"  # -right_deg
    right: str = "d"  # +right_deg


@dataclass(frozen=True)
class TiltKeyConfig:
    # Hysteresis (degrees, after calibration/inversion/filtering).
    on_threshold_deg: float = 15.0
    off_threshold_deg: float = 10.0

    keys: KeyBindings = field(default_factory=KeyBindings)
    invert_forward: bool = False
    invert_right: bool = False

    # One Euro filter (Casiez et al. 2012). Cutoffs in Hz, beta in 1/deg.
    filter_enabled: bool = True
    filter_min_cutoff_hz: float = 1.0
    filter_beta: float = 0.05
    filter_d_cutoff_hz: float = 1.0

    # Safety: release all keys if no tilt_update arrives within this window.
    stale_timeout_ms: int = 200
    watchdog_period_ms: int = 20

    # Neutral calibration.
    calibration_duration_ms: int = 2000
    calibration_min_samples: int = 10
    calibration_min_valid_fraction: float = 0.8
    calibration_max_std_deg: float = 1.5
    calibration_max_range_deg: float = 5.0

    def __post_init__(self) -> None:
        if not 0 <= self.off_threshold_deg < self.on_threshold_deg:
            raise ValueError(
                f"need 0 <= off_threshold_deg ({self.off_threshold_deg}) < on_threshold_deg ({self.on_threshold_deg})"
            )
        bound = [self.keys.forward, self.keys.back, self.keys.left, self.keys.right]
        if len(set(bound)) != len(bound):
            raise ValueError(f"key bindings must be distinct, got {bound}")
        for name in ("stale_timeout_ms", "watchdog_period_ms", "calibration_min_samples"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be > 0")
        if self.calibration_duration_ms < 0:
            raise ValueError("calibration_duration_ms must be >= 0 (0 disables calibration)")
        if self.filter_min_cutoff_hz <= 0 or self.filter_d_cutoff_hz <= 0 or self.filter_beta < 0:
            raise ValueError("filter cutoffs must be > 0 and beta >= 0")

    @classmethod
    def from_dict(cls, data: dict) -> "TiltKeyConfig":
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"unknown config keys: {sorted(unknown)}")
        data = dict(data)
        if "keys" in data:
            data["keys"] = KeyBindings(**data["keys"])
        return cls(**data)

    @classmethod
    def from_file(cls, path: str | Path) -> "TiltKeyConfig":
        path = Path(path)
        if path.suffix == ".toml":
            data = tomllib.loads(path.read_text())
        elif path.suffix == ".json":
            data = json.loads(path.read_text())
        else:
            raise ValueError(f"config must be .toml or .json, got {path}")
        return cls.from_dict(data)

    def to_dict(self) -> dict:
        return asdict(self)
