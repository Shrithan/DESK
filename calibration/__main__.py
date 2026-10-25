"""Calibration command line. Run camera ingest first (`python -m camera serve`), then:

  python -m calibration board --out board.png              printable 9x6 board (print at 100 %, measure!)
  python -m calibration intrinsics --camera cam_1          wave the board in front of cam_1 (repeat per camera)
  python -m calibration extrinsics --square-mm 20.0        board face-up in the middle of the table
  python -m calibration verify --board-height-mm 0         re-check later / after bumps (drift)
  python -m calibration show                               summary of the current calibration
  python -m calibration synth-fixtures                     regenerate synthetic test clips + ground truth

Offline: --images DIR (intrinsics) or --images-dir DIR containing cam_1.png, cam_2.png, ... (extrinsics/verify).
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import shutil
import sys
import urllib.request
from pathlib import Path

import cv2
import numpy as np

from camera.rig import DEFAULT_RIG_CONFIG, REPO_ROOT, load_rig

from .board import Checkerboard
from .models import CameraIntrinsics, RigCalibration

DATA = REPO_ROOT / "calibration" / "data"
log = logging.getLogger("calibration")


def _board(args) -> Checkerboard:
    if args.square_mm is None:
        log.warning("--square-mm not given: assuming 20.0 mm. Printers rescale pages; MEASURE the squares, "
                    "otherwise every distance will be off by the same factor.")
    return Checkerboard(args.cols, args.rows, (args.square_mm or 20.0) / 1000)


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.loads(r.read())


def _snapshot(server: str, cam: str) -> np.ndarray | None:
    try:
        with urllib.request.urlopen(f"{server}/api/cameras/{cam}/snapshot.jpg?quality=95", timeout=5) as r:
            return cv2.imdecode(np.frombuffer(r.read(), np.uint8), cv2.IMREAD_COLOR)
    except OSError:
        return None


def _frameset_images(args, cam_ids: list[str]) -> dict[str, np.ndarray | None]:
    if args.images_dir:
        d = Path(args.images_dir)
        return {c: cv2.imread(str(d / f"{c}.png")) if (d / f"{c}.png").exists() else None for c in cam_ids}
    fs = _get_json(f"{args.server}/api/frameset?quality=95")
    imgs = {c: None for c in cam_ids}
    for c, f in fs["frames"].items():
        imgs[c] = cv2.imdecode(np.frombuffer(base64.b64decode(f["jpeg_base64"]), np.uint8), cv2.IMREAD_COLOR)
    if fs["missing"]:
        log.warning("no frame from %s", fs["missing"])
    return imgs


def cmd_board(args) -> None:
    b = _board(args)
    img = b.render_printable(dpi=args.dpi)
    cv2.imwrite(args.out, img)
    print(f"wrote {args.out} ({img.shape[1]}x{img.shape[0]} px at {args.dpi} dpi = "
          f"{img.shape[1] / args.dpi * 25.4:.0f} x {img.shape[0] / args.dpi * 25.4:.0f} mm). Print at 100 %/actual size, "
          f"tape it flat to stiff card, then measure 9 squares with a ruler and pass --square-mm.")


def cmd_intrinsics(args) -> None:
    from .intrinsics import calibrate_intrinsics, capture_views, detections_from_images, image_coverage

    board = _board(args)
    if args.images:
        paths = sorted(p for p in Path(args.images).iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg"))
        dets, size = detections_from_images(paths, board)
    else:
        save = DATA / "captures" / args.camera
        if save.exists():
            shutil.rmtree(save)
        print(f"Hold the board in front of {args.camera}: near/far, tilted, and in every corner of the image.")
        dets, size = capture_views(lambda: _snapshot(args.server, args.camera), board, args.views, args.timeout, save)
    intr = calibrate_intrinsics(dets, board, size)
    cov = image_coverage(dets, size)
    out = DATA / f"intrinsics_{args.camera}.json"
    intr.save(out, args.camera)
    print(json.dumps({"camera": args.camera, "image_size": size, "views": intr.num_views,
                      "rms_reprojection_px": round(intr.rms_reprojection_px, 4), "image_coverage": round(cov, 2),
                      "fx": round(float(intr.K[0, 0]), 2), "fy": round(float(intr.K[1, 1]), 2),
                      "cx": round(float(intr.K[0, 2]), 2), "cy": round(float(intr.K[1, 2]), 2),
                      "dist": np.round(intr.dist, 5).tolist(), "saved": str(out)}, indent=1))
    if intr.rms_reprojection_px > 0.8 or cov < 0.6:
        print("WARNING: high error or poor coverage; recapture with more varied views covering the image corners.")


def cmd_extrinsics(args) -> None:
    from .extrinsics import calibrate_extrinsics

    rig = load_rig(args.rig)
    board = _board(args)
    intr = {}
    idir = Path(args.intrinsics_dir) if args.intrinsics_dir else DATA
    for c in rig.camera_ids:
        p = idir / f"intrinsics_{c}.json"
        if not p.exists():
            sys.exit(f"missing {p}: run `python -m calibration intrinsics --camera {c}` first")
        intr[c] = CameraIntrinsics.load(p)[1]
    imgs = _frameset_images(args, rig.camera_ids)
    dets = {}
    for c, img in imgs.items():
        if img is not None and (img.shape[1], img.shape[0]) != (intr[c].image_width, intr[c].image_height):
            sys.exit(f"{c}: frame is {img.shape[1]}x{img.shape[0]} but intrinsics are for "
                     f"{intr[c].image_width}x{intr[c].image_height}; recalibrate intrinsics at this resolution")
        dets[c] = None if img is None else board.detect(img)
        print(f"{c}: board {'found' if dets[c] is not None else 'NOT found'}")
    nominal = {c.id: c.lens_position_m for c in rig.cameras}
    cal = calibrate_extrinsics(dets, intr, board, rig.name, nominal, board_height_m=args.board_height_mm / 1000)
    out = Path(args.out) if args.out else rig.calibration_file
    cid = cal.save(out)
    if not args.no_history:
        hist = DATA / "history"
        hist.mkdir(parents=True, exist_ok=True)
        shutil.copy(out, hist / f"{cid}.json")
    print(json.dumps({"calibration_id": cid, "saved": str(out), **cal.validation}, indent=1))
    print("Restart `python -m camera serve` so frames carry the new calibration_version.")


def cmd_verify(args) -> None:
    from .extrinsics import verify_board

    rig = load_rig(args.rig)
    cal = RigCalibration.load(args.calibration or rig.calibration_file)
    board = _board(args)
    imgs = _frameset_images(args, list(cal.cameras))
    dets = {c: (None if im is None else board.detect(im)) for c, im in imgs.items()}
    print(json.dumps({"calibration_id": cal.calibration_id, **verify_board(cal, dets, board, args.board_height_mm / 1000)}, indent=1))


def cmd_show(args) -> None:
    rig = load_rig(args.rig)
    cal = RigCalibration.load(args.calibration or rig.calibration_file)
    print(f"calibration {cal.calibration_id} ({cal.rig_name})")
    for cid, c in cal.cameras.items():
        e = c.extrinsics
        pos = "no extrinsics" if e is None else f"centre {np.round(e.camera_center_world_m, 3).tolist()} m, axis {np.round(e.optical_axis_world, 3).tolist()}"
        print(f"  {cid}: {c.intrinsics.image_width}x{c.intrinsics.image_height} fx={c.K[0, 0]:.1f} "
              f"rms={c.intrinsics.rms_reprojection_px}  {pos}")
    print(json.dumps(cal.validation, indent=1))


def cmd_synth(args) -> None:
    from .synthetic import write_fixtures

    out = Path(args.out)
    info = write_fixtures(out, seconds=args.seconds, fps=args.fps)
    print(f"wrote synthetic fixtures to {out}: {info}")


def main() -> None:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--rig", default=str(DEFAULT_RIG_CONFIG))
    common.add_argument("--server", default="http://127.0.0.1:8100", help="camera ingest server")
    common.add_argument("--cols", type=int, default=9)
    common.add_argument("--rows", type=int, default=6)
    common.add_argument("--square-mm", type=float, default=None, help="MEASURED printed square size in mm")
    ap = argparse.ArgumentParser(prog="python -m calibration", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("board", parents=[common])
    p.add_argument("--out", default="checkerboard_9x6.png")
    p.add_argument("--dpi", type=int, default=300)
    p.set_defaults(func=cmd_board)
    p = sub.add_parser("intrinsics", parents=[common])
    p.add_argument("--camera", required=True)
    p.add_argument("--images", help="calibrate from a folder of images instead of the live server")
    p.add_argument("--views", type=int, default=20)
    p.add_argument("--timeout", type=float, default=300)
    p.set_defaults(func=cmd_intrinsics)
    for name, fn in (("extrinsics", cmd_extrinsics), ("verify", cmd_verify)):
        p = sub.add_parser(name, parents=[common])
        p.add_argument("--images-dir", help="folder with cam_1.png ... instead of the live server")
        p.add_argument("--board-height-mm", type=float, default=0.0, help="board raised on a block of this height")
        p.add_argument("--calibration", help="calibration JSON (default: rig config's calibration_file)")
        if name == "extrinsics":
            p.add_argument("--out", help="where to write the rig calibration (default: rig config's calibration_file)")
            p.add_argument("--intrinsics-dir", help="folder with intrinsics_<cam>.json (default: calibration/data)")
            p.add_argument("--no-history", action="store_true", help="don't archive a copy in calibration/data/history")
        p.set_defaults(func=fn)
    p = sub.add_parser("show", parents=[common])
    p.add_argument("--calibration")
    p.set_defaults(func=cmd_show)
    p = sub.add_parser("synth-fixtures", parents=[common])
    p.add_argument("--out", default=str(REPO_ROOT / "camera" / "fixtures" / "synthetic_rig"))
    p.add_argument("--seconds", type=float, default=4.0)
    p.add_argument("--fps", type=float, default=15.0)
    p.set_defaults(func=cmd_synth)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format='{"t":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}')
    args.func(args)


if __name__ == "__main__":
    main()
