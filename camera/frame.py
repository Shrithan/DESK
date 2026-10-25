"""The frame type every downstream consumer (agents 2 and 3) receives from camera ingest."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

# Offset between the host's monotonic clock and Unix time, captured once at import so that
# every frame from this process converts with the same offset.
_MONO_TO_UNIX_NS = time.time_ns() - time.monotonic_ns()


def monotonic_to_unix_ms(monotonic_ns: int) -> int:
    return (monotonic_ns + _MONO_TO_UNIX_NS) // 1_000_000


@dataclass(frozen=True)
class CameraFrame:
    """One decoded frame.

    Timestamps use the host's monotonic clock (time.monotonic_ns), which is shared by every
    camera on this machine, so frames from different cameras are directly comparable.

    capture_time_monotonic_ns: best estimate of when the image was exposed. For USB webcams
        this is the receive time minus the configured pipeline latency (UVC does not report
        the exposure time through OpenCV); for recorded/synthetic sources it is exact.
    receive_time_monotonic_ns: when ingest got the decoded frame.
    """

    camera_id: str
    frame_index: int
    capture_time_monotonic_ns: int
    receive_time_monotonic_ns: int
    frame_size: tuple[int, int]  # (width, height) in pixels
    image: np.ndarray = field(repr=False)  # BGR uint8, H x W x 3
    calibration_version: str | None = None
    source_kind: str = "uvc"

    @property
    def capture_time_unix_ms(self) -> int:
        return monotonic_to_unix_ms(self.capture_time_monotonic_ns)

    def age_ms(self, now_ns: int | None = None) -> float:
        now_ns = time.monotonic_ns() if now_ns is None else now_ns
        return (now_ns - self.capture_time_monotonic_ns) / 1e6

    def metadata(self) -> dict:
        """JSON-serialisable description (everything except the pixels)."""
        return {
            "camera_id": self.camera_id,
            "frame_index": self.frame_index,
            "capture_time_monotonic_ns": self.capture_time_monotonic_ns,
            "receive_time_monotonic_ns": self.receive_time_monotonic_ns,
            "capture_time_unix_ms": self.capture_time_unix_ms,
            "frame_size": {"width": self.frame_size[0], "height": self.frame_size[1]},
            "calibration_version": self.calibration_version,
            "source_kind": self.source_kind,
        }
