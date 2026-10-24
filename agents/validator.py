"""Decide whether a recent setting change should stay after live play."""

from __future__ import annotations

from agents.tuning import _axis_numbers, compare


def assess(before: dict, after: dict, kind: str) -> tuple[str, list[str]]:
    """Return keep, undo, or inconclusive using rate-normalized evidence."""
    b_frames, a_frames = before.get("frames", 0), after.get("frames", 0)
    bw, aw = max(float(before.get("window_s") or 1), 1), max(float(after.get("window_s") or 1), 1)
    evidence = [f"Frames: {b_frames} in {bw:g}s before, {a_frames} in {aw:g}s after"]
    if b_frames >= 60 and a_frames < 30:
        return "undo", evidence + ["Tracking stopped after the change"]
    if a_frames < 60:
        return "inconclusive", evidence + ["Too little play to judge the change safely"]
    b_loss = 60 * before.get("tracking_lost", 0) / bw
    a_loss = 60 * after.get("tracking_lost", 0) / aw
    if a_loss >= max(3, b_loss * 2) and a_loss > b_loss:
        return "undo", evidence + [f"Tracking losses per minute rose from {b_loss:.1f} to {a_loss:.1f}"]
    if kind == "tune":
        evidence += compare(before, after)
        worse = False
        for axis in ("forward", "right"):
            _, bf, *_ = _axis_numbers(before, axis)
            _, af, *_ = _axis_numbers(after, axis)
            old, new = 60 * bf / bw, 60 * af / aw
            if af >= 3 and new >= max(old * 1.5, old + 3):
                worse = True
        if worse:
            return "undo", evidence + ["Short accidental presses increased"]
    return "keep", evidence
