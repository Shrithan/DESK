"""Mask statistics -> calibrated, smoothed joystick vector.

Tilt cues (both normalised by the upright apparent radius r0, so they don't depend on zoom):
1. centroid shift: (centroid - neutral anchor) / r0. Seen from above, a tilted can's top
   swings out over its base, so the silhouette's centre moves toward the tilt.
2. shape change: covariance(now)/r0^2 - covariance(neutral)/r0^2. Tilting stretches the
   silhouette along the tilt axis; the positive eigenvector of that difference is the axis,
   sqrt(eigenvalue) its size. The axis has no sign, so it takes the sign of the centroid
   shift (or the previous sign while the shift is ~0).
The fused image vector is rotated (and optionally mirrored) by direction calibration so that
"tilt toward W" is +y, then One Euro filtered.

Phases: 'neutral' (hold upright) -> 'direction' (tilt toward W; optional) -> 'running'.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from tilt_joystick.filters import OneEuro as OneEuroFilter
from tilt_joystick.config import FilterConfig, TiltConfig
from tilt_joystick.features import MaskFeatures


@dataclass
class Direction:
    """Image vector (x right, y DOWN) -> joystick (x right, y up = W)."""
    rotation_deg: float = 0.0
    mirror: bool = False

    def apply(self, dx: float, dy_down: float) -> tuple[float, float]:
        x, y = dx, -dy_down
        t = math.radians(self.rotation_deg)
        x, y = x * math.cos(t) - y * math.sin(t), x * math.sin(t) + y * math.cos(t)
        return (-x if self.mirror else x), y


@dataclass
class JoystickState:
    x: float = 0.0
    y: float = 0.0
    mag: float = 0.0
    valid: bool = False
    status: str = 'neutral'  # neutral | direction | running | holding | lost
    prompt: str = ''
    confidence: float = 0.0
    raw: tuple[float, float] = (0.0, 0.0)
    raw_img: tuple[float, float] = (0.0, 0.0)  # fused tilt in image pixels / r0 (for drawing)


class TiltEstimator:
    def __init__(self, tilt: TiltConfig, filt: FilterConfig, direction: Direction | None = None,
                 calibrate_direction: bool = False) -> None:
        self.cfg, self.fcfg = tilt, filt
        self.direction = direction or Direction()
        self.want_direction = calibrate_direction
        self.direction_done = False
        self.fx = OneEuroFilter(filt.min_cutoff_hz, filt.beta, filt.d_cutoff_hz)
        self.fy = OneEuroFilter(filt.min_cutoff_hz, filt.beta, filt.d_cutoff_hz)
        self.recalibrate()

    # ------------------------------------------------------------- calibration
    def recalibrate(self, direction: bool | None = None) -> None:
        if direction is not None:
            self.want_direction = direction
            self.direction_done = False
        self.phase = 'neutral'
        self.samples: list[MaskFeatures] = []
        self.t0: float | None = None
        self.anchor = None
        self.r0 = self.area0 = None
        self.cov0 = None
        self.dir_samples: list[tuple[float, float]] = []
        self.shape_sign = 1.0
        self.last_good_ms: float | None = None
        self.last = JoystickState(status='neutral', prompt='Hold the can upright and still...')
        self.still_since: float | None = None
        self.prev_raw: tuple[float, float] | None = None
        self.shape_level = 0.0
        self.raw_img = (0.0, 0.0)
        self.wait_upright = False
        self.fx.reset(); self.fy.reset()

    def start_direction_calibration(self) -> None:
        if self.anchor is not None:
            self.direction = Direction()
            self.phase, self.dir_samples, self.t0 = 'direction', [], None

    def _neutral(self, f: MaskFeatures, t_ms: float) -> JoystickState:
        self.samples.append(f)
        if self.t0 is None:
            self.t0 = t_ms
        pts = np.array([[s.cx, s.cy] for s in self.samples])
        r = math.sqrt(np.mean([s.area for s in self.samples]) / math.pi)
        if len(self.samples) >= 10:
            # Real movement shows up as drift between the two halves; allow for what pixel noise alone gives.
            half = len(pts) // 2
            drift = float(np.linalg.norm(pts[:half].mean(axis=0) - pts[half:].mean(axis=0)))
            noise = float(np.linalg.norm(pts.std(axis=0))) * math.sqrt(4 / len(pts))
            if drift > self.cfg.neutral_max_jitter * r + 2.5 * noise or float(np.linalg.norm(pts.std(axis=0))) / r > 0.25:
                self.samples, self.t0 = [f], t_ms  # moved: start the second over
        if t_ms - self.t0 < self.cfg.neutral_s * 1000 or len(self.samples) < 5:
            done = (t_ms - self.t0) / (self.cfg.neutral_s * 1000)
            return JoystickState(status='neutral', prompt=f'Hold the can upright and still... {min(done, 1):.0%}',
                                 confidence=f.confidence)
        self.anchor = pts.mean(axis=0)
        self.area0 = float(np.mean([s.area for s in self.samples]))
        self.r0 = math.sqrt(self.area0 / math.pi)
        self.cov0 = np.mean([s.cov() for s in self.samples], axis=0)
        self.phase = 'direction' if self.want_direction and not self.direction_done else 'running'
        self.t0 = None
        if self.phase == 'direction':
            self.direction = Direction()
        prompt = 'Tilt the can toward W and hold...' if self.phase == 'direction' else 'Ready'
        return JoystickState(status=self.phase, prompt=prompt, valid=False, confidence=f.confidence)

    def _direction(self, raw: tuple[float, float], t_ms: float) -> JoystickState:
        """Step 1: tilt toward W fits the rotation. Step 2: tilt toward D detects a mirrored view."""
        target = 'W' if self.phase == 'direction' else 'D'
        if math.hypot(*raw) < 0.5:  # not tilted far enough yet (raw is in full-scale units)
            self.dir_samples, self.t0 = [], None
            return JoystickState(status=self.phase, prompt=f'Tilt the can toward {target} and hold...')
        self.dir_samples.append(raw)
        self.t0 = self.t0 or t_ms
        if t_ms - self.t0 < 500:
            return JoystickState(status=self.phase, prompt=f'Tilt the can toward {target} and hold... keep it there')
        mx, my = np.mean(self.dir_samples, axis=0)
        self.dir_samples, self.t0 = [], None
        if self.phase == 'direction':
            # rotate so the measured W direction (clockwise angle from up) becomes +y
            self.direction.rotation_deg = (self.direction.rotation_deg + math.degrees(math.atan2(mx, my))) % 360
            self.phase = 'direction_d'
            return JoystickState(status=self.phase, prompt='Now tilt the can toward D and hold...')
        if mx < 0:
            self.direction.mirror = not self.direction.mirror
        self.phase = 'running'
        self.fx.reset(); self.fy.reset()
        self.direction_done = True
        self.wait_upright = True
        return JoystickState(status='running', prompt='Direction saved. Return the can upright.')

    # ----------------------------------------------------------------- per frame
    def raw_vector(self, f: MaskFeatures) -> tuple[float, float] | None:
        """Fused tilt in joystick space (full_scale = 1), or None when the mask is implausible."""
        ratio = f.area / self.area0
        if not self.cfg.area_min_ratio <= ratio <= self.cfg.area_max_ratio:
            return None  # hand over the can, two cans merged, detector glitch
        vc = np.array([f.cx, f.cy]) - self.anchor
        vc /= self.r0
        d = (f.cov() - self.cov0) / (self.r0 ** 2)
        w, v = np.linalg.eigh(d)
        axis, size = v[:, 1], math.sqrt(max(w[1], 0.0))
        self.shape_level = self.cfg.shape_weight * size / self.cfg.full_scale
        dot = float(axis @ vc)
        if abs(dot) > 0.02:
            self.shape_sign = 1.0 if dot > 0 else -1.0
        fused = self.cfg.centroid_weight * vc + self.cfg.shape_weight * size * self.shape_sign * axis
        self.raw_img = (float(fused[0]), float(fused[1]))
        x, y = self.direction.apply(float(fused[0]), float(fused[1]))
        return x / self.cfg.full_scale, y / self.cfg.full_scale

    def update(self, f: MaskFeatures | None, t_ms: float) -> JoystickState:
        if self.phase == 'neutral':
            if f is None:
                return JoystickState(status='neutral', prompt='Put the can in view, upright')
            self.last = self._neutral(f, t_ms)
            return self.last
        raw = self.raw_vector(f) if f is not None else None
        if raw is not None and self.phase == 'running' and self.last.valid:
            if math.hypot(raw[0] - self.last.raw[0], raw[1] - self.last.raw[1]) > self.cfg.max_jump:
                if self.last_good_ms is not None and t_ms - self.last_good_ms < self.cfg.hold_ms:
                    raw = None  # single-frame glitch: treat as a dropout
        if raw is None:
            return self._dropout(t_ms)
        if self.phase in ('direction', 'direction_d'):
            self.last = self._direction(raw, t_ms)
            self.last_good_ms = t_ms
            return self.last
        self.last_good_ms = t_ms
        x, y = self.fx(raw[0], int(t_ms)), self.fy(raw[1], int(t_ms))
        x, y = self._lead(x, y)
        mag = math.hypot(x, y)
        if mag > 1:
            x, y, mag = x / mag, y / mag, 1.0
        self._recenter(f, raw, t_ms)
        if self.wait_upright:
            if mag > 0.2:
                self.last = JoystickState(x=x, y=y, mag=mag, valid=False, status='running', raw=raw,
                                          confidence=f.confidence, prompt='Return the can upright to start')
                return self.last
            self.wait_upright = False
        self.last = JoystickState(x=x, y=y, mag=mag, valid=True, status='running', confidence=f.confidence, raw=raw,
                                  raw_img=self.raw_img)
        return self.last

    def _lead(self, x: float, y: float) -> tuple[float, float]:
        """Extrapolate along the filtered velocity by lead_ms. Never past the centre: on a snap back
        to upright the prediction stops at zero instead of overshooting into the opposite key."""
        lead = self.cfg.lead_ms / 1000
        if lead <= 0:
            return x, y
        px, py = x + self.fx.velocity * lead, y + self.fy.velocity * lead
        if px * x + py * y < 0:
            return 0.0, 0.0
        return px, py

    def _dropout(self, t_ms: float) -> JoystickState:
        if self.phase == 'running' and self.last.valid and self.last_good_ms is not None \
                and t_ms - self.last_good_ms <= self.cfg.hold_ms:
            s = self.last
            return JoystickState(x=s.x, y=s.y, mag=s.mag, valid=True, status='holding', raw=s.raw, raw_img=s.raw_img,
                                 confidence=0.0, prompt='')
        self.fx.reset(); self.fy.reset()
        self.still_since = None
        state = JoystickState(status='lost' if self.phase == 'running' else self.phase,
                              prompt='Can lost: keys released' if self.phase == 'running' else self.last.prompt)
        if self.phase == 'running':
            self.last = state
        return state

    def _recenter(self, f: MaskFeatures, raw: tuple[float, float], t_ms: float) -> None:
        """Slowly move the neutral anchor to the can's resting pose (it slid, or the camera settled).

        Only while the silhouette is upright-shaped (no elongation), the reading is small and
        nothing is moving, so a held tilt is never re-centred away."""
        moving = self.prev_raw is not None and math.hypot(raw[0] - self.prev_raw[0], raw[1] - self.prev_raw[1]) > 0.03
        self.prev_raw = raw
        if self.shape_level > self.cfg.recenter_mag or math.hypot(*raw) > self.cfg.recenter_max or moving:
            self.still_since = None
            return
        if self.still_since is None:
            self.still_since = self._last_recenter = t_ms
            return
        dt = (t_ms - self._last_recenter) / 1000
        self._last_recenter = t_ms
        if t_ms - self.still_since < self.cfg.recenter_after_s * 1000:
            return
        k = min(1.0, self.cfg.recenter_rate * dt)
        self.anchor = self.anchor + k * (np.array([f.cx, f.cy]) - self.anchor)
        self.cov0 = self.cov0 + k * (f.cov() - self.cov0)
