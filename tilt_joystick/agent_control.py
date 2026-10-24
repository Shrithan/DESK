"""Agent control API for the camera can joystick (the real key path).

The five DESK Fetch.ai agents (Coach, Setup, Tuner, Doctor, Validator) talk to
whatever is pressing keys through one JSON protocol on ws://127.0.0.1:8766/ws/control
(see backend/tilt_keys/control.py). This module serves that same protocol for
``python -m tilt_joystick --control`` so the agents tune the live camera joystick,
not only the simulated player.

Units. The agents think in tilt degrees and per-axis on/off triggers; the joystick
thinks in unit-circle magnitude with one press/release pair and 8-way sectors. The
bridge:

* degrees = joystick units x DEG_PER_UNIT x tilt.full_scale (full push ~22 deg at
  full_scale 1.0, per docs/can_joystick.md). Approximate: it comes from the overhead
  silhouette, not an IMU.
* forward/back trigger -> keys.press / keys.release
* separate left/right trigger and inversion -> pipeline.gain_x / gain_y (scales the
  vector the key mapper sees; the published joystick vector is untouched)
* triggers above the measurable range raise tilt.full_scale so they stay reachable.

Every change goes through backend.tilt_keys.control.apply_patch (same safe ranges,
distinct keys, hysteresis gap), releases held keys first, and can be undone.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from dataclasses import replace
from typing import Any

from backend.tilt_keys.config import KeyBindings, TiltKeyConfig
from backend.tilt_keys.control import MIN_HYSTERESIS_GAP_DEG, ControlError, apply_patch, config_summary
from backend.tilt_keys.telemetry import Telemetry, _monotonic_ms
from tilt_joystick.bus import EventBus
from tilt_joystick.config import KeyConfig
from tilt_joystick.pipeline import TiltPipeline

log = logging.getLogger(__name__)

DEG_PER_UNIT = 22.0  # degrees of tilt for joystick magnitude 1.0 at full_scale 1.0
HEADROOM = 0.8  # the highest trigger must sit at or below this fraction of a full push
PLAY_STATES = ('running', 'holding')
CALIBRATING_STATES = ('neutral', 'direction', 'direction_d')


class JoystickTelemetry:
    """Feeds backend Telemetry from the joystick event bus, in degrees."""

    def __init__(self, telemetry: Telemetry, deg_per_unit, clock_ms=_monotonic_ms) -> None:
        self.telemetry = telemetry
        self._deg = deg_per_unit  # callable: current degrees per joystick unit
        self._clock = clock_ms
        self._status: str | None = None
        self._held: set[str] = set()

    def attach(self, bus: EventBus) -> None:
        bus.subscribe('joystick', self._on_joystick)
        bus.subscribe('key_down', self._on_key)
        bus.subscribe('key_up', self._on_key)

    def _on_joystick(self, _name: str, p: dict) -> None:
        status, prev = p.get('status'), self._status
        self._status = status
        if prev in PLAY_STATES and status == 'lost':
            self.telemetry.on_event('tracking_lost', {})
        elif prev == 'lost' and status in PLAY_STATES:
            self.telemetry.on_event('tracking_restored', {})
        elif prev in CALIBRATING_STATES and status in PLAY_STATES:
            self.telemetry.on_event('calibration_complete', {})
        now = self._clock()
        if status == 'lost':
            self.telemetry.on_sample(now, None, None)
        elif status in PLAY_STATES and p.get('valid'):
            k = self._deg()
            self.telemetry.on_sample(now, p['y'] * k, p['x'] * k)  # forward = image-up = W, right = D

    def _on_key(self, name: str, p: dict) -> None:
        (self._held.add if name == 'key_down' else self._held.discard)(p['key'])
        self.telemetry.on_event('key_state', {'held': sorted(self._held)})


def to_agent_config(keys: KeyConfig, deg_per_unit: float) -> TiltKeyConfig:
    return TiltKeyConfig(
        on_threshold_deg=round(keys.press * deg_per_unit, 1),
        off_threshold_deg=round(keys.release * deg_per_unit, 1),
        keys=KeyBindings(forward=keys.up, back=keys.down, left=keys.left, right=keys.right),
        calibration_duration_ms=0,
    )


def project(cfg: TiltKeyConfig, keys: KeyConfig, base_full_scale: float) -> tuple[TiltKeyConfig, KeyConfig, float, float, float]:
    """Agent config -> (truthful agent config, joystick keys, gain_x, gain_y, full_scale)."""
    fwd_on, fwd_off = cfg.thresholds('forward')
    lr_on, _ = cfg.thresholds('right')
    full_scale = max(base_full_scale, max(fwd_on, lr_on) / (HEADROOM * DEG_PER_UNIT))
    k = DEG_PER_UNIT * full_scale
    new_keys = replace(keys, press=fwd_on / k, release=fwd_off / k, up=cfg.keys.forward, down=cfg.keys.back,
                       left=cfg.keys.left, right=cfg.keys.right)
    gain_x = (fwd_on / lr_on) * (-1.0 if cfg.invert_right else 1.0)
    gain_y = -1.0 if cfg.invert_forward else 1.0
    if cfg.lr_on_threshold_deg is not None:
        # One release magnitude serves both axes, so left/right's release scales with its trigger.
        derived_off = round(fwd_off * lr_on / fwd_on, 1)
        if lr_on - derived_off < MIN_HYSTERESIS_GAP_DEG:
            raise ControlError(f'left/right on/off gap {lr_on - derived_off:.1f} deg is below {MIN_HYSTERESIS_GAP_DEG} (keys would flicker)')
        cfg = replace(cfg, lr_off_threshold_deg=derived_off)
    return cfg, new_keys, gain_x, gain_y, full_scale


class JoystickControlService:
    """Same ops and reply shapes as backend.tilt_keys.control.ControlService."""

    def __init__(self, pipeline: TiltPipeline, *, clock_ms=_monotonic_ms, history: int = 50) -> None:
        self.pipeline = pipeline
        self.base_full_scale = pipeline.estimator.cfg.full_scale
        self.telemetry = Telemetry(clock_ms=clock_ms)
        self.feed = JoystickTelemetry(self.telemetry, self.deg_per_unit, clock_ms)
        self.feed.attach(pipeline.bus)
        self.config = to_agent_config(pipeline.config.keys, self.deg_per_unit())
        self.profile: str | None = None
        self._history: deque[dict[str, Any]] = deque(maxlen=history)
        self._undo: list[tuple[TiltKeyConfig, str | None]] = []
        self._revision = 0
        self._lock = threading.Lock()

    def deg_per_unit(self) -> float:
        return DEG_PER_UNIT * self.pipeline.estimator.cfg.full_scale

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        req_id = request.get('id') if isinstance(request, dict) else None
        try:
            if not isinstance(request, dict):
                raise ControlError('request must be a JSON object')
            op = request.get('op')
            handler = getattr(self, f'_op_{op}', None) if isinstance(op, str) else None
            if handler is None:
                raise ControlError(f'unknown op {op!r}')
            with self._lock:
                return {'id': req_id, 'ok': True, 'result': handler(request)}
        except ControlError as exc:
            return {'id': req_id, 'ok': False, 'error': str(exc)}
        except Exception as exc:  # never let a bad request reach the key loop
            log.exception('control op failed')
            return {'id': req_id, 'ok': False, 'error': f'internal error: {exc}'}

    # ------------------------------------------------------------- helpers
    def _apply(self, cfg: TiltKeyConfig, reason: str) -> TiltKeyConfig:
        cfg, keys, gx, gy, fs = project(cfg, self.pipeline.config.keys, self.base_full_scale)
        try:
            self.pipeline.apply_keys(keys, gx, gy, fs)
        except ValueError as exc:
            raise ControlError(str(exc)) from exc
        log.info('joystick settings changed (%s): press %.2f release %.2f gain x %.2f y %.2f full_scale %.2f',
                 reason, keys.press, keys.release, gx, gy, fs)
        self.config = cfg
        return cfg

    def _mode(self) -> str:
        p = self.pipeline
        if p.paused:
            return 'disabled'
        if p.estimator.phase in CALIBRATING_STATES:
            return 'calibrating'
        if p.state.status == 'lost':
            return 'tracking_lost'
        return 'active'

    def _record(self, actor: str, reason: str, before: TiltKeyConfig, after: TiltKeyConfig) -> dict:
        self._revision += 1
        entry = {'revision': self._revision, 'time': time.strftime('%H:%M:%S'), 'actor': actor, 'reason': reason,
                 'before': config_summary(before), 'after': config_summary(after)}
        self._history.append(entry)
        return entry

    # ------------------------------------------------------------------ ops
    def _op_status(self, req: dict) -> dict:
        p = self.pipeline
        return {
            'mode': self._mode(),
            'enabled': not p.paused,
            'calibrated': p.estimator.phase == 'running',
            'held': sorted(p.held),
            # The overhead joystick learns a neutral pose, not per-axis angle offsets.
            'calibration_offsets_deg': {'forward': None, 'right': None},
            'profile': self.profile,
            'revision': self._revision,
            'config': config_summary(self.config),
            'source': 'camera can joystick',
            'degrees_per_full_push': round(self.deg_per_unit(), 1),
        }

    def _op_telemetry(self, req: dict) -> dict:
        window = req.get('window_s', 60)
        if isinstance(window, bool) or not isinstance(window, (int, float)) or not 1 <= window <= 300:
            raise ControlError('window_s must be 1..300')
        snap = self.telemetry.snapshot(float(window))
        snap['config'] = config_summary(self.config)
        snap['mode'] = self._mode()
        return snap

    def _op_set_config(self, req: dict) -> dict:
        actor = str(req.get('actor', 'unknown'))[:40]
        reason = str(req.get('reason', ''))[:300]
        before = self.config
        after = self._apply(apply_patch(before, req.get('patch')), f'{actor}: {reason}')
        self._undo.append((before, self.profile))
        if 'profile' in req:
            self.profile = None if req['profile'] is None else str(req['profile'])[:40]
        return self._record(actor, reason, before, after)

    def _op_undo(self, req: dict) -> dict:
        if not self._undo:
            raise ControlError('nothing to undo')
        before = self.config
        prev, prev_profile = self._undo.pop()
        after = self._apply(prev, 'undo')
        self.profile = prev_profile
        return self._record(str(req.get('actor', 'unknown'))[:40], 'undo', before, after)

    def _op_undo_if_revision(self, req: dict) -> dict:
        expected = req.get('revision')
        if isinstance(expected, bool) or not isinstance(expected, int) or expected != self._revision:
            raise ControlError('settings changed since validation began; refusing to undo a newer change')
        return self._op_undo(req)

    def _op_history(self, req: dict) -> dict:
        return {'changes': list(self._history)}

    def _op_recalibrate(self, req: dict) -> dict:
        self.pipeline.recalibrate()
        return {'mode': self._mode(), 'duration_ms': int(self.pipeline.estimator.cfg.neutral_s * 1000)}

    def _op_enable(self, req: dict) -> dict:
        self.pipeline.set_paused(False)
        return {'enabled': True}

    def _op_disable(self, req: dict) -> dict:
        self.pipeline.set_paused(True)
        return {'enabled': False, 'held': sorted(self.pipeline.held)}


CONTROL_PATH = '/ws/control'


def serve_control(service: JoystickControlService, host: str = '127.0.0.1', port: int = 8766):
    """Serve the control API on ws://host:port/ws/control in a daemon thread. Returns the server."""
    from websockets.sync.server import serve

    def handler(conn) -> None:
        if conn.request.path != CONTROL_PATH:
            conn.close(1008, f'use {CONTROL_PATH}')
            return
        for raw in conn:
            try:
                request = json.loads(raw)
            except ValueError:
                request = None
            conn.send(json.dumps(service.handle(request)))

    server = serve(handler, host, port)
    threading.Thread(target=server.serve_forever, daemon=True, name='agent-control').start()
    log.info('agent control API on ws://%s:%d%s', host, port, CONTROL_PATH)
    return server
