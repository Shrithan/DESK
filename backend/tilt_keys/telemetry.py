"""Rolling telemetry for tilt-to-keys, read by the DESK agents.

Fed by two controller hooks (``on_sample`` for every processed frame and
``on_event`` for state changes). Everything is kept in bounded deques, so memory
stays flat however long DESK runs. ``snapshot()`` is cheap and thread-safe.

"Flicker" = a key that was pressed and released again within ``flicker_ms``.
That is the signature of a threshold sitting inside the user's natural wobble.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any


def _monotonic_ms() -> int:
    return time.monotonic_ns() // 1_000_000


def _percentile(sorted_vals: list[float], q: float) -> float | None:
    if not sorted_vals:
        return None
    idx = min(len(sorted_vals) - 1, max(0, round(q * (len(sorted_vals) - 1))))
    return sorted_vals[idx]


class Telemetry:
    def __init__(
        self,
        *,
        clock_ms: Callable[[], int] = _monotonic_ms,
        flicker_ms: int = 250,
        max_samples: int = 30 * 300,  # ~5 minutes at 30 Hz
        max_events: int = 5000,
    ) -> None:
        self._clock_ms = clock_ms
        self.flicker_ms = flicker_ms
        self._lock = threading.Lock()
        self._samples: deque[tuple[int, float | None, float | None]] = deque(maxlen=max_samples)
        # (ms, key, held_ms) for every completed press
        self._presses: deque[tuple[int, str, int]] = deque(maxlen=max_events)
        self._events: deque[tuple[int, str, dict[str, Any]]] = deque(maxlen=max_events)
        self._held_since: dict[str, int] = {}
        self._held: frozenset[str] = frozenset()
        self.started_ms = clock_ms()

    # ------------------------------------------------------------------ hooks
    def on_sample(self, ms: int, forward: float | None, right: float | None) -> None:
        with self._lock:
            self._samples.append((ms, forward, right))

    def on_event(self, name: str, details: dict[str, Any]) -> None:
        now = self._clock_ms()
        with self._lock:
            if name == "key_state":
                new = frozenset(details.get("held", ()))
                for key in new - self._held:
                    self._held_since[key] = now
                for key in self._held - new:
                    start = self._held_since.pop(key, now)
                    self._presses.append((now, key, now - start))
                self._held = new
            else:
                self._events.append((now, name, dict(details)))

    # ------------------------------------------------------------------ reads
    def snapshot(self, window_s: float = 60.0) -> dict[str, Any]:
        now = self._clock_ms()
        since = now - int(window_s * 1000)
        with self._lock:
            samples = [s for s in self._samples if s[0] >= since]
            presses = [p for p in self._presses if p[0] >= since]
            events = [e for e in self._events if e[0] >= since]
        span_s = (now - max(since, self.started_ms)) / 1000 or 1e-9

        def axis_stats(values: list[float]) -> dict[str, Any]:
            mags = sorted(abs(v) for v in values)
            pos = [v for v in values if v > 0]
            neg = [-v for v in values if v < 0]
            return {
                "n": len(values),
                "abs_p50_deg": _r(_percentile(mags, 0.5)),
                "abs_p90_deg": _r(_percentile(mags, 0.9)),
                "max_pos_deg": _r(max(pos, default=None)),
                "max_neg_deg": _r(max(neg, default=None)),
            }

        fwd = [s[1] for s in samples if s[1] is not None]
        rgt = [s[2] for s in samples if s[2] is not None]
        unavailable = sum(1 for s in samples if s[1] is None and s[2] is None)

        keys: dict[str, dict[str, int]] = {}
        for _, key, held_ms in presses:
            k = keys.setdefault(key, {"presses": 0, "flickers": 0, "held_ms_total": 0})
            k["presses"] += 1
            k["held_ms_total"] += held_ms
            if held_ms < self.flicker_ms:
                k["flickers"] += 1

        def count(name: str) -> int:
            return sum(1 for e in events if e[1] == name)

        last_cal = next((e for e in reversed(events) if e[1] in ("calibration_complete", "calibration_failed")), None)
        return {
            "window_s": round(min(window_s, span_s), 1),
            "frames": len(samples),
            "frame_rate_hz": round(len(samples) / span_s, 1) if samples else 0.0,
            "unavailable_frames": unavailable,
            "forward": axis_stats(fwd),
            "right": axis_stats(rgt),
            "keys": keys,
            "tracking_lost": count("tracking_lost"),
            "tracking_restored": count("tracking_restored"),
            "stale_releases": count("stale_release"),
            "calibration_failures": count("calibration_failed"),
            "last_calibration": None if last_cal is None else {"event": last_cal[1], **last_cal[2]},
            "recent_events": [{"age_s": round((now - t) / 1000, 1), "event": n, **d} for t, n, d in events[-8:]],
        }

    def reset(self) -> None:
        with self._lock:
            self._samples.clear()
            self._presses.clear()
            self._events.clear()
            self.started_ms = self._clock_ms()


def _r(v: float | None) -> float | None:
    return None if v is None else round(v, 2)
