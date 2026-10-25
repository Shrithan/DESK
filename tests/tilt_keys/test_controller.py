"""Behavioral tests for the full pipeline (the required acceptance list)."""

import pytest

from backend.tilt_keys.config import KeyBindings, TiltKeyConfig
from backend.tilt_keys.controller import TiltKeyController
from tests.tilt_keys.conftest import FRAME_MS, Rig, RecordingBackend


# 20 deg forward presses W once; 12 keeps it held; 8 releases it.
def test_forward_press_hold_release(rig):
    rig.feed(20, 0, frames=10)
    assert rig.held == {"w"}
    rig.feed(12, 0, frames=10)
    assert rig.held == {"w"}
    rig.feed(8, 0, frames=5)
    assert rig.held == frozenset()
    assert rig.backend.events == [("down", "w"), ("up", "w")]


def test_forward_press_hold_release_with_default_filter():
    r = Rig(TiltKeyConfig(calibration_duration_ms=0))  # One Euro filter ON
    r.feed(0, 0, frames=10)
    r.feed(20, 0, frames=30)
    r.feed(12, 0, frames=30)
    assert r.held == {"w"}
    r.feed(8, 0, frames=30)
    assert r.backend.events == [("down", "w"), ("up", "w")]


# A reading oscillating between 13 and 16 does not flicker the key.
def test_oscillation_13_16_does_not_flicker(rig):
    for _ in range(50):
        rig.feed(13, 0)
        rig.feed(16, 0)
    assert rig.backend.events == [("down", "w")]  # pressed once at the first 16, never released


def test_oscillation_below_on_threshold_never_presses_with_filter():
    r = Rig(TiltKeyConfig(calibration_duration_ms=0))
    for _ in range(50):
        r.feed(13, 0)
        r.feed(14.5, 0)
    assert r.backend.events == []


# Forward + left holds W and A together.
def test_diagonal_holds_two_keys(rig):
    rig.feed(20, -25, frames=5)
    assert rig.held == {"w", "a"}
    rig.feed(-20, 25, frames=5)
    assert rig.held == {"s", "d"}
    # releases are sent before presses so W and S are never down together
    assert rig.backend.events == [("down", "a"), ("down", "w"), ("up", "a"), ("up", "w"), ("down", "d"), ("down", "s")]


# can_found=false releases keys immediately.
def test_can_lost_releases_immediately(rig):
    rig.feed(20, -25, frames=5)
    rig.feed(20, -25, can_found=False)
    assert rig.held == frozenset()
    assert "tracking_lost" in rig.event_names()
    rig.feed(20, -25, frames=1)
    assert rig.held == {"w", "a"}
    assert "tracking_restored" in rig.event_names()


def test_null_axis_releases_only_that_axis(rig):
    rig.feed(20, -25, frames=5)
    rig.feed(20, None)
    assert rig.held == {"w"}
    rig.feed(None, -25)
    assert rig.held == {"a"}


# No updates for >200 ms releases all keys.
def test_stale_input_releases_all(rig):
    rig.feed(20, -25, frames=5)
    rig.advance(200)
    assert rig.held == {"w", "a"}  # exactly 200 ms is not yet stale
    rig.advance(1)
    assert rig.held == frozenset()
    assert "stale_release" in rig.event_names()
    rig.feed(20, -25)  # fresh data re-presses
    assert rig.held == {"w", "a"}


def test_stale_timeout_configurable(make_rig):
    r = make_rig(stale_timeout_ms=500)
    r.feed(20, 0, frames=3)
    r.advance(400)
    assert r.held == {"w"}
    r.advance(101)
    assert r.held == frozenset()


def test_invalid_messages_do_not_refresh_watchdog(rig):
    rig.feed(20, 0, frames=3)
    for _ in range(10):
        rig.now_ms += 30
        rig.ctl.handle_message('{"type":"tilt_update","forward_deg":"oops"}')
        rig.ctl.tick()
    assert rig.held == frozenset()


# Exit/exception path releases all keys.
def test_shutdown_releases_all_and_closes(rig):
    rig.feed(20, -25, frames=5)
    rig.ctl.shutdown()
    assert rig.held == frozenset() and rig.backend.closed
    assert rig.backend.down == set()
    rig.feed(20, -25)  # updates after shutdown are ignored
    assert rig.backend.down == set()
    rig.ctl.shutdown()  # idempotent


def test_exception_path_releases_all():
    backend = RecordingBackend()
    ctl = TiltKeyController(TiltKeyConfig(filter_enabled=False, calibration_duration_ms=0), backend, clock_ms=lambda: 0)
    with pytest.raises(RuntimeError):
        try:
            ctl.handle_message({"type": "tilt_update", "timestamp_ms": 1, "forward_deg": 30, "right_deg": 0, "can_found": True})
            assert backend.down == {"w"}
            raise RuntimeError("simulated crash in the main loop")
        finally:
            ctl.shutdown("exception")
    assert backend.down == set()


