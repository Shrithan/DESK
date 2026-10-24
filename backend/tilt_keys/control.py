"""Control API that lets the DESK agents read and safely change tilt-to-keys.

Transport-agnostic: ``ControlService.handle(request) -> response`` takes and
returns plain dicts. run.py serves it as JSON over ws://HOST:PORT/ws/control:

    -> {"id": "1", "op": "telemetry", "window_s": 60}
    <- {"id": "1", "ok": true, "result": {...}}

Ops: status, telemetry, set_config, undo, history, recalibrate, enable, disable.

Every change is validated against AGENT_LIMITS *in addition to* TiltKeyConfig's
own checks, keys are released before the swap, and every change is recorded
(who, why, before, after) so it can be audited and undone.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import replace
from typing import Any

from backend.tilt_keys.config import KeyBindings, TiltKeyConfig
from backend.tilt_keys.controller import TiltKeyController
from backend.tilt_keys.telemetry import Telemetry

log = logging.getLogger(__name__)

# The only settings an agent may touch, and their safe ranges.
AGENT_LIMITS: dict[str, tuple[float, float]] = {
    "on_threshold_deg": (5.0, 45.0),
    "off_threshold_deg": (2.0, 40.0),
    "lr_on_threshold_deg": (5.0, 45.0),
    "lr_off_threshold_deg": (2.0, 40.0),
}
MIN_HYSTERESIS_GAP_DEG = 2.0
AGENT_BOOL_FIELDS = {"invert_forward", "invert_right"}
KEY_SLOTS = ("forward", "back", "left", "right")
# Named keys an agent may bind (pynput Key names). Single printable characters are also allowed.
ALLOWED_NAMED_KEYS = {"up", "down", "left", "right", "space", "enter", "shift", "ctrl", "alt", "tab"}


class ControlError(ValueError):
    pass


def validate_key(key: str) -> str:
    if not isinstance(key, str):
        raise ControlError(f"key must be a string, got {key!r}")
    k = key.strip().lower()
    if len(k) == 1 and k.isprintable() and not k.isspace():
        return k
    if k in ALLOWED_NAMED_KEYS:
        return k
    raise ControlError(f"key {key!r} not allowed; use one character or one of {sorted(ALLOWED_NAMED_KEYS)}")


def apply_patch(config: TiltKeyConfig, patch: dict[str, Any]) -> TiltKeyConfig:
    """Return a new validated config with ``patch`` applied. Raises ControlError."""
    if not isinstance(patch, dict) or not patch:
        raise ControlError("patch must be a non-empty object")
    changes: dict[str, Any] = {}
    for name, value in patch.items():
        if name in AGENT_LIMITS:
            if value is None and name.startswith("lr_"):
                changes[name] = None
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ControlError(f"{name} must be a number")
            lo, hi = AGENT_LIMITS[name]
            if not lo <= float(value) <= hi:
                raise ControlError(f"{name}={value} outside the safe range {lo}..{hi}")
            changes[name] = float(value)
        elif name in AGENT_BOOL_FIELDS:
            if not isinstance(value, bool):
                raise ControlError(f"{name} must be true/false")
            changes[name] = value
        elif name == "keys":
            if not isinstance(value, dict) or not set(value) <= set(KEY_SLOTS):
                raise ControlError(f"keys must be an object with any of {list(KEY_SLOTS)}")
            current = config.keys
            changes["keys"] = KeyBindings(**{s: validate_key(value.get(s, getattr(current, s))) for s in KEY_SLOTS})
        else:
            raise ControlError(f"agents may not change {name!r}")
    try:
        new = replace(config, **changes)
    except ValueError as exc:  # TiltKeyConfig.__post_init__ checks
        raise ControlError(str(exc)) from exc
    for axis in ("forward", "right"):
        on, off = new.thresholds(axis)
        if on - off < MIN_HYSTERESIS_GAP_DEG:
            raise ControlError(f"{axis} on/off gap {on - off:.1f} deg is below {MIN_HYSTERESIS_GAP_DEG} (keys would flicker)")
    return new


def config_summary(config: TiltKeyConfig) -> dict[str, Any]:
    fwd_on, fwd_off = config.thresholds("forward")
    lr_on, lr_off = config.thresholds("right")
    return {
        "forward_back": {"on_deg": fwd_on, "off_deg": fwd_off},
        "left_right": {"on_deg": lr_on, "off_deg": lr_off},
        "keys": {s: getattr(config.keys, s) for s in KEY_SLOTS},
        "invert_forward": config.invert_forward,
        "invert_right": config.invert_right,
    }


class ControlService:
    def __init__(self, controller: TiltKeyController, telemetry: Telemetry, *, history: int = 50) -> None:
        self.controller = controller
        self.telemetry = telemetry
        self.profile: str | None = None
        self._history: deque[dict[str, Any]] = deque(maxlen=history)
        self._undo: list[tuple[TiltKeyConfig, str | None]] = []
        self._revision = 0

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        req_id = request.get("id") if isinstance(request, dict) else None
        try:
            if not isinstance(request, dict):
                raise ControlError("request must be a JSON object")
            op = request.get("op")
            handler = getattr(self, f"_op_{op}", None) if isinstance(op, str) else None
            if handler is None:
                raise ControlError(f"unknown op {op!r}")
            return {"id": req_id, "ok": True, "result": handler(request)}
        except ControlError as exc:
            return {"id": req_id, "ok": False, "error": str(exc)}
        except Exception as exc:  # never let a bad request kill the controller
            log.exception("control op failed")
            return {"id": req_id, "ok": False, "error": f"internal error: {exc}"}

    # ------------------------------------------------------------------- ops
    def _op_status(self, req: dict) -> dict:
        c = self.controller
        return {
            "mode": c.mode,
            "enabled": c.enabled,
            "calibrated": c.calibrated,
            "held": sorted(c.held),
            "calibration_offsets_deg": {"forward": round(c.forward_offset_deg, 2), "right": round(c.right_offset_deg, 2)},
            "profile": self.profile,
            "revision": self._revision,
            "config": config_summary(c.config),
        }

    def _op_telemetry(self, req: dict) -> dict:
        window = req.get("window_s", 60)
        if isinstance(window, bool) or not isinstance(window, (int, float)) or not 1 <= window <= 300:
            raise ControlError("window_s must be 1..300")
        snap = self.telemetry.snapshot(float(window))
        snap["config"] = config_summary(self.controller.config)
        snap["mode"] = self.controller.mode
        return snap

    def _op_set_config(self, req: dict) -> dict:
        actor = str(req.get("actor", "unknown"))[:40]
        reason = str(req.get("reason", ""))[:300]
        before = self.controller.config
        new = apply_patch(before, req.get("patch"))
        self._undo.append((before, self.profile))
        if "profile" in req:
            self.profile = None if req["profile"] is None else str(req["profile"])[:40]
        self.controller.apply_config(new, reason=f"{actor}: {reason}")
        self._revision += 1
        entry = {
            "revision": self._revision,
            "time": time.strftime("%H:%M:%S"),
            "actor": actor,
            "reason": reason,
            "before": config_summary(before),
            "after": config_summary(new),
        }
        self._history.append(entry)
        log.info("config changed by %s: %s", actor, reason)
        return entry

    def _op_undo(self, req: dict) -> dict:
        if not self._undo:
            raise ControlError("nothing to undo")
        before = self.controller.config
        prev, prev_profile = self._undo.pop()
        self.profile = prev_profile
        self.controller.apply_config(prev, reason="undo")
        self._revision += 1
        entry = {"revision": self._revision, "time": time.strftime("%H:%M:%S"), "actor": str(req.get("actor", "unknown"))[:40],
                 "reason": "undo", "before": config_summary(before), "after": config_summary(prev)}
        self._history.append(entry)
        return entry

    def _op_undo_if_revision(self, req: dict) -> dict:
        expected = req.get("revision")
        if isinstance(expected, bool) or not isinstance(expected, int) or expected != self._revision:
            raise ControlError("settings changed since validation began; refusing to undo a newer change")
        return self._op_undo(req)

    def _op_history(self, req: dict) -> dict:
        return {"changes": list(self._history)}

    def _op_recalibrate(self, req: dict) -> dict:
        self.controller.recalibrate()
        return {"mode": self.controller.mode, "duration_ms": self.controller.config.calibration_duration_ms}

    def _op_enable(self, req: dict) -> dict:
        self.controller.set_enabled(True)
        return {"enabled": True}

    def _op_disable(self, req: dict) -> dict:
        self.controller.set_enabled(False)
        return {"enabled": False, "held": sorted(self.controller.held)}
