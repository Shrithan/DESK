"""Doctor agent logic: turn telemetry + status into findings with concrete fixes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Severity = Literal["ok", "warning", "problem"]


@dataclass
class Finding:
    severity: Severity
    title: str
    evidence: str
    fixes: list[str] = field(default_factory=list)
    action: str | None = None  # a card action that fixes it, if any


def diagnose(status: dict, telemetry: dict) -> list[Finding]:
    f: list[Finding] = []
    window = telemetry.get("window_s") or 1
    per_min = 60.0 / window
    frames = telemetry.get("frames", 0)

    if not status.get("enabled", True):
        f.append(Finding("problem", "DESK is paused", "Controls are switched off, so no keys are pressed.",
                         ["Say 'resume' or tap Resume."], "desk_resume"))
    if status.get("mode") == "calibrating":
        f.append(Finding("warning", "Still calibrating", "DESK is waiting for the can to stand still to learn 'straight'.",
                         ["Stand the can upright and keep your hands off it for 2 seconds."]))
    if telemetry.get("calibration_failures", 0):
        last = telemetry.get("last_calibration") or {}
        f.append(Finding("problem", "Calibration keeps failing",
                         f"{telemetry['calibration_failures']} failed attempts. Last reason: {last.get('reason', 'unknown')}.",
                         ["Let go of the can completely during calibration.", "Make sure the table is not being bumped."],
                         "desk_recalibrate"))
    if frames == 0 and status.get("mode") != "disabled":
        f.append(Finding("problem", "No tilt data is reaching DESK",
                         f"0 camera frames in the last {window:g}s.",
                         ["Check python -m tilt_joystick --control is running and the can is under the overhead camera.",
                          "Check the camera is connected and not in use by another app.",
                          "Stand the can upright so DESK can lock on and calibrate."]))
        return f or [Finding("ok", "Nothing else to check", "No data yet.")]

    rate = telemetry.get("frame_rate_hz", 0)
    if 0 < rate < 15:
        f.append(Finding("warning", "Camera data is slow", f"{rate:g} frames per second (want 25 to 30).",
                         ["Close other heavy apps.", "Use a wired connection for the phones if possible.", "Add light: dim scenes slow the camera down."]))
    lost = telemetry.get("tracking_lost", 0)
    unavailable = telemetry.get("unavailable_frames", 0)
    if lost * per_min >= 3 or (frames and unavailable / frames > 0.15):
        pct = 100 * unavailable / frames if frames else 0
        f.append(Finding("problem", "The camera keeps losing the can",
                         f"Lost the can {lost} times in {window:g}s; it was missing in {pct:.0f}% of frames.",
                         ["Turn on a lamp or face a window; shadows and glare are the usual cause.",
                          "Use a plain background that contrasts with the can.",
                          "Hold the can by its base so your hand doesn't cover it.",
                          "Keep the whole can inside the overhead camera view."]))
    if telemetry.get("stale_releases", 0) >= 2:
        f.append(Finding("warning", "The data stream keeps pausing",
                         f"{telemetry['stale_releases']} gaps longer than 0.2s; DESK released all keys each time for safety.",
                         ["Check the phone connection (Wi-Fi or cable).", "Keep the phones from going to sleep."]))
    offsets = status.get("calibration_offsets_deg") or {}
    big = {k: v for k, v in offsets.items() if v is not None and abs(v) > 8}
    if big:
        f.append(Finding("warning", "A camera looks tilted",
                         "Your 'straight' can reads as " + ", ".join(f"{k} {v:+.0f}°" for k, v in big.items()) + ". DESK corrects it, but big offsets reduce accuracy.",
                         ["Straighten the phone stands, then recalibrate."], "desk_recalibrate"))
    flicker = sum(k.get("flickers", 0) for k in telemetry.get("keys", {}).values())
    if flicker * per_min >= 6:
        f.append(Finding("warning", "Keys are flickering",
                         f"{flicker} very short key presses in {window:g}s; the trigger is inside your normal wobble.",
                         ["Let the Tuning agent raise the trigger."], "desk_tune_auto"))
    if not f:
        f.append(Finding("ok", "Everything looks healthy",
                         f"{rate:g} frames/s, can lost {lost} times, {flicker} flickers in the last {window:g}s."))
    return f
