"""Frame sources: USB webcams via OpenCV, recorded clips (offline fallback), synthetic patterns."""

from __future__ import annotations

import json
import logging
import platform
import time
from abc import ABC, abstractmethod
from pathlib import Path

import cv2
import numpy as np

from .devices import ResolvedDevice, resolve
from .rig import REPO_ROOT, CameraSpec

log = logging.getLogger(__name__)


class SourceError(RuntimeError):
    pass


class FrameSource(ABC):
    """Produces (image, capture_time_monotonic_ns). read() blocks until a frame or returns None on failure."""

    kind = "abstract"

    @property
    def nominal_fps(self) -> float | None:
        """Frame rate the source actually runs at (known after open), or None if unknown."""
        return None

    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def read(self) -> tuple[np.ndarray, int] | None: ...

    @abstractmethod
    def close(self) -> None: ...

    def describe(self) -> dict:
        return {"kind": self.kind}


class UVCSource(FrameSource):
    """A USB webcam opened through OpenCV, asking for MJPEG so three cameras fit on one USB 2 bus."""

    kind = "uvc"

    def __init__(self, spec: CameraSpec, latency_ms: float = 0.0):
        self.spec = spec
        self.latency_ns = int(latency_ms * 1e6)
        self.cap: cv2.VideoCapture | None = None
        self.resolved: ResolvedDevice | None = None
        self.actual: dict = {}

    def open(self) -> None:
        self.resolved = resolve(self.spec.source)
        backend = {"Darwin": cv2.CAP_AVFOUNDATION, "Linux": cv2.CAP_V4L2, "Windows": cv2.CAP_MSMF}.get(platform.system(), cv2.CAP_ANY)
        cap = cv2.VideoCapture(self.resolved.open_arg, backend)
        if not cap.isOpened():
            raise SourceError(f"could not open {self.resolved.open_arg!r} ({self.resolved.reason})")
        if self.spec.fourcc:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*self.spec.fourcc))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.spec.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.spec.height)
        cap.set(cv2.CAP_PROP_FPS, self.spec.fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # newest frame, not a queue of stale ones (ignored by some backends)
        self.actual = {
            "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "fps": float(cap.get(cv2.CAP_PROP_FPS)),
        }
        if (self.actual["width"], self.actual["height"]) != (self.spec.width, self.spec.height):
            log.warning("%s: asked %dx%d, camera gives %dx%d; calibration must match the actual size",
                        self.spec.id, self.spec.width, self.spec.height, self.actual["width"], self.actual["height"])
        self.cap = cap
        log.info("%s opened %r via %s (stable=%s) actual=%s", self.spec.id, self.resolved.open_arg,
                 self.resolved.reason, self.resolved.stable, self.actual)

    @property
    def nominal_fps(self) -> float | None:
        return self.actual.get("fps") or None

    def read(self) -> tuple[np.ndarray, int] | None:
        if self.cap is None:
            return None
        ok, img = self.cap.read()
        now = time.monotonic_ns()
        if not ok or img is None:
            return None
        return img, now - self.latency_ns

    def close(self) -> None:
        if self.cap is not None:
            self.cap.release()
        self.cap = None

    def describe(self) -> dict:
        r = self.resolved
        return {
            "kind": self.kind,
            "open_arg": None if r is None else r.open_arg,
            "stable_identity": None if r is None else r.stable,
            "resolution": None if r is None else r.reason,
            "device": None if (r is None or r.info is None) else r.info.to_dict(),
            "actual": self.actual,
            "assumed_latency_ms": self.latency_ns / 1e6,
        }


class VideoFileSource(FrameSource):
    """Plays a recorded clip as if it were a live camera.

    Capture times come from the clip's own timeline anchored to a shared `epoch_ns`, so clips
    recorded together stay in sync (plus an optional per-clip `capture_offset_ms` read from a
    sidecar `<clip>.json`, used by fixtures to simulate unsynchronised cameras).
    """

    kind = "video"

    def __init__(self, path: str | Path, epoch_ns: int, loop: bool = True, realtime: bool = True, fps: float | None = None):
        p = Path(path)
        self.path = p if p.is_absolute() else REPO_ROOT / p
        self.epoch_ns = epoch_ns
        self.loop = loop
        self.realtime = realtime
        self.fps_override = fps
        self.cap: cv2.VideoCapture | None = None
        self.n = 0
        self.fps = 30.0
        self.offset_ns = 0
        self.frame_times_ns: list[int] | None = None  # recorded per-frame times (from `python -m camera record`)
        sidecar = self.path.with_suffix(".json")
        if sidecar.exists():
            meta = json.loads(sidecar.read_text())
            self.offset_ns = int(meta.get("capture_offset_ms", 0.0) * 1e6)
            self.frame_times_ns = meta.get("frame_times_ns")

    def open(self) -> None:
        if not self.path.exists():
            raise SourceError(f"video not found: {self.path}")
        self.cap = cv2.VideoCapture(str(self.path))
        if not self.cap.isOpened():
            raise SourceError(f"cannot decode {self.path}")
        self.fps = self.fps_override or self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.frames_per_loop = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT)) or None

    def read(self) -> tuple[np.ndarray, int] | None:
        if self.cap is None:
            return None
        ok, img = self.cap.read()
        if not ok:
            if not self.loop:
                return None
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, img = self.cap.read()
            if not ok:
                return None
        t = self.epoch_ns + self._clip_time_ns(self.n) + self.offset_ns
        self.n += 1
        if self.realtime:
            wait = (t - self.offset_ns) - time.monotonic_ns()
            if wait > 0:
                time.sleep(wait / 1e9)
        return img, t

    @property
    def nominal_fps(self) -> float | None:
        return self.fps

    def _clip_time_ns(self, n: int) -> int:
        period = 1e9 / self.fps
        ts = self.frame_times_ns
        if not ts:
            return int(n * period)
        loops, i = divmod(n, len(ts))
        return int(loops * (ts[-1] + period) + ts[i])

    def close(self) -> None:
        if self.cap is not None:
            self.cap.release()
        self.cap = None

    def describe(self) -> dict:
        return {"kind": self.kind, "path": str(self.path), "fps": self.fps, "loop": self.loop,
                "capture_offset_ms": self.offset_ns / 1e6}


