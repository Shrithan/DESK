import asyncio
import json

import pytest

from backend.tilt_keys.config import TiltKeyConfig
from backend.tilt_keys.control import ControlError, ControlService, apply_patch
from backend.tilt_keys.controller import TiltKeyController
from backend.tilt_keys.telemetry import Telemetry
from tests.tilt_keys.conftest import RecordingBackend


class Clock:
    def __init__(self):
        self.t = 1_000_000

    def __call__(self):
        return self.t


def make(cfg=None):
    clock = Clock()
    tel = Telemetry(clock_ms=clock)
    backend = RecordingBackend()
    ctl = TiltKeyController(cfg or TiltKeyConfig(calibration_duration_ms=0), backend, clock_ms=clock,
                            on_event=tel.on_event, on_sample=tel.on_sample)
    return ctl, tel, ControlService(ctl, tel), clock, backend


def feed(ctl, clock, fwd, right, frames=5, found=True):
    for _ in range(frames):
        clock.t += 33
        ctl.handle_message({"type": "tilt_update", "timestamp_ms": clock.t, "forward_deg": fwd, "right_deg": right, "can_found": found})


def test_left_right_can_have_its_own_threshold():
    cfg = TiltKeyConfig(calibration_duration_ms=0, filter_enabled=False, lr_on_threshold_deg=20, lr_off_threshold_deg=15)
    ctl, _, _, clock, _ = make(cfg)
    feed(ctl, clock, 17, 17)
    assert ctl.held == {"w"}  # forward uses 15, steering needs 20
    feed(ctl, clock, 0, 22)
    assert ctl.held == {"d"}


@pytest.mark.parametrize("patch, msg", [
    ({"on_threshold_deg": 80}, "safe range"),
    ({"on_threshold_deg": 12, "off_threshold_deg": 11}, "gap"),
    ({"keys": {"forward": "delete"}}, "not allowed"),
    ({"keys": {"forward": "s"}}, "distinct"),
    ({"stale_timeout_ms": 99999}, "may not change"),
    ({"lr_on_threshold_deg": 20}, "both"),
    ({}, "non-empty"),
])
def test_apply_patch_rejects_unsafe_changes(patch, msg):
    with pytest.raises(ControlError, match=msg):
        apply_patch(TiltKeyConfig(), patch)


def test_set_config_releases_keys_records_history_and_undoes():
    ctl, _, svc, clock, backend = make(TiltKeyConfig(calibration_duration_ms=0, filter_enabled=False))
    feed(ctl, clock, 25, 0)
    assert ctl.held == {"w"}
    r = svc.handle({"id": "1", "op": "set_config", "actor": "tuning-agent", "reason": "test",
                    "patch": {"keys": {"forward": "up", "back": "down", "left": "left", "right": "right"}}})
    assert r["ok"], r
    assert ctl.held == frozenset()
    assert backend.events[-1] == ("up", "w")  # W released before the swap
    assert r["result"]["after"]["keys"]["forward"] == "up"
    assert svc.handle({"op": "history"})["result"]["changes"][0]["actor"] == "tuning-agent"
    u = svc.handle({"op": "undo"})
    assert u["ok"] and ctl.config.keys.forward == "w"
    assert not svc.handle({"op": "undo"})["ok"]


def test_bad_requests_never_raise():
    _, _, svc, _, _ = make()
    assert not svc.handle({"op": "explode"})["ok"]
    assert not svc.handle(None)["ok"]
    assert not svc.handle({"op": "telemetry", "window_s": 0})["ok"]


def test_telemetry_counts_flicker_and_tracking_loss():
    ctl, tel, svc, clock, _ = make(TiltKeyConfig(calibration_duration_ms=0, filter_enabled=False))
    for _ in range(5):  # quick taps = flicker
        feed(ctl, clock, 0, 16, frames=2)
        feed(ctl, clock, 0, 5, frames=2)
    feed(ctl, clock, 0, 25, frames=20)  # a real, long press
    feed(ctl, clock, 0, 0, frames=2)
    feed(ctl, clock, None, None, frames=3, found=False)
    feed(ctl, clock, 0, 0, frames=3)
    snap = svc.handle({"op": "telemetry", "window_s": 60})["result"]
    assert snap["keys"]["d"]["presses"] == 6
    assert snap["keys"]["d"]["flickers"] == 5
    assert snap["tracking_lost"] == 1 and snap["tracking_restored"] == 1
    assert snap["right"]["max_pos_deg"] == 25
    assert snap["config"]["left_right"]["on_deg"] == 15


def test_control_over_websocket():
    from agents.desk_link import DeskError, DeskLink
    from backend.tilt_keys.run import WebSocketHub

    async def main():
        ctl, tel, svc, _, _ = make()
        hub = WebSocketHub("127.0.0.1", 0)
        hub.control = svc
        server = asyncio.create_task(hub.serve_forever(ctl))
        await hub.ready.wait()
        link = DeskLink(f"ws://127.0.0.1:{hub.bound_port}/ws/control")
        status = await link.call("status")
        change = await link.call("set_config", patch={"on_threshold_deg": 20, "off_threshold_deg": 14}, actor="test")
        with pytest.raises(DeskError):
            await link.call("set_config", patch={"on_threshold_deg": 99})
        server.cancel()
        return status, change

    status, change = asyncio.run(main())
    assert status["mode"] == "active"
    assert change["after"]["forward_back"]["on_deg"] == 20
