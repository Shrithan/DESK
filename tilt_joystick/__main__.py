"""Can-tilt joystick -> held W/A/S/D keys.

    python -m tilt_joystick --camera 0 --dry-run            # no real key presses, log only
    python -m tilt_joystick --camera 0                      # real keys (macOS: Accessibility permission)
    python -m tilt_joystick --camera 0 --calibrate-direction  # also learn W/D directions
    python -m tilt_joystick --camera 0 --record runs/a.jsonl   # save per-frame mask features
    python -m tilt_joystick --replay runs/a.jsonl           # deterministic replay, prints key events
    python -m tilt_joystick --camera 0 --control            # + agent control API for the DESK Fetch.ai agents
"""
from __future__ import annotations

import argparse
import atexit
import json
import logging
import signal
import sys
import threading
import time
from collections import deque
from pathlib import Path

import numpy as np

from backend.tilt_keys.backends import LogKeyBackend, macos_accessibility_trusted
from tilt_joystick.bus import EventBus, JsonlSink
from tilt_joystick.config import load_config
from tilt_joystick.pipeline import TiltPipeline, load_direction, replay

log = logging.getLogger('tilt_joystick')
DEFAULT_CONFIG = Path(__file__).with_name('tilt_joystick.toml')


class LatestFrame:
    """Background grabber that keeps only the newest frame, so we never process a stale buffer."""

    def __init__(self, source, width=1280, height=720) -> None:
        import cv2
        self.cap = cv2.VideoCapture(int(source) if str(source).isdigit() else str(source))
        if not self.cap.isOpened():
            raise SystemExit(f'cannot open camera/video {source!r}')
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.live = str(source).isdigit()
        self.frame, self.t, self.id = None, 0.0, 0
        self.cond = threading.Condition()
        self.running = True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        while self.running:
            ok, frame = self.cap.read()
            t = time.perf_counter()
            with self.cond:
                if not ok:
                    self.running = False
                else:
                    self.frame, self.t, self.id = frame, t, self.id + 1
                self.cond.notify_all()
            if not self.live:
                time.sleep(1 / 30)

    def next(self, last_id: int):
        with self.cond:
            self.cond.wait_for(lambda: self.id != last_id or not self.running, timeout=1.0)
            return self.frame, self.t, self.id

    def close(self) -> None:
        self.running = False
        self.cap.release()


def make_backend(dry_run: bool):
    if dry_run:
        return LogKeyBackend()
    from backend.tilt_keys.backends import PynputKeyBackend
    if macos_accessibility_trusted() is False:
        print('\n*** macOS Accessibility permission is missing: key presses will be dropped. ***\n'
              'System Settings > Privacy & Security > Accessibility: enable your terminal app, then restart it.\n'
              'Or run with --dry-run.\n', file=sys.stderr)
    return PynputKeyBackend()


def start_pause_hotkey(name: str, toggle) -> object | None:
    try:
        from pynput import keyboard
        return keyboard.GlobalHotKeys({f'<{name}>': toggle}).__enter__()
    except Exception as exc:  # pynput missing or no Input Monitoring permission
        log.warning('global pause hotkey unavailable (%s); use space in the window', exc)
        return None


class Processor:
    """Camera thread: newest frame -> detector -> pipeline (keys). The UI thread only reads `latest`,
    so drawing and window events never delay a key."""

    def __init__(self, camera, detector, pipeline, width: int, record, budget_ms: float) -> None:
        self.camera, self.detector, self.pipeline = camera, detector, pipeline
        self.width, self.record, self.budget = width, record, budget_ms
        self.latest = None  # (frame, det, state, held)
        self.stats: dict = {'mode': detector.mode}
        self.running = True
        self.error: BaseException | None = None
        self.reset_requested = False  # set by the UI thread; applied here so the detector has one owner
        self.thread = threading.Thread(target=self._run, daemon=True, name='can-joystick')

    def _run(self) -> None:
        import cv2
        e2e, stamps, stage_sum, n, last_print, last_id = deque(maxlen=300), deque(maxlen=60), {}, 0, time.perf_counter(), -1
        try:
            while self.running:
                prev_id = last_id
                frame, t_cap, last_id = self.camera.next(prev_id)
                if frame is None or last_id == prev_id:  # stalled/ended: the dropout rule releases keys
                    self.pipeline.step(None, time.perf_counter() * 1000)
                    if not self.camera.running:
                        break
                    continue
                if self.reset_requested:
                    self.reset_requested = False
                    self.detector.reset_lock()
                t0 = time.perf_counter()
                if frame.shape[1] != self.width:
                    frame = cv2.resize(frame, (self.width, round(frame.shape[0] * self.width / frame.shape[1])),
                                       interpolation=cv2.INTER_AREA)
                t1 = time.perf_counter()
                det, feats = self.detector.track(frame)
                t2 = time.perf_counter()
                state = self.pipeline.step(feats, t_cap * 1000)
                t3 = time.perf_counter()  # key events have been sent
                self.latest = (frame, det, state, self.pipeline.held)
                if self.record:
                    self.record.write(json.dumps({'t_ms': round(t_cap * 1000, 2), 'f': feats.to_dict() if feats else None}) + '\n')
                e2e.append((t3 - t_cap) * 1000)
                stamps.append(t3)
                for name, v in (('queue', t0 - t_cap), ('resize', t1 - t0), ('track', t2 - t1), ('keys', t3 - t2)):
                    stage_sum[name] = stage_sum.get(name, 0) + v * 1000
                n += 1
                if len(stamps) > 1:
                    self.stats.update(fps=(len(stamps) - 1) / (stamps[-1] - stamps[0]), e2e_ms=float(np.mean(e2e)),
                                      e2e_p95=float(np.percentile(e2e, 95)), model_ms=self.detector.model_ms,
                                      flow_ms=self.detector.flow_ms)
                if t3 - last_print >= 1.0:
                    parts = '  '.join(f'{k} {v / n:.1f}' for k, v in stage_sum.items())
                    over = '  OVER BUDGET' if self.stats.get('e2e_p95', 0) > self.budget else ''
                    print(f"fps {self.stats.get('fps', 0):5.1f} | frame->key mean {self.stats.get('e2e_ms', 0):.1f} ms "
                          f"p95 {self.stats.get('e2e_p95', 0):.1f} ms{over} | ms/frame: {parts} | model {self.detector.model_ms:.0f} ms "
                          f"(background) | {state.status} held={sorted(self.pipeline.held)}", flush=True)
                    stage_sum, n, last_print = {}, 0, t3
        except BaseException as exc:  # never leave a key down because the camera thread died
            self.error = exc
            log.exception('processing thread failed')
        finally:
            self.pipeline.release_all()
            self.running = False


