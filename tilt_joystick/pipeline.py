"""Features -> estimator -> sector keys -> edge-triggered key output, with all the safety rules.

Shared by the live camera loop and by replay, so a recording reproduces the exact key events.
"""
from __future__ import annotations

import json
import threading
from dataclasses import replace
from pathlib import Path

from backend.tilt_keys.output import EdgeTriggeredOutput
from tilt_joystick.bus import BusKeyBackend, EventBus
from tilt_joystick.config import Config, KeyConfig
from tilt_joystick.estimator import Direction, JoystickState, TiltEstimator
from tilt_joystick.features import MaskFeatures
from tilt_joystick.keymap import SectorKeyMapper

DIRECTION_FILE = Path('outputs/tilt_joystick_direction.json')


def load_direction(path: Path = DIRECTION_FILE) -> Direction | None:
    try:
        data = json.loads(path.read_text())
        return Direction(float(data['rotation_deg']), bool(data['mirror']))
    except (OSError, ValueError, KeyError):
        return None


def save_direction(direction: Direction, path: Path = DIRECTION_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'rotation_deg': direction.rotation_deg, 'mirror': direction.mirror}))


class TiltPipeline:
    def __init__(self, config: Config, backend, bus: EventBus | None = None,
                 direction: Direction | None = None, calibrate_direction: bool = False) -> None:
        self.config = config
        self.bus = bus or EventBus()
        self.estimator = TiltEstimator(config.tilt, config.filter, direction, calibrate_direction)
        self.mapper = SectorKeyMapper(config.keys)
        self.output = EdgeTriggeredOutput(BusKeyBackend(backend, self.bus))
        self.backend = backend
        self.paused = False
        # Per-axis key gain (x = left/right, y = forward/back). Default 1.0 leaves behaviour unchanged.
        # The agent control API uses it for a separate left/right trigger and for direction inversion
        # (negative gain). It only affects which keys are held, never the published joystick vector.
        self.gain_x = 1.0
        self.gain_y = 1.0
        self.state = JoystickState()
        self.closed = False
        self.lock = threading.RLock()  # camera thread steps; UI thread pauses/recalibrates

    @property
    def held(self) -> frozenset[str]:
        return self.output.held

    def step(self, features: MaskFeatures | None, t_ms: float) -> JoystickState:
        with self.lock:
            was = self.estimator.phase
            state = self.estimator.update(features, t_ms)
            if was.startswith('direction') and self.estimator.phase == 'running':
                save_direction(self.estimator.direction)
            active = state.valid and not self.paused and state.status in ('running', 'holding')
            keys = self.mapper.update(state.x * self.gain_x, state.y * self.gain_y, active)
            self.output.set_held(keys)
            self.state = state
            self.bus.publish('joystick', {'x': round(state.x, 4), 'y': round(state.y, 4), 'mag': round(state.mag, 4),
                                          'status': state.status, 'valid': state.valid, 't_ms': round(t_ms, 1)})
            return state

    def set_paused(self, paused: bool) -> None:
        with self.lock:
            self.paused = paused
            if paused:
                self.mapper.reset()
                self.output.release_all()
            self.bus.publish('status', {'paused': paused})

    def recalibrate(self, direction: bool = False) -> None:
        with self.lock:
            self.mapper.reset()
            self.output.release_all()
            self.estimator.recalibrate(direction=direction or None)
            if direction:
                self.estimator.want_direction = True

    def apply_keys(self, keys: KeyConfig, gain_x: float = 1.0, gain_y: float = 1.0, full_scale: float | None = None) -> None:
        """Swap key settings at runtime (agent control API). Keys are released first so a new
        binding or threshold can never leave a stale key held."""
        mapper = SectorKeyMapper(keys)  # validates press/release before anything changes
        with self.lock:
            self.mapper.reset()
            self.output.release_all()
            self.config = replace(self.config, keys=keys)
            self.mapper = mapper
            self.gain_x, self.gain_y = gain_x, gain_y
            if full_scale is not None and full_scale != self.estimator.cfg.full_scale:
                self.estimator.cfg = replace(self.estimator.cfg, full_scale=full_scale)
                self.config = replace(self.config, tilt=self.estimator.cfg)

    def release_all(self) -> None:
        with self.lock:
            self.mapper.reset()
            self.output.release_all()

    def close(self) -> None:
        with self.lock:
            if self.closed:
                return
            self.closed = True
            try:
                self.release_all()
            finally:
                self.backend.close()


def replay(path: str | Path, pipeline: TiltPipeline) -> list[tuple[float, frozenset[str], JoystickState]]:
    """Feed a recorded features JSONL file through the pipeline; returns (t_ms, held, state) per frame."""
    out = []
    try:
        for line in Path(path).read_text().splitlines():
            row = json.loads(line)
            f = MaskFeatures(**row['f']) if row.get('f') else None
            state = pipeline.step(f, row['t_ms'])
            out.append((row['t_ms'], pipeline.held, state))
    finally:
        pipeline.close()
    return out


