"""Tuning agent logic: read real telemetry, decide new thresholds, explain why.

Pure functions, no I/O. The rule of thumb:
* Flicker (a key pressed and released within ~250 ms) means the trigger sits
  inside the player's natural wobble, so raise it above the wobble.
* Never raise it past ~80% of the furthest the player actually tilts, or they
  could not trigger the key at all.
* "Not responding" with tilts that come close but never cross means lower it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Direction = Literal["less", "more", "auto"]
Axis = Literal["forward", "right"]
AXIS_KEYS = {"forward": ("forward", "back"), "right": ("left", "right")}
AXIS_NAME = {"forward": "forward/back", "right": "left/right"}
STEP_DEG = 5.0
GAP_DEG = 5.0
MIN_ON, MAX_ON = 8.0, 35.0
MIN_FRAMES = 60  # ~2 s at 30 Hz


@dataclass
class AxisChange:
    axis: Axis
    before: tuple[float, float]
    after: tuple[float, float]
    evidence: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.before != self.after


@dataclass
class TuningPlan:
    changes: list[AxisChange]
    patch: dict
    summary: str
    notes: list[str] = field(default_factory=list)


def _clamp_on(v: float) -> float:
    return round(min(MAX_ON, max(MIN_ON, v)), 1)


def _axis_numbers(telemetry: dict, axis: Axis) -> tuple[int, int, float | None, float | None, float | None]:
    keys_cfg = telemetry["config"]["keys"]
    stats = telemetry.get(axis, {})
    presses = flickers = 0
    for slot in AXIS_KEYS[axis]:
        k = telemetry.get("keys", {}).get(keys_cfg[slot], {})
        presses += k.get("presses", 0)
        flickers += k.get("flickers", 0)
    reach = max(v for v in (stats.get("max_pos_deg"), stats.get("max_neg_deg"), 0.0) if v is not None)
    return presses, flickers, stats.get("abs_p50_deg"), stats.get("abs_p90_deg"), reach or None


def plan_axis(telemetry: dict, axis: Axis, direction: Direction) -> AxisChange:
    cfg = telemetry["config"]["forward_back" if axis == "forward" else "left_right"]
    on, off = float(cfg["on_deg"]), float(cfg["off_deg"])
    presses, flickers, p50, p90, reach = _axis_numbers(telemetry, axis)
    frames = telemetry.get("frames", 0)
    ev: list[str] = []
    name = AXIS_NAME[axis]
    if frames >= MIN_FRAMES:
        ev.append(f"{name}: {presses} key presses in the last {telemetry.get('window_s', 60):g}s, {flickers} of them flickers (released in under 0.25s)")
        if p50 is not None:
            ev.append(f"{name}: your typical tilt is {p50:g}°, 90% of the time under {p90:g}°, furthest {reach or 0:g}°")
    flicker_ratio = flickers / presses if presses else 0.0

    if direction == "auto":
        if frames < MIN_FRAMES:
            return AxisChange(axis, (on, off), (on, off), ev)
        if flickers >= 4 and flicker_ratio >= 0.3:
            direction = "less"
        elif presses == 0 and reach is not None and on * 0.6 <= reach <= on:
            direction = "more"
            ev.append(f"{name}: you tilted up to {reach:g}° but the trigger is {on:g}°, so nothing fired")
        else:
            return AxisChange(axis, (on, off), (on, off), ev)

    if direction == "less":
        target = on + STEP_DEG
        if p50 is not None and frames >= MIN_FRAMES and flickers:
            # get the trigger clear of the everyday wobble
            target = max(target, round(p50 * 1.6 + 4))
        if reach and frames >= MIN_FRAMES and target > reach * 0.85 and reach * 0.85 > on:
            target = reach * 0.85
            ev.append(f"{name}: capped at {target:.0f}° so your full tilt ({reach:g}°) still triggers it")
        new_on = _clamp_on(target)
    else:
        target = on - STEP_DEG
        if reach and frames >= MIN_FRAMES and presses == 0:
            target = min(target, reach * 0.8)
        new_on = _clamp_on(target)
    # When calming a twitchy axis, keep its existing release point. Raising
    # OFF along with ON preserves a narrow hysteresis band and can turn a
    # brief dip during an intentional turn into another flicker.
    release = min(off, new_on - GAP_DEG) if direction == "less" else new_on - GAP_DEG
    new_off = round(max(2.0, release), 1)
    return AxisChange(axis, (on, off), (new_on, new_off), ev)


def plan_tuning(telemetry: dict, direction: Direction = "auto", axis: Axis | None = None) -> TuningPlan:
    axes: list[Axis] = [axis] if axis else ["forward", "right"]
    if direction != "auto" and axis is None:
        # "less sensitive" with no axis: pick the twitchier axis if the data says so, else both
        scored = sorted(axes, key=lambda a: _axis_numbers(telemetry, a)[1], reverse=True)
        top_flicker = _axis_numbers(telemetry, scored[0])[1]
        if direction == "less" and top_flicker >= 4 and top_flicker > 2 * _axis_numbers(telemetry, scored[1])[1]:
            axes = [scored[0]]
    changes = [plan_axis(telemetry, a, direction) for a in axes]
    patch: dict = {}
    fb = telemetry["config"]["forward_back"]
    lr = telemetry["config"]["left_right"]
    lr_new = (lr["on_deg"], lr["off_deg"])
    fb_new = (fb["on_deg"], fb["off_deg"])
    for ch in changes:
        if ch.changed:
            if ch.axis == "forward":
                fb_new = ch.after
            else:
                lr_new = ch.after
    if fb_new != (fb["on_deg"], fb["off_deg"]):
        patch.update(on_threshold_deg=fb_new[0], off_threshold_deg=fb_new[1])
    if patch or lr_new != (lr["on_deg"], lr["off_deg"]):
        # always pin left/right explicitly so a forward change never moves steering
        patch.update(lr_on_threshold_deg=lr_new[0], lr_off_threshold_deg=lr_new[1])
        if lr_new == (lr["on_deg"], lr["off_deg"]) and "on_threshold_deg" not in patch:
            patch = {}
    notes = []
    if telemetry.get("frames", 0) < MIN_FRAMES:
        notes.append("I only have a few seconds of play data, so I made a standard 5° step instead of a data-driven one. Play for 30 seconds and ask again for a precise tune.")
    moved = [c for c in changes if c.changed]
    if not moved:
        summary = "Your settings already look right for how you tilt; no change needed."
    else:
        parts = [f"{AXIS_NAME[c.axis]} trigger {c.before[0]:g}° → {c.after[0]:g}°" for c in moved]
        summary = "Changed " + " and ".join(parts) + "."
    return TuningPlan(changes, patch, summary, notes)


def compare(before: dict, after: dict) -> list[str]:
    """Before/after flicker comparison for the 'check results' step."""
    lines = []
    for axis in ("forward", "right"):
        bp, bf, *_ = _axis_numbers(before, axis)  # type: ignore[arg-type]
        ap, af, *_ = _axis_numbers(after, axis)  # type: ignore[arg-type]
        bw, aw = before.get("window_s") or 1, after.get("window_s") or 1
        if bp or ap:
            lines.append(f"{AXIS_NAME[axis]}: flickers per minute {60 * bf / bw:.0f} → {60 * af / aw:.0f} "
                         f"(presses per minute {60 * bp / bw:.0f} → {60 * ap / aw:.0f})")
    return lines or ["Not enough play since the change to compare yet. Play for 20–30 seconds and check again."]
