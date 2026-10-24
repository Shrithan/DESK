import json

import pytest

from agents import cards
from agents.desk_link import FakeDesk
from agents.doctor import diagnose
from agents.intent import parse_keywords
from agents.profiles import find_profile
from agents.tuning import compare, plan_tuning


@pytest.mark.parametrize("text, kind, extra", [
    ("set up desk for a racing game", "setup", {"game": "racing"}),
    ("I want to play subway surfers", "setup", {"game": "subway-surfers"}),
    ("the steering is way too twitchy", "tune", {"direction": "less", "axis": "right"}),
    ("I have to tilt too much to accelerate", "tune", {"direction": "more", "axis": "forward"}),
    ("it keeps stopping", "diagnose", {}),
    ("why isn't it working", "diagnose", {}),
    ("pause", "pause", {}),
    ("resume please", "resume", {}),
    ("recalibrate", "recalibrate", {}),
    ("undo that", "undo", {}),
    ("did it work?", "verify", {}),
    ("show my settings", "status", {}),
    ("hello", "help", {}),
])
def test_keyword_intents(text, kind, extra):
    it = parse_keywords(text)
    assert it.kind == kind
    for k, v in extra.items():
        assert getattr(it, k) == v


def test_profiles():
    assert find_profile("let's do mario kart racing").id == "racing"
    assert find_profile("subway surfers").keys["forward"] == "up"
    assert find_profile("chess") is None


def test_tuning_targets_the_twitchy_axis_with_evidence():
    desk = FakeDesk("twitchy")
    tel = desk.service.handle({"op": "telemetry", "window_s": 60})["result"]
    assert tel["keys"]["d"]["flickers"] + tel["keys"]["a"]["flickers"] >= 4
    plan = plan_tuning(tel, "less", None)
    changed = {c.axis: c for c in plan.changes if c.changed}
    assert set(changed) == {"right"}, plan.summary  # steering only
    assert changed["right"].after[0] > 15 and changed["right"].after[0] <= 35
    assert plan.patch["lr_on_threshold_deg"] > plan.patch["lr_off_threshold_deg"]
    assert "on_threshold_deg" not in plan.patch  # forward/back untouched
    assert any("flicker" in e for e in changed["right"].evidence)
    # applying it really reduces flicker on the simulated player
    desk.service.handle({"op": "set_config", "patch": plan.patch, "actor": "t"})
    desk.telemetry.reset()
    desk.advance(60)
    after = desk.service.handle({"op": "telemetry", "window_s": 60})["result"]
    f_before = tel["keys"]["d"]["flickers"] + tel["keys"]["a"]["flickers"]
    f_after = sum(after["keys"].get(k, {}).get("flickers", 0) for k in "ad")
    assert f_after < f_before / 2, (f_before, f_after)
    assert compare(tel, after)


def test_tuning_leaves_good_settings_alone():
    tel = FakeDesk("calm").service.handle({"op": "telemetry", "window_s": 60})["result"]
    assert plan_tuning(tel, "auto").patch == {}


def test_doctor_finds_tracking_loss_and_pause():
    desk = FakeDesk("dark")
    status = desk.service.handle({"op": "status"})["result"]
    tel = desk.service.handle({"op": "telemetry", "window_s": 60})["result"]
    titles = [f.title for f in diagnose(status, tel)]
    assert "The camera keeps losing the can" in titles
    status["enabled"] = False
    assert diagnose(status, tel)[0].title == "DESK is paused"


def test_doctor_no_data():
    tel = {"window_s": 60, "frames": 0}
    assert diagnose({"enabled": True, "mode": "active"}, tel)[0].title == "No tilt data is reaching DESK"


def test_card_message_and_selection_parsing():
    msg = cards.message("pick", cards.review("Apply?", [("a", "b")], cards.cta("Apply", "desk_apply_profile", profile="racing"),
                                             cards.cta("No", "desk_cancel")))
    meta = msg.content[1].metadata
    payload = json.loads(meta["card_payload"])
    assert meta["card_kind"] == "review" and payload["approve_cta"]["selection"]["profile"] == "racing"
    known = {"desk_apply_profile", "desk_cancel"}
    assert cards.parse_selection('@desk {"action":"desk_apply_profile","profile":"racing"}', known)["profile"] == "racing"
    assert cards.parse_selection("The user tapped desk_apply_profile for racing", known)["action"] == "desk_apply_profile"
    assert cards.parse_selection("my game is twitchy", known) == {}