def test_run_loop_crash_releases_keys():
    """The real runner's try/finally: a crash inside the input loop still releases."""
    import asyncio

    from backend.tilt_keys.run import run_controller

    backend = RecordingBackend()
    ctl = TiltKeyController(TiltKeyConfig(filter_enabled=False, calibration_duration_ms=0), backend)

    async def crashing_source(controller):
        controller.handle_message(
            {"type": "tilt_update", "timestamp_ms": 1, "forward_deg": 30, "right_deg": 0, "can_found": True}
        )
        assert backend.down == {"w"}
        raise RuntimeError("source crashed")

    with pytest.raises(RuntimeError, match="source crashed"):
        asyncio.run(run_controller(ctl, [crashing_source], install_signal_handlers=False))
    assert backend.down == set() and backend.closed


# Calibration offset is subtracted; a moving can fails calibration.
def test_calibration_offset_subtracted(make_rig):
    r = make_rig(calibration_duration_ms=2000)
    assert r.ctl.mode == "calibrating"
    r.feed(6.0, -3.0, frames=70)  # can naturally sits 6 deg forward, 3 deg left
    assert r.ctl.calibrated
    assert r.ctl.forward_offset_deg == pytest.approx(6.0)
    assert r.ctl.right_offset_deg == pytest.approx(-3.0)
    assert r.backend.events == []  # nothing pressed while calibrating
    r.feed(20.0, -3.0, frames=3)  # only 14 deg past neutral: below ON
    assert r.held == frozenset()
    r.feed(22.0, -20.0, frames=3)  # 16 forward, 17 left past neutral
    assert r.held == {"w", "a"}


def test_moving_can_fails_calibration_then_retries(make_rig):
    r = make_rig(calibration_duration_ms=2000)
    for i in range(70):
        r.feed(i * 0.5, 0.0)  # steadily tilting
    assert not r.ctl.calibrated
    failed = [d for n, d in r.events if n == "calibration_failed"]
    assert failed and "moving" in failed[0]["reason"]
    assert r.backend.events == []
    # The retry window that straddles the tail of the motion is also rejected;
    # the next fully-still window succeeds.
    r.feed(1.0, 1.0, frames=140)
    assert r.ctl.calibrated
    assert r.ctl.forward_offset_deg == pytest.approx(1.0)


def test_recalibrate_command_releases_and_recollects(make_rig):
    r = make_rig(calibration_duration_ms=1000)
    r.feed(0, 0, frames=40)
    r.feed(20, 0, frames=3)
    assert r.held == {"w"}
    r.ctl.handle_message({"type": "tilt_command", "timestamp_ms": 1, "command": "recalibrate"})
    assert r.held == frozenset() and r.ctl.mode == "calibrating"
    r.feed(20, 0, frames=40)  # new neutral is 20 deg
    assert r.ctl.forward_offset_deg == pytest.approx(20)
    r.feed(20, 0, frames=5)
    assert r.held == frozenset()


# Inverted axis and remapped keys work.
def test_inverted_axes(make_rig):
    r = make_rig(invert_forward=True, invert_right=True)
    r.feed(20, -25, frames=3)
    assert r.held == {"s", "d"}


def test_remapped_keys(make_rig):
    r = make_rig(keys=KeyBindings(forward="up", back="down", left="left", right="right"))
    r.feed(20, -25, frames=3)
    assert r.held == {"up", "left"}
    r.feed(0, 0)
    assert r.backend.events == [("down", "left"), ("down", "up"), ("up", "left"), ("up", "up")]


# No key-down is sent twice in a row for the same key (RecordingBackend asserts on every call).
def test_no_duplicate_key_down_over_long_run(rig):
    import random

    rnd = random.Random(42)
    for _ in range(2000):
        rig.feed(rnd.uniform(-30, 30), rnd.uniform(-30, 30), can_found=rnd.random() > 0.05)
    downs = [k for kind, k in rig.backend.events if kind == "down"]
    assert downs  # the walk did press things
    last = {}
    for kind, key in rig.backend.events:
        assert last.get(key) != kind, f"{kind} sent twice in a row for {key}"
        last[key] = kind


# Global enable/disable toggle.
def test_disable_releases_and_sends_nothing(rig):
    rig.feed(20, 0, frames=3)
    rig.ctl.handle_command("disable")
    assert rig.held == frozenset()
    n = len(rig.backend.events)
    rig.feed(30, 30, frames=20)
    rig.advance(1000)
    assert len(rig.backend.events) == n and rig.ctl.mode == "disabled"
    rig.ctl.handle_command("toggle")
    rig.feed(30, 30)
    assert rig.held == {"w", "d"}


def test_out_of_order_updates_dropped(rig):
    rig.feed(20, 0, frames=3)
    rig.ctl.handle_message(
        {"type": "tilt_update", "timestamp_ms": rig.ts_ms - 10 * FRAME_MS, "forward_deg": 0, "right_deg": 0, "can_found": True}
    )
    assert rig.held == {"w"}
