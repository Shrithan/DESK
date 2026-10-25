"""Joystick vector -> set of held keys: 8-way sectors with magnitude and angle hysteresis.

Pure state machine, no I/O. Angles are clockwise from "up" (W): 0 = W, 45 = W+D, 90 = D ...
Key edges (old key up before new key down) are produced by backend.tilt_keys.output.EdgeTriggeredOutput.
"""
from __future__ import annotations

import math

from tilt_joystick.config import KeyConfig


def sector_keys(cfg: KeyConfig) -> list[frozenset[str]]:
    u, r, d, l = cfg.up, cfg.right, cfg.down, cfg.left
    if cfg.diagonals:
        return [frozenset(k) for k in ({u}, {u, r}, {r}, {d, r}, {d}, {d, l}, {l}, {u, l})]
    return [frozenset({u}), frozenset({r}), frozenset({d}), frozenset({l})]


def angle_deg(x: float, y: float) -> float:
    return math.degrees(math.atan2(x, y)) % 360.0


def angular_distance(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


class SectorKeyMapper:
    def __init__(self, cfg: KeyConfig) -> None:
        if not 0 <= cfg.release < cfg.press <= 1:
            raise ValueError('need 0 <= release < press <= 1')
        self.cfg = cfg
        self.keys = sector_keys(cfg)
        self.width = 360.0 / len(self.keys)
        self.sector: int | None = None

    def nearest(self, angle: float) -> int:
        return int(round(angle / self.width)) % len(self.keys)

    def update(self, x: float, y: float, valid: bool = True) -> frozenset[str]:
        """Return the keys that should be held for joystick (x right, y up = W)."""
        mag = math.hypot(x, y)
        if not valid or not math.isfinite(mag):
            self.sector = None
            return frozenset()
        if self.sector is None:
            if mag <= self.cfg.press:
                return frozenset()
            self.sector = self.nearest(angle_deg(x, y))
        elif mag < self.cfg.release:
            self.sector = None
            return frozenset()
        else:
            angle = angle_deg(x, y)
            if angular_distance(angle, self.sector * self.width) > self.width / 2 + self.cfg.sector_hysteresis_deg:
                self.sector = self.nearest(angle)
        return self.keys[self.sector]

    def reset(self) -> None:
        self.sector = None
