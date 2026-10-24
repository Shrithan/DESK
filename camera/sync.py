"""Timestamp pairing across unsynchronised cameras, and mismatch metrics.

The C270s free-run: nothing aligns their exposures, so two cameras at 30 fps can be up to
half a frame period (~16.7 ms) apart even with perfect timestamps, plus USB/driver latency
differences. We therefore (1) pair frames by nearest capture time within a tolerance,
(2) report the spread of every set, and (3) optionally estimate constant per-camera latency
offsets from motion seen by all cameras. Nothing here claims frame-perfect sync.
"""

from __future__ import annotations

import collections
import threading
from dataclasses import dataclass, field

import numpy as np

from .frame import CameraFrame


@dataclass(frozen=True)
class FrameSet:
    frames: dict[str, CameraFrame]
    reference_time_monotonic_ns: int | None
    spread_ns: int | None  # max - min capture time among included frames
    tolerance_ns: int
    missing: tuple[str, ...] = ()  # cameras with no frame within tolerance (or none at all)
    offsets_ns: dict[str, int] = field(default_factory=dict)  # capture time - reference, per camera

    @property
    def complete(self) -> bool:
        return not self.missing and len(self.frames) > 0

    @property
    def spread_ms(self) -> float | None:
        return None if self.spread_ns is None else self.spread_ns / 1e6

    def metadata(self) -> dict:
        return {
            "reference_time_monotonic_ns": self.reference_time_monotonic_ns,
            "spread_ms": self.spread_ms,
            "tolerance_ms": self.tolerance_ns / 1e6,
            "complete": self.complete,
            "missing": list(self.missing),
            "offsets_ms": {k: v / 1e6 for k, v in self.offsets_ns.items()},
            "frames": {k: f.metadata() for k, f in self.frames.items()},
        }


def match_frameset(recent: dict[str, list[CameraFrame]], tolerance_ns: int) -> FrameSet:
    """Pick one frame per camera so capture times are as close as possible.

    Reference = the oldest of the cameras' newest frames (the laggard), so every other camera
    has a frame at or after it in its ring buffer; each camera contributes the frame nearest
    to the reference. Cameras farther than the tolerance are listed in `missing` and left out
    (graceful degradation to fewer views).
    """
    newest = {cid: fs[-1] for cid, fs in recent.items() if fs}
    if not newest:
        return FrameSet({}, None, None, tolerance_ns, tuple(recent))
    ref = min(f.capture_time_monotonic_ns for f in newest.values())
    chosen: dict[str, CameraFrame] = {}
    missing = [cid for cid, fs in recent.items() if not fs]
    for cid, fs in recent.items():
        if not fs:
            continue
        best = min(fs, key=lambda f: abs(f.capture_time_monotonic_ns - ref))
        if abs(best.capture_time_monotonic_ns - ref) <= tolerance_ns:
            chosen[cid] = best
        else:
            missing.append(cid)
    times = [f.capture_time_monotonic_ns for f in chosen.values()]
    spread = (max(times) - min(times)) if times else None
    offsets = {cid: f.capture_time_monotonic_ns - ref for cid, f in chosen.items()}
    return FrameSet(chosen, ref, spread, tolerance_ns, tuple(sorted(missing)), offsets)


class SyncMonitor:
    """Rolling statistics of frameset spread and completeness."""

    def __init__(self, camera_ids: list[str], window: int = 300):
        self.camera_ids = camera_ids
        self.spreads: collections.deque[float] = collections.deque(maxlen=window)
        self.complete: collections.deque[bool] = collections.deque(maxlen=window)
        self.offsets: dict[str, collections.deque[float]] = {c: collections.deque(maxlen=window) for c in camera_ids}
        self._lock = threading.Lock()

    def record(self, fs: FrameSet) -> None:
        with self._lock:
            self.complete.append(fs.complete)
            if fs.spread_ns is not None and len(fs.frames) > 1:
                self.spreads.append(fs.spread_ns / 1e6)
            for cid, off in fs.offsets_ns.items():
                if cid in self.offsets:
                    self.offsets[cid].append(off / 1e6)

    def summary(self) -> dict:
        with self._lock:
            s = np.array(self.spreads) if self.spreads else None
            return {
                "framesets": len(self.complete),
                "complete_ratio": None if not self.complete else round(float(np.mean(self.complete)), 3),
                "spread_ms": None if s is None else {
                    "mean": round(float(s.mean()), 2),
                    "p50": round(float(np.percentile(s, 50)), 2),
                    "p95": round(float(np.percentile(s, 95)), 2),
                    "max": round(float(s.max()), 2),
                },
                "mean_offset_ms": {c: (round(float(np.mean(v)), 2) if v else None) for c, v in self.offsets.items()},
                "note": "free-running cameras: expect spreads up to ~half a frame period plus latency differences",
            }


def motion_energy(prev_gray: np.ndarray, gray: np.ndarray) -> float:
    """Mean absolute frame difference: a per-frame motion signal for offset estimation."""
    return float(np.mean(np.abs(gray.astype(np.int16) - prev_gray.astype(np.int16))))


def estimate_offset_ms(
    times_a_ns: np.ndarray, signal_a: np.ndarray, times_b_ns: np.ndarray, signal_b: np.ndarray,
    max_lag_ms: float = 200.0, step_ms: float = 1.0,
) -> tuple[float, float]:
    """Estimate how much camera B's timestamps lag camera A's for the same physical events.

    Both cameras watch the same motion (wave a hand, flick the lights). Returns (offset_ms,
    peak normalised correlation). Subtract offset_ms from B's capture times to align it to A.
    A low correlation (< ~0.5) means the estimate is not trustworthy.
    """
    t0 = max(times_a_ns.min(), times_b_ns.min())
    t1 = min(times_a_ns.max(), times_b_ns.max())
    if t1 - t0 < 4 * max_lag_ms * 1e6:
        raise ValueError("signals overlap too little for the requested max lag")
    grid = np.arange(t0, t1, step_ms * 1e6)
    a = np.interp(grid, times_a_ns, signal_a)
    b = np.interp(grid, times_b_ns, signal_b)
    a = (a - a.mean()) / (a.std() + 1e-12)
    b = (b - b.mean()) / (b.std() + 1e-12)
    max_k = int(max_lag_ms / step_ms)
    best_k, best_c = 0, -np.inf
    for k in range(-max_k, max_k + 1):
        if k >= 0:
            c = np.dot(a[: len(a) - k], b[k:]) / (len(a) - k)
        else:
            c = np.dot(a[-k:], b[: len(b) + k]) / (len(b) + k)
        if c > best_c:
            best_k, best_c = k, c
    return best_k * step_ms, float(best_c)
