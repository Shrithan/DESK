"""Camera ingest: one capture thread per camera, newest-frame delivery, health and reconnects.

Latency policy: every consumer gets a bounded slot of size one. When a consumer is slower than
the camera, the older undelivered frame is replaced (and counted as dropped for that consumer),
so frame age never grows without bound. A short ring buffer per camera (`recent`) keeps the
last few frames for timestamp pairing across cameras.
"""

from __future__ import annotations

import collections
import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Iterable

from .frame import CameraFrame
from .rig import CameraSpec, RigConfig
from .sources import FrameSource, make_source
from .sync import FrameSet, SyncMonitor, match_frameset

log = logging.getLogger(__name__)

STATES = ("idle", "connecting", "streaming", "stalled", "disconnected", "stopped")


class Subscription:
    """Newest-frame mailbox for one consumer of one camera."""

    def __init__(self, camera_id: str):
        self.camera_id = camera_id
        self._frame: CameraFrame | None = None
        self._cond = threading.Condition()
        self.delivered = 0
        self.dropped = 0
        self.closed = False

    def _put(self, frame: CameraFrame) -> None:
        with self._cond:
            if self._frame is not None:
                self.dropped += 1
            self._frame = frame
            self._cond.notify_all()

    def get(self, timeout: float | None = None) -> CameraFrame | None:
        """Block until a frame newer than the last one returned arrives (None on timeout/close)."""
        with self._cond:
            if self._frame is None and not self.closed:
                self._cond.wait(timeout)
            f, self._frame = self._frame, None
            if f is not None:
                self.delivered += 1
            return f

    def close(self) -> None:
        with self._cond:
            self.closed = True
            self._cond.notify_all()


@dataclass
class Stats:
    frames: int = 0
    missed: int = 0  # gaps in the camera's own frame cadence (> 1.5 frame periods)
    reconnects: int = 0
    fps: float = 0.0
    last_capture_ns: int | None = None
    last_receive_ns: int | None = None
    last_error: str | None = None
    pipeline_latency_ms: float | None = None  # receive - capture of the latest frame


