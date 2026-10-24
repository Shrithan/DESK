"""Every threshold and filter parameter for the can-tilt joystick, in one place.

Defaults live here; override any of them in a TOML or JSON file (see tilt_joystick.toml)
with the same section/field names.
"""
from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field, fields, is_dataclass, replace
from pathlib import Path


@dataclass(frozen=True)
class DetectorConfig:
    weights: str = 'outputs/models/desk-yoloe-s.pt'  # prepared by `python -m vision.prepare_model --size s`
    prompts: tuple[str, ...] = ('soda can', 'aluminum can')  # used when the weights accept set_classes
    labels: tuple[str, ...] = ('soda can', 'aluminum can', 'top of a soda can', 'can')  # accepted class names
    fallback_weights: str = 'yolov8s-worldv2.pt'  # YOLO-World boxes when segmentation is unavailable
    confidence: float = 0.15
    image_size: int = 480
    device: str = 'auto'  # auto -> cuda, mps, cpu
    detect_every: int = 1  # run the model every N frames; optical flow carries the mask in between
    tracker: str = 'bytetrack.yaml'


@dataclass(frozen=True)
class TiltConfig:
    neutral_s: float = 1.0  # hold upright this long to calibrate
    neutral_max_jitter: float = 0.04  # centroid std / radius allowed while calibrating
    centroid_weight: float = 1.0  # tilt from centroid shift (fraction of the can radius)
    shape_weight: float = 0.8  # tilt from elongation (major/minor ratio growth)
    full_scale: float = 1.0  # fused tilt (in can radii) for magnitude 1.0: ~22 deg seen from above, press ~7 deg
    area_min_ratio: float = 0.55  # mask smaller than this x neutral area = occluded (hand), low confidence
    area_max_ratio: float = 2.2
    max_jump: float = 0.9  # joystick units per frame; bigger jumps are rejected as glitches
    recenter_after_s: float = 1.0  # upright-shaped & still this long -> slowly re-centre the anchor
    recenter_mag: float = 0.12  # shape cue (joystick units) below this counts as upright
    recenter_max: float = 0.5  # never re-centre while the joystick reads more than this
    recenter_rate: float = 0.5  # fraction of the offset removed per second while re-centring
    hold_ms: float = 250  # keep the last value through a dropout this long, then release everything


@dataclass(frozen=True)
class FilterConfig:
    min_cutoff_hz: float = 1.5
    beta: float = 4.0
    d_cutoff_hz: float = 1.0


@dataclass(frozen=True)
class KeyConfig:
    press: float = 0.35  # magnitude to start pressing
    release: float = 0.25  # magnitude to release everything
    sector_hysteresis_deg: float = 10.0  # stay in the current 45 deg sector until this far past its edge
    diagonals: bool = True  # 8-way; False = 4-way
    up: str = 'w'
    left: str = 'a'
    down: str = 's'
    right: str = 'd'
    pause_hotkey: str = 'f8'  # global pynput hotkey (window hotkey is space)


@dataclass(frozen=True)
class Config:
    detector: DetectorConfig = field(default_factory=DetectorConfig)
    tilt: TiltConfig = field(default_factory=TiltConfig)
    filter: FilterConfig = field(default_factory=FilterConfig)
    keys: KeyConfig = field(default_factory=KeyConfig)
    latency_budget_ms: float = 90.0


def _merge(obj, data: dict):
    known = {f.name: f for f in fields(obj)}
    changes = {}
    for key, value in data.items():
        if key not in known:
            raise ValueError(f'unknown config field {key!r} in {type(obj).__name__}')
        current = getattr(obj, key)
        if is_dataclass(current):
            changes[key] = _merge(current, value)
        else:
            changes[key] = tuple(value) if isinstance(current, tuple) else type(current)(value)
    return replace(obj, **changes)


def load_config(path: str | Path | None = None) -> Config:
    if path is None:
        return Config()
    path = Path(path)
    data = tomllib.loads(path.read_text()) if path.suffix == '.toml' else json.loads(path.read_text())
    return _merge(Config(), data)
