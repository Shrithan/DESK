"""Tilt -> keys pipeline with safety rules. No I/O of its own besides the injected
key backend, so every rule is unit-testable with a fake clock.

Per tilt_update:  calibration offset -> invert -> One Euro filter -> hysteresis
                  -> edge-triggered output.
Safety:           unavailable axis releases that axis immediately; no update for
                  stale_timeout_ms releases everything (call tick() periodically);
                  disabled sends nothing; shutdown() releases everything.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from backend.tilt_keys.calibration import (
    CalibrationSample,
    NeutralCalibrator,
    apply_offset,
    compute_neutral_offset,
)
from backend.tilt_keys.config import TiltKeyConfig
from backend.tilt_keys.hysteresis import desired_keys
from backend.tilt_keys.one_euro import OneEuroFilter
from backend.tilt_keys.output import EdgeTriggeredOutput, KeyBackend
from shared.contracts.tilt import TiltCommand, TiltUpdate, parse_tilt_message

log = logging.getLogger(__name__)

EventListener = Callable[[str, dict[str, Any]], None]
# (local_ms, forward_deg, right_deg) after calibration/inversion/filtering; None = unavailable.
SampleListener = Callable[[int, float | None, float | None], None]


def monotonic_ms() -> int:
    return time.monotonic_ns() // 1_000_000


class TiltKeyController:
    def __init__(
        self,
        config: TiltKeyConfig,
        backend: KeyBackend,
        *,
        clock_ms: Callable[[], int] = monotonic_ms,
        on_event: EventListener | None = None,
        on_sample: SampleListener | None = None,
    ) -> None:
        self.config = config
        self.output = EdgeTriggeredOutput(backend)
        self._clock_ms = clock_ms
        self._on_event = on_event
        self._on_sample = on_sample
        self._lock = threading.RLock()
        self._closed = False

        self._filters = {
            axis: OneEuroFilter(config.filter_min_cutoff_hz, config.filter_beta, config.filter_d_cutoff_hz)
            for axis in ("forward", "right")
        }
        self._calibrator = NeutralCalibrator(config.calibration_duration_ms)
        self.forward_offset_deg = 0.0
        self.right_offset_deg = 0.0
        self.calibrated = config.calibration_duration_ms == 0

        self.enabled = True
        self._last_rx_ms: int | None = None  # local receive time, for the stale watchdog
        self._last_msg_ts_ms: int | None = None  # producer timestamp, for ordering/filtering
        self._stale = False
        self._can_visible: bool | None = None

        if not self.calibrated:
            self._emit("calibration_started", duration_ms=config.calibration_duration_ms)

    # ------------------------------------------------------------------ state
    @property
    def held(self) -> frozenset[str]:
        return self.output.held

    @property
    def mode(self) -> str:
        if not self.enabled:
            return "disabled"
        return "active" if self.calibrated else "calibrating"

    # ----------------------------------------------------------------- inputs
    def handle_message(self, raw: str | bytes | dict, now_ms: int | None = None) -> None:
        """Entry point for JSON from a websocket, stdin line, or function call.

        Invalid messages are logged and dropped; they do NOT refresh the stale
        watchdog, so garbage input can never keep a key held.
        """
        try:
            data = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
            msg = parse_tilt_message(data)
        except (ValueError, ValidationError) as exc:
            log.warning("dropping invalid tilt message: %s", exc)
            return
        if isinstance(msg, TiltUpdate):
            self.handle_update(msg, now_ms)
        elif isinstance(msg, TiltCommand):
            self.handle_command(msg.command)

    def handle_command(self, command: str) -> None:
        if command == "recalibrate":
            self.recalibrate()
        elif command == "enable":
            self.set_enabled(True)
        elif command == "disable":
            self.set_enabled(False)
        elif command == "toggle":
            self.set_enabled(not self.enabled)
        else:
            log.warning("unknown tilt command %r", command)

    def handle_update(self, update: TiltUpdate, now_ms: int | None = None) -> None:
        with self._lock:
            if self._closed:
                return
            self._last_rx_ms = self._clock_ms() if now_ms is None else now_ms
            self._stale = False
            if not self.enabled:
                return
            if self._last_msg_ts_ms is not None and update.timestamp_ms <= self._last_msg_ts_ms:
                log.debug("dropping out-of-order tilt_update ts=%d", update.timestamp_ms)
                return
            self._last_msg_ts_ms = update.timestamp_ms

            forward_raw, right_raw = update.usable_forward(), update.usable_right()
            self._track_visibility(update.can_found)

            if not self.calibrated:
                self.output.release_all()
                self._calibrate_step(CalibrationSample(update.timestamp_ms, forward_raw, right_raw))
                return

            forward = self._process_axis("forward", forward_raw, update.timestamp_ms)
            right = self._process_axis("right", right_raw, update.timestamp_ms)
            if self._on_sample is not None:
                try:
                    self._on_sample(self._last_rx_ms, forward, right)
                except Exception:
                    log.exception("sample listener failed")
            self._set_held(desired_keys(forward, right, self.output.held, self.config))

    def tick(self, now_ms: int | None = None) -> None:
        """Stale-input watchdog; call every ``watchdog_period_ms``."""
        with self._lock:
            if self._closed or self._stale or self._last_rx_ms is None:
                return
            now = self._clock_ms() if now_ms is None else now_ms
            age = now - self._last_rx_ms
            if age > self.config.stale_timeout_ms:
                self._stale = True
                self._reset_signal_state()
                self._last_msg_ts_ms = None  # producer may have restarted with a new clock
                if not self.calibrated:
                    self._calibrator.reset()
                had_keys = bool(self.output.held)
                self._set_held(frozenset())
                self._emit("stale_release", age_ms=age, released=had_keys)
                log.warning("no tilt_update for %d ms (> %d): released all keys", age, self.config.stale_timeout_ms)

    # --------------------------------------------------------------- controls
    def recalibrate(self) -> None:
        with self._lock:
            self._set_held(frozenset())
            self._reset_signal_state()
            self._calibrator.reset()
            self.calibrated = self.config.calibration_duration_ms == 0
            self._emit("calibration_started", duration_ms=self.config.calibration_duration_ms)

    def apply_config(self, config: TiltKeyConfig, reason: str = "") -> None:
        """Swap in a new (already validated) config at runtime.

        Keys are released first so a binding or threshold change can never leave a
        stale key held. Calibration offsets are kept; filters are rebuilt.
        """
        with self._lock:
            if self._closed:
                return
            self._set_held(frozenset())
            self.config = config
            self._filters = {
                axis: OneEuroFilter(config.filter_min_cutoff_hz, config.filter_beta, config.filter_d_cutoff_hz)
                for axis in ("forward", "right")
            }
            self._emit("config_applied", reason=reason)

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            if enabled == self.enabled:
                return
            if not enabled:
                self._set_held(frozenset())
            self._reset_signal_state()
            self.enabled = enabled
            self._emit("enabled" if enabled else "disabled")

    def release_all(self, reason: str = "requested") -> None:
        with self._lock:
            if self.output.held:
                log.info("releasing all keys (%s)", reason)
            self._set_held(frozenset())

    def shutdown(self, reason: str = "shutdown") -> None:
        """Release everything and close the backend. Safe to call repeatedly."""
        with self._lock:
            if self._closed:
                return
            try:
                self.release_all(reason)
            finally:
                self._closed = True
                try:
                    self.output.backend.close()
                except Exception:
                    log.exception("key backend close() failed")
                self._emit("shutdown", reason=reason)

    # --------------------------------------------------------------- internals
    def _calibrate_step(self, sample: CalibrationSample) -> None:
        if not self._calibrator.add(sample):
            return
        cfg = self.config
        result = compute_neutral_offset(
            self._calibrator.samples,
            min_samples=cfg.calibration_min_samples,
            min_valid_fraction=cfg.calibration_min_valid_fraction,
            max_std_deg=cfg.calibration_max_std_deg,
            max_range_deg=cfg.calibration_max_range_deg,
        )
        self._calibrator.reset()
        if result.ok:
            self.forward_offset_deg = result.forward_offset_deg
            self.right_offset_deg = result.right_offset_deg
            self.calibrated = True
            self._emit(
                "calibration_complete",
                forward_offset_deg=round(result.forward_offset_deg, 3),
                right_offset_deg=round(result.right_offset_deg, 3),
                n_samples=result.n_samples,
            )
        else:
            log.warning("calibration rejected: %s (retrying)", result.reason)
            self._emit("calibration_failed", reason=result.reason)

    def _process_axis(self, axis: str, raw: float | None, ts_ms: int) -> float | None:
        filt = self._filters[axis]
        if raw is None:
            filt.reset()
            return None
        offset = self.forward_offset_deg if axis == "forward" else self.right_offset_deg
        invert = self.config.invert_forward if axis == "forward" else self.config.invert_right
        value = apply_offset(raw, offset)
        if invert:
            value = -value
        return filt(value, ts_ms) if self.config.filter_enabled else value

    def _reset_signal_state(self) -> None:
        for filt in self._filters.values():
            filt.reset()

    def _track_visibility(self, can_found: bool) -> None:
        if self._can_visible is not None and can_found != self._can_visible:
            self._emit("tracking_restored" if can_found else "tracking_lost")
        self._can_visible = can_found

    def _set_held(self, keys: frozenset[str]) -> None:
        before = self.output.held
        self.output.set_held(keys)
        if self.output.held != before:
            self._emit("key_state", held=sorted(self.output.held))

    def _emit(self, name: str, **details: Any) -> None:
        log.info("event %s %s", name, details or "")
        if self._on_event is not None:
            try:
                self._on_event(name, details)
            except Exception:
                log.exception("event listener failed for %s", name)