class CameraWorker:
    def __init__(
        self,
        spec: CameraSpec,
        source_factory: Callable[[], FrameSource],
        calibration_version: Callable[[], str | None] = lambda: None,
        recent_len: int = 6,
        stall_timeout_s: float = 2.0,
        reconnect_backoff_s: tuple[float, float] = (0.5, 5.0),
    ):
        self.spec = spec
        self.source_factory = source_factory
        self.calibration_version = calibration_version
        self.stall_timeout_ns = int(stall_timeout_s * 1e9)
        self.backoff = reconnect_backoff_s
        self.state = "idle"
        self.stats = Stats()
        self.recent: collections.deque[CameraFrame] = collections.deque(maxlen=recent_len)
        self.source: FrameSource | None = None
        self._subs: list[Subscription] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._index = 0
        self.nominal_fps = spec.fps

    # ---- lifecycle -------------------------------------------------------------------
    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=f"cam-{self.spec.id}", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 3.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)
        self.state = "stopped"
        with self._lock:
            for s in self._subs:
                s.close()

    def _run(self) -> None:
        delay = self.backoff[0]
        while not self._stop.is_set():
            self.state = "connecting"
            src = None
            try:
                src = self.source_factory()
                src.open()
                self.source = src
                self.state = "streaming"
                delay = self.backoff[0]
                self._stream(src)
            except Exception as e:  # noqa: BLE001 - any device failure must lead to a reconnect, not a dead thread
                self.stats.last_error = f"{type(e).__name__}: {e}"
                log.warning("%s: %s", self.spec.id, self.stats.last_error)
            finally:
                if src is not None:
                    try:
                        src.close()
                    except Exception:  # noqa: BLE001
                        pass
            if self._stop.is_set():
                break
            self.state = "disconnected"
            self.stats.reconnects += 1
            log.warning("%s disconnected; reconnecting in %.1fs (id is kept: %s)", self.spec.id, delay, self.spec.id)
            self._stop.wait(delay)
            delay = min(delay * 2, self.backoff[1])

    def _stream(self, src: FrameSource) -> None:
        self.nominal_fps = src.nominal_fps or self.spec.fps
        period_ns = 1e9 / max(self.nominal_fps, 1e-3)
        while not self._stop.is_set():
            got = src.read()
            if got is None:
                self.stats.last_error = "read failed (unplugged, end of clip or driver error)"
                return
            img, capture_ns = got
            receive_ns = time.monotonic_ns()
            h, w = img.shape[:2]
            frame = CameraFrame(
                camera_id=self.spec.id,
                frame_index=self._index,
                capture_time_monotonic_ns=int(capture_ns),
                receive_time_monotonic_ns=receive_ns,
                frame_size=(w, h),
                image=img,
                calibration_version=self.calibration_version(),
                source_kind=src.kind,
            )
            self._index += 1
            st = self.stats
            if st.last_capture_ns is not None:
                dt = capture_ns - st.last_capture_ns
                if dt > 0:
                    inst = 1e9 / dt
                    st.fps = inst if st.fps == 0 else 0.9 * st.fps + 0.1 * inst
                    if dt > 1.5 * period_ns:
                        st.missed += int(round(dt / period_ns)) - 1
            st.frames += 1
            st.last_capture_ns, st.last_receive_ns = int(capture_ns), receive_ns
            st.pipeline_latency_ms = (receive_ns - capture_ns) / 1e6
            with self._lock:
                self.recent.append(frame)
                subs = list(self._subs)
            for s in subs:
                s._put(frame)

    # ---- consumers ---------------------------------------------------------------------
    def subscribe(self) -> Subscription:
        s = Subscription(self.spec.id)
        with self._lock:
            self._subs.append(s)
        return s

    def unsubscribe(self, s: Subscription) -> None:
        with self._lock:
            if s in self._subs:
                self._subs.remove(s)
        s.close()

    def latest(self) -> CameraFrame | None:
        with self._lock:
            return self.recent[-1] if self.recent else None

    def recent_frames(self) -> list[CameraFrame]:
        with self._lock:
            return list(self.recent)

    def health(self, now_ns: int | None = None) -> dict:
        now_ns = time.monotonic_ns() if now_ns is None else now_ns
        st = self.stats
        age = None if st.last_receive_ns is None else (now_ns - st.last_receive_ns) / 1e6
        state = self.state
        if state == "streaming" and (st.last_receive_ns is None or now_ns - st.last_receive_ns > self.stall_timeout_ns):
            state = "stalled"
        with self._lock:
            dropped = sum(s.dropped for s in self._subs)
        return {
            "camera_id": self.spec.id,
            "role": self.spec.role,
            "state": state,
            "fps": round(st.fps, 2),
            "nominal_fps": round(self.nominal_fps, 2),
            "frames": st.frames,
            "missed_frames": st.missed,
            "dropped_by_consumers": dropped,
            "reconnects": st.reconnects,
            "last_frame_age_ms": None if age is None else round(age, 1),
            "pipeline_latency_ms": None if st.pipeline_latency_ms is None else round(st.pipeline_latency_ms, 2),
            "last_error": st.last_error,
        }


