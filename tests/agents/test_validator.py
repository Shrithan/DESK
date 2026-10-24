from agents.desk_link import FakeDesk
from agents.tuning import plan_tuning
from agents.validator import assess


def test_validator_keeps_effective_tune():
    desk = FakeDesk("twitchy")
    before = desk.service.handle({"op": "telemetry", "window_s": 60})["result"]
    plan = plan_tuning(before, "less", "right")
    change = desk.service.handle({"op": "set_config", "patch": plan.patch, "actor": "test"})["result"]
    desk.telemetry.reset()
    desk.advance(20)
    after = desk.service.handle({"op": "telemetry", "window_s": 20})["result"]
    verdict, _ = assess(before, after, "tune")
    assert verdict == "keep"
    assert desk.service.handle({"op": "status"})["result"]["revision"] == change["revision"]


def test_conditional_undo_refuses_to_revert_newer_change():
    desk = FakeDesk("calm")
    first = desk.service.handle({"op": "set_config", "patch": {"on_threshold_deg": 20}, "actor": "test"})["result"]
    desk.service.handle({"op": "set_config", "patch": {"on_threshold_deg": 25}, "actor": "test"})
    stale = desk.service.handle({"op": "undo_if_revision", "revision": first["revision"], "actor": "validator"})
    assert not stale["ok"]
    assert desk.controller.config.on_threshold_deg == 25


def test_validator_flags_tracking_collapse():
    before = {"frames": 600, "window_s": 20, "tracking_lost": 0}
    after = {"frames": 0, "window_s": 20, "tracking_lost": 1}
    verdict, _ = assess(before, after, "setup")
    assert verdict == "undo"