def run_live(args, config, pipeline: TiltPipeline) -> None:
    import cv2
    from tilt_joystick.detector import CanDetector
    from tilt_joystick.overlay import Overlay

    detector = CanDetector(config.detector)
    print(f'detector: {detector.describe()}' + (f"  ({'; '.join(detector.notes)})" if detector.notes else ''))
    width = config.detector.proc_width
    camera = LatestFrame(args.camera, width, round(width * 3 / 4))  # C270: 640x480 is a native mode
    overlay = Overlay(config.keys)
    record = open(args.record, 'w') if args.record else None
    hotkey = start_pause_hotkey(config.keys.pause_hotkey, lambda: pipeline.set_paused(not pipeline.paused))
    proc = Processor(camera, detector, pipeline, width, record, config.latency_budget_ms)
    proc.thread.start()
    try:
        while proc.running:
            if proc.latest is not None:
                frame, det, state, held = proc.latest
                cv2.imshow('Can joystick', overlay.draw(frame, det, pipeline.estimator, state, held, pipeline.paused, proc.stats))
            key = cv2.waitKey(15) & 0xFF
            if key in (ord('q'), 27):
                break
            if key == ord(' '):
                pipeline.set_paused(not pipeline.paused)
            elif key in (ord('c'), ord('r')):
                proc.reset_requested = True
                pipeline.recalibrate(direction=key == ord('r'))
    finally:
        proc.running = False
        pipeline.close()
        proc.thread.join(timeout=1)
        detector.close()
        camera.close()
        if hotkey is not None:
            hotkey.stop()
        if record:
            record.close()
        cv2.destroyAllWindows()
    if proc.error:
        raise proc.error


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--camera', default='0', help='camera index or a video file')
    ap.add_argument('--config', default=str(DEFAULT_CONFIG))
    ap.add_argument('--dry-run', action='store_true', help='log key events instead of pressing keys')
    ap.add_argument('--calibrate-direction', action='store_true', help='after neutral: tilt toward W, then D')
    ap.add_argument('--record', help='write per-frame mask features to this JSONL for replay')
    ap.add_argument('--replay', help='replay a recorded JSONL (no camera, no model; always dry-run)')
    ap.add_argument('--events-log', help='append every bus event (joystick, key_down, key_up) as JSONL')
    ap.add_argument('--control', action='store_true',
                    help='serve the DESK agent control API on ws://127.0.0.1:PORT/ws/control (python -m agents.run)')
    ap.add_argument('--control-port', type=int, default=8766)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')
    config = load_config(args.config if Path(args.config).exists() else None)
    bus = EventBus()
    if args.events_log:
        bus.subscribe('*', JsonlSink(open(args.events_log, 'a')))
    direction = load_direction()
    backend = make_backend(args.dry_run or bool(args.replay))
    pipeline = TiltPipeline(config, backend, bus, direction, args.calibrate_direction)
    atexit.register(pipeline.close)  # last line of defence: never leave a key held
    control_server = None
    if args.control:
        from tilt_joystick.agent_control import JoystickControlService, serve_control
        control_server = serve_control(JoystickControlService(pipeline), port=args.control_port)
        print(f'agent control API: ws://127.0.0.1:{args.control_port}/ws/control  (start the agents with python -m agents.run)')
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        if args.replay:
            frames = replay(args.replay, pipeline)
            print(f'replayed {len(frames)} frames; final status {frames[-1][2].status if frames else "-"}')
        else:
            run_live(args, config, pipeline)
    except KeyboardInterrupt:
        pass
    finally:
        pipeline.close()
        if control_server is not None:
            control_server.shutdown()
    return 0


if __name__ == '__main__':
    sys.exit(main())
