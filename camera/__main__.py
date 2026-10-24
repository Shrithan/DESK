"""Command line for camera ingest.

  python -m camera devices                      list attached cameras and their stable ids
  python -m camera serve                        run ingest + diagnostics page on :8100
  python -m camera serve --fixture synthetic    no cameras needed (moving test pattern)
  python -m camera serve --video-dir camera/fixtures/synthetic_rig   play recorded clips as cameras
  python -m camera identify                     print per-camera brightness; cover lenses to confirm ids
  python -m camera record --seconds 10 --out recordings/run1   save timestamped clips (offline fallback)
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

from .rig import DEFAULT_RIG_CONFIG, load_rig

log = logging.getLogger("camera")


def _rig_from_args(args) -> "RigConfig":  # noqa: F821
    overrides = None
    if getattr(args, "fixture", None) == "synthetic":
        overrides = {cid: {"kind": "synthetic"} for cid in load_rig(args.rig).camera_ids}
    elif getattr(args, "video_dir", None):
        d = Path(args.video_dir)
        overrides = {cid: {"kind": "video", "path": str(d / f"{cid}.mp4")} for cid in load_rig(args.rig).camera_ids}
    return load_rig(args.rig, overrides)


def _calibration_version(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        from calibration.models import RigCalibration

        return RigCalibration.load(path).calibration_id
    except Exception as e:  # noqa: BLE001 - a bad calibration file must not stop the cameras
        log.error("ignoring calibration %s: %s", path, e)
        return None


def cmd_devices(args) -> None:
    from .devices import list_devices

    devs = list_devices()
    if not devs:
        print("no cameras found")
    for d in devs:
        print(json.dumps(d.to_dict()))
    print("\nPut unique_id (macOS) or linux_by_path (Linux) into camera/config/rig_c270.json for each cam_N.")


def cmd_serve(args) -> None:
    import uvicorn

    from .ingest import CameraHub
    from .server import create_app

    rig = _rig_from_args(args)
    cal_path = Path(args.calibration) if args.calibration else rig.calibration_file
    hub = CameraHub(rig, latency_ms=args.latency_ms, calibration_version=_calibration_version(cal_path)).start()
    log.info("cameras: %s; diagnostics on http://%s:%d/", rig.camera_ids, args.host, args.port)
    try:
        uvicorn.run(create_app(hub, cal_path), host=args.host, port=args.port, log_level="warning")
    finally:
        hub.stop()


def cmd_identify(args) -> None:
    import cv2

    from .ingest import CameraHub

    rig = _rig_from_args(args)
    with CameraHub(rig) as hub:
        hub.wait_until_streaming(10)
        print("Cover one lens at a time; the matching id should drop to ~0. Ctrl-C to stop.")
        try:
            while True:
                parts = []
                for cid in rig.camera_ids:
                    f = hub.latest(cid)
                    v = None if f is None else float(cv2.cvtColor(f.image, cv2.COLOR_BGR2GRAY).mean())
                    parts.append(f"{cid}: {'--' if v is None else f'{v:5.1f}'}")
                print("  ".join(parts), end="\r", flush=True)
                time.sleep(0.2)
        except KeyboardInterrupt:
            print()


def cmd_record(args) -> None:
    import cv2

    from .ingest import CameraHub

    rig = _rig_from_args(args)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with CameraHub(rig, latency_ms=args.latency_ms) as hub:
        if not hub.wait_until_streaming(10):
            log.warning("not every camera is streaming; recording what is available")
        subs = {cid: hub.subscribe(cid) for cid in rig.camera_ids}
        writers, times = {}, {cid: [] for cid in rig.camera_ids}
        end = time.monotonic() + args.seconds
        while time.monotonic() < end:
            for cid, s in subs.items():
                f = s.get(timeout=0.01)
                if f is None:
                    continue
                if cid not in writers:
                    w, h = f.frame_size
                    writers[cid] = cv2.VideoWriter(str(out / f"{cid}.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), rig.camera(cid).fps, (w, h))
                writers[cid].write(f.image)
                times[cid].append(f.capture_time_monotonic_ns)
        for cid, w in writers.items():
            w.release()
            t = times[cid]
            (out / f"{cid}.json").write_text(json.dumps({
                "camera_id": cid, "frames": len(t), "frame_times_ns": [x - t[0] for x in t],
                "first_capture_time_monotonic_ns": t[0], "capture_offset_ms": 0.0,
            }))
        for cid, s in subs.items():
            print(f"{cid}: {len(times[cid])} frames, dropped by recorder {s.dropped}")
    print(f"saved to {out}; replay with: python -m camera serve --video-dir {out}")


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m camera", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rig", default=str(DEFAULT_RIG_CONFIG))
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_sources(p):
        g = p.add_mutually_exclusive_group()
        g.add_argument("--fixture", choices=["synthetic"], help="use a synthetic pattern instead of cameras")
        g.add_argument("--video-dir", help="directory with cam_1.mp4, cam_2.mp4, ... to play as cameras")
        p.add_argument("--latency-ms", type=float, default=0.0, help="assumed USB capture latency subtracted from receive time")

    sub.add_parser("devices").set_defaults(func=cmd_devices)
    p = sub.add_parser("serve")
    add_sources(p)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8100)
    p.add_argument("--calibration", help="rig calibration JSON (default: rig config's calibration_file)")
    p.set_defaults(func=cmd_serve)
    p = sub.add_parser("identify")
    add_sources(p)
    p.set_defaults(func=cmd_identify)
    p = sub.add_parser("record")
    add_sources(p)
    p.add_argument("--seconds", type=float, default=10.0)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_record)

    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format='{"t":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}')
    args.func(args)


if __name__ == "__main__":
    main()