class CameraHub:
    """All cameras of a rig. Camera ids come from the rig config, never from device order."""

    def __init__(
        self,
        rig: RigConfig,
        source_factories: dict[str, Callable[[], FrameSource]] | None = None,
        latency_ms: float = 0.0,
        calibration_version: str | None = None,
    ):
        self.rig = rig
        self.calibration_version = calibration_version
        self.epoch_ns = time.monotonic_ns() + int(0.2e9)  # shared timeline for recorded/synthetic sources
        self.sync_monitor = SyncMonitor(rig.camera_ids)
        self.workers: dict[str, CameraWorker] = {}
        for spec in rig.cameras:
            factory = (source_factories or {}).get(spec.id) or self._default_factory(spec, latency_ms)
            self.workers[spec.id] = CameraWorker(spec, factory, lambda: self.calibration_version)

    def _default_factory(self, spec: CameraSpec, latency_ms: float) -> Callable[[], FrameSource]:
        return lambda: make_source(spec, self.epoch_ns, latency_ms)

    def start(self) -> "CameraHub":
        for w in self.workers.values():
            w.start()
        return self

    def stop(self) -> None:
        for w in self.workers.values():
            w.stop()

    def __enter__(self) -> "CameraHub":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()

    def worker(self, camera_id: str) -> CameraWorker:
        if camera_id not in self.workers:
            raise KeyError(f"unknown camera id {camera_id!r}; known: {list(self.workers)}")
        return self.workers[camera_id]

    def latest(self, camera_id: str) -> CameraFrame | None:
        return self.worker(camera_id).latest()

    def subscribe(self, camera_id: str) -> Subscription:
        return self.worker(camera_id).subscribe()

    def frameset(self, tolerance_ms: float | None = None, camera_ids: Iterable[str] | None = None) -> FrameSet:
        """Best timestamp-matched set of frames across cameras (may be partial; see FrameSet.missing)."""
        ids = list(camera_ids or self.workers)
        tol = self.rig.pair_tolerance_ms if tolerance_ms is None else tolerance_ms
        recent = {cid: self.workers[cid].recent_frames() for cid in ids}
        fs = match_frameset(recent, int(tol * 1e6))
        self.sync_monitor.record(fs)
        return fs

    def wait_until_streaming(self, timeout: float = 10.0, min_frames: int = 1) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if all(w.stats.frames >= min_frames for w in self.workers.values()):
                return True
            time.sleep(0.02)
        return False

    def inventory(self) -> dict:
        now = time.monotonic_ns()
        cams = []
        for cid, w in self.workers.items():
            s = w.spec
            src = w.source.describe() if w.source is not None else {"kind": s.source.kind}
            latest = w.latest()
            cams.append({
                "camera_id": cid,
                "role": s.role,
                "requested": {"width": s.width, "height": s.height, "fps": s.fps, "fourcc": s.fourcc},
                "frame_size": None if latest is None else {"width": latest.frame_size[0], "height": latest.frame_size[1]},
                "source": src,
                "nominal_pose": {
                    "lens_position_world_m": [round(float(v), 4) for v in s.lens_position_m],
                    "R_world_to_camera": [[round(float(v), 6) for v in row] for row in s.R_world_to_camera],
                    "note": "design prior from the frame; use calibration for real geometry",
                },
                "health": w.health(now),
            })
        return {
            "schema": "phantom.camera_inventory",
            "schema_version": "1.0.0",
            "rig_name": self.rig.name,
            "timestamp_unix_ms": int(time.time() * 1000),
            "clock": "capture/receive times are host time.monotonic_ns; unix ms derived with a fixed per-process offset",
            "calibration_version": self.calibration_version,
            "cameras": cams,
        }

    def health(self) -> dict:
        """Low-rate summary suitable for agent 4 (Convex persistence / Cartesia speech)."""
        now = time.monotonic_ns()
        per = {cid: w.health(now) for cid, w in self.workers.items()}
        streaming = [cid for cid, h in per.items() if h["state"] == "streaming"]
        status = "ok" if len(streaming) == len(per) else ("degraded" if len(streaming) >= 2 else "unusable")
        return {
            "schema": "phantom.camera_health",
            "schema_version": "1.0.0",
            "timestamp_unix_ms": int(time.time() * 1000),
            "status": status,
            "streaming_cameras": streaming,
            "multiview_available": len(streaming) >= 2,
            "calibration_version": self.calibration_version,
            "cameras": per,
            "sync": self.sync_monitor.summary(),
        }