class SyntheticPatternSource(FrameSource):
    """Cheap moving test pattern with the frame number burned in; for tests and demos with no cameras."""

    kind = "synthetic"

    def __init__(self, camera_id: str, width: int, height: int, fps: float, epoch_ns: int, offset_ms: float = 0.0,
                 fail_after: int | None = None):
        self.camera_id, self.width, self.height, self.fps = camera_id, width, height, fps
        self.epoch_ns = epoch_ns
        self.offset_ns = int(offset_ms * 1e6)
        self.fail_after = fail_after  # simulate an unplug after N frames (tests)
        self.n = 0
        self.opened = False

    @property
    def nominal_fps(self) -> float | None:
        return self.fps

    def open(self) -> None:
        self.opened = True

    def read(self) -> tuple[np.ndarray, int] | None:
        if not self.opened or (self.fail_after is not None and self.n >= self.fail_after):
            return None
        t = self.epoch_ns + int(self.n * 1e9 / self.fps)
        wait = t - time.monotonic_ns()
        if wait > 0:
            time.sleep(wait / 1e9)
        img = np.zeros((self.height, self.width, 3), np.uint8)
        x = int((self.n * 7) % self.width)
        img[:, : self.width // 2] = (40, 40, 40)
        cv2.circle(img, (x, self.height // 2), max(4, self.height // 10), (0, 200, 255), -1)
        cv2.putText(img, f"{self.camera_id} #{self.n}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        self.n += 1
        return img, t + self.offset_ns

    def close(self) -> None:
        self.opened = False

    def describe(self) -> dict:
        return {"kind": self.kind, "fps": self.fps, "capture_offset_ms": self.offset_ns / 1e6}


def make_source(spec: CameraSpec, epoch_ns: int, latency_ms: float = 0.0) -> FrameSource:
    s = spec.source
    if s.kind == "uvc":
        return UVCSource(spec, latency_ms=latency_ms)
    if s.kind == "video":
        if not s.path:
            raise SourceError(f"{spec.id}: video source needs a path")
        return VideoFileSource(s.path, epoch_ns, loop=s.loop, realtime=s.realtime)
    if s.kind == "synthetic":
        return SyntheticPatternSource(spec.id, spec.width, spec.height, spec.fps, epoch_ns)
    raise SourceError(f"{spec.id}: unknown source kind {s.kind!r}")
