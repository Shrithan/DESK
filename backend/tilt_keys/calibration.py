"""Neutral (upright) calibration: average ~2 s of readings while the can stands
still and use that as the zero for every later reading."""

from __future__ import annotations

import statistics
from dataclasses import dataclass


@dataclass(frozen=True)
class CalibrationSample:
    timestamp_ms: int
    forward_deg: float | None  # None = unavailable at this instant
    right_deg: float | None


@dataclass(frozen=True)
class CalibrationResult:
    ok: bool
    forward_offset_deg: float = 0.0
    right_offset_deg: float = 0.0
    reason: str = ""
    n_samples: int = 0
    forward_std_deg: float | None = None
    right_std_deg: float | None = None


def compute_neutral_offset(
    samples: list[CalibrationSample],
    *,
    min_samples: int,
    min_valid_fraction: float,
    max_std_deg: float,
    max_range_deg: float,
) -> CalibrationResult:
    """Return the mean upright angle per axis, or a failed result with a reason.

    Fails if too few readings had the can visible, or if either axis moved more
    than allowed (std dev or peak-to-peak range), which means the can was not
    standing still.
    """
    valid = [s for s in samples if s.forward_deg is not None and s.right_deg is not None]
    if len(valid) < min_samples:
        return CalibrationResult(
            ok=False,
            reason=f"only {len(valid)} usable readings (need {min_samples}); is the can visible?",
            n_samples=len(valid),
        )
    if len(valid) < min_valid_fraction * len(samples):
        return CalibrationResult(
            ok=False,
            reason=f"can was missing in {len(samples) - len(valid)}/{len(samples)} readings",
            n_samples=len(valid),
        )

    fwd = [s.forward_deg for s in valid]
    rgt = [s.right_deg for s in valid]
    fwd_std, rgt_std = statistics.pstdev(fwd), statistics.pstdev(rgt)
    fwd_range, rgt_range = max(fwd) - min(fwd), max(rgt) - min(rgt)

    for axis, std, rng in (("forward", fwd_std, fwd_range), ("right", rgt_std, rgt_range)):
        if std > max_std_deg or rng > max_range_deg:
            return CalibrationResult(
                ok=False,
                reason=(
                    f"can was moving during calibration: {axis} std {std:.2f} deg (max {max_std_deg}), "
                    f"range {rng:.2f} deg (max {max_range_deg}). Hold it still and recalibrate."
                ),
                n_samples=len(valid),
                forward_std_deg=fwd_std,
                right_std_deg=rgt_std,
            )

    return CalibrationResult(
        ok=True,
        forward_offset_deg=statistics.fmean(fwd),
        right_offset_deg=statistics.fmean(rgt),
        n_samples=len(valid),
        forward_std_deg=fwd_std,
        right_std_deg=rgt_std,
    )


def apply_offset(value: float | None, offset: float) -> float | None:
    return None if value is None else value - offset


class NeutralCalibrator:
    """Collects samples until ``duration_ms`` of message time has elapsed."""

    def __init__(self, duration_ms: int) -> None:
        self.duration_ms = duration_ms
        self.samples: list[CalibrationSample] = []

    def reset(self) -> None:
        self.samples.clear()

    def add(self, sample: CalibrationSample) -> bool:
        """Add a sample; return True once the collection window is complete."""
        self.samples.append(sample)
        return self.samples[-1].timestamp_ms - self.samples[0].timestamp_ms >= self.duration_ms
