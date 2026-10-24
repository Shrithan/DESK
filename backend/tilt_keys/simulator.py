"""Fake tilt_update producer so tilt-to-keys works without cameras.

Scripted mode, JSON lines to stdout (pipe into the runner):
    python -m backend.tilt_keys.simulator scripted --noise 0.5 | python -m backend.tilt_keys.run --input stdin

Interactive mode (arrow keys), sends to a runner started with --input ws:
    python -m backend.tilt_keys.run --input ws          # terminal 1
    python -m backend.tilt_keys.simulator interactive   # terminal 2
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass

from backend.tilt_keys.backends import json_line, now_unix_ms


@dataclass(frozen=True)
class Segment:
    label: str
    forward_deg: float
    right_deg: float
    duration_s: float
    can_found: bool = True


# The first segment doubles as the runner's 2 s neutral calibration window.
SCRIPTED: tuple[Segment, ...] = (
    Segment("upright (hold still: calibrating)", 0, 0, 2.5),
    Segment("upright", 0, 0, 1.0),
    Segment("forward 20 deg  -> expect W down", 20, 0, 1.5),
    Segment("forward 12 deg  -> expect W still held", 12, 0, 1.5),
    Segment("forward 8 deg   -> expect W up", 8, 0, 1.5),
    Segment("left 25 deg     -> expect A down", 0, -25, 1.5),
    Segment("forward+left    -> expect W+A", 20, -25, 1.5),
    Segment("can lost        -> expect all up", 20, -25, 1.0, can_found=False),
    Segment("upright         -> expect nothing", 0, 0, 1.5),
)


def scripted_frames(
    segments: tuple[Segment, ...] = SCRIPTED,
    *,
    rate_hz: float = 30.0,
    noise_deg: float = 0.0,
    bias_forward_deg: float = 0.0,
    bias_right_deg: float = 0.0,
    seed: int = 0,
    start_ms: int | None = None,
) -> Iterator[tuple[float, str | None, dict]]:
    """Yield (seconds since start, segment label on its first frame else None, tilt_update dict)."""
    rng = random.Random(seed)
    start_ms = now_unix_ms() if start_ms is None else start_ms
    period = 1.0 / rate_hz
    t = 0.0
    for seg in segments:
        n = max(1, round(seg.duration_s * rate_hz))
        for i in range(n):
            if seg.can_found:
                fwd = seg.forward_deg + bias_forward_deg + rng.gauss(0, noise_deg)
                rgt = seg.right_deg + bias_right_deg + rng.gauss(0, noise_deg)
                fwd, rgt = round(fwd, 3), round(rgt, 3)
            else:
                fwd = rgt = None
            msg = {
                "type": "tilt_update",
                "schema_version": "1.0.0",
                "timestamp_ms": start_ms + round(t * 1000),
                "forward_deg": fwd,
                "right_deg": rgt,
                "can_found": seg.can_found,
            }
            yield t, (seg.label if i == 0 else None), msg
            t += period


def run_scripted(args: argparse.Namespace) -> None:
    t_start = time.monotonic()
    for t, label, msg in scripted_frames(
        rate_hz=args.rate, noise_deg=args.noise, bias_forward_deg=args.bias_forward,
        bias_right_deg=args.bias_right, seed=args.seed,
    ):
        delay = t_start + t - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        msg["timestamp_ms"] = now_unix_ms()  # real wall-clock timestamps when paced live
        if label:
            print(f"--- sim: {label}", file=sys.stderr, flush=True)
        print(json_line(msg), flush=True)


def run_interactive(args: argparse.Namespace) -> None:
    import curses

    from websockets.sync.client import connect

    with connect(args.url) as ws:
        curses.wrapper(lambda scr: _interactive_loop(scr, ws, args))


def _interactive_loop(scr, ws, args: argparse.Namespace) -> None:
    import curses

    curses.curs_set(0)
    scr.timeout(round(1000 / args.rate))
    fwd = rgt = 0.0
    found = True
    rng = random.Random(args.seed)
    help_text = (
        "arrows: tilt (up=forward, down=back, left/right)   space: upright   "
        "l: toggle can lost   c: recalibrate   e: enable/disable   q: quit"
    )
    while True:
        ch = scr.getch()
        cmd = None
        if ch in (ord("q"), 27):
            break
        elif ch == curses.KEY_UP:
            fwd += args.step
        elif ch == curses.KEY_DOWN:
            fwd -= args.step
        elif ch == curses.KEY_RIGHT:
            rgt += args.step
        elif ch == curses.KEY_LEFT:
            rgt -= args.step
        elif ch == ord(" "):
            fwd = rgt = 0.0
        elif ch == ord("l"):
            found = not found
        elif ch == ord("c"):
            cmd = "recalibrate"
        elif ch == ord("e"):
            cmd = "toggle"
        if cmd:
            ws.send(json_line({"type": "tilt_command", "timestamp_ms": now_unix_ms(), "command": cmd}))
        noisy = lambda v: round(v + rng.gauss(0, args.noise), 3)  # noqa: E731
        ws.send(json_line({
            "type": "tilt_update", "schema_version": "1.0.0", "timestamp_ms": now_unix_ms(),
            "forward_deg": noisy(fwd) if found else None, "right_deg": noisy(rgt) if found else None,
            "can_found": found,
        }))
        scr.erase()
        scr.addstr(0, 0, help_text[: curses.COLS - 1])
        scr.addstr(2, 0, f"forward_deg = {fwd:+6.1f}   right_deg = {rgt:+6.1f}   can_found = {found}")
        scr.addstr(3, 0, f"sending to {args.url} at {args.rate:.0f} Hz" + (f" (last command: {cmd})" if cmd else ""))
        scr.refresh()


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="mode", required=True)
    for name in ("scripted", "interactive"):
        sp = sub.add_parser(name)
        sp.add_argument("--rate", type=float, default=30.0, help="updates per second (default 30)")
        sp.add_argument("--noise", type=float, default=0.0, help="gaussian jitter std dev in degrees")
        sp.add_argument("--seed", type=int, default=0)
    s = sub.choices["scripted"]
    s.add_argument("--bias-forward", type=float, default=0.0, help="constant lean added to forward (tests calibration)")
    s.add_argument("--bias-right", type=float, default=0.0, help="constant lean added to right (tests calibration)")
    i = sub.choices["interactive"]
    i.add_argument("--url", default="ws://127.0.0.1:8765/ws/tilt")
    i.add_argument("--step", type=float, default=5.0, help="degrees per arrow press")
    args = p.parse_args(argv)
    try:
        run_scripted(args) if args.mode == "scripted" else run_interactive(args)
    except (BrokenPipeError, KeyboardInterrupt):
        pass


if __name__ == "__main__":
    main()
