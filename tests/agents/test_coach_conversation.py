"""Full conversations with the Coach: real Coach + real specialists + simulated DESK.
Agent-to-agent messages are routed in-process instead of over the network."""

import asyncio
import json
import logging

import pytest
from uagents_core.contrib.protocols.chat import ChatMessage, MetadataContent, TextContent

from agents import coach as coach_mod
from agents.coach import Coach
from agents.desk_link import DeskLink, FakeDesk
from agents.messages import TaskRequest
from agents.shared_desk import set_desk
from agents.specialists import HANDLERS, execute

ROLES = {"setup": "addr-setup", "tuner": "addr-tuner", "doctor": "addr-doctor", "validator": "addr-validator"}


class Storage(dict):
    def set(self, k, v):
        self[k] = v


class Ctx:
    def __init__(self, coach):
        self.coach = coach
        self.storage = Storage()
        self.logger = logging.getLogger("test")
        self.outbox: list[ChatMessage] = []
        self.delegated: list[str] = []

    async def send(self, dest, msg):
        if isinstance(msg, TaskRequest):
            role = next(r for r, a in ROLES.items() if a == dest)
            self.delegated.append(role)
            if role == "validator":
                return  # separate validator behavior is tested without a 20-second sleep
            label, handlers = HANDLERS[role]
            await self.coach.on_result(self, dest, await execute(label, handlers, self, msg))
        else:
            self.outbox.append(msg)


def last(ctx):
    msg = ctx.outbox[-1]
    text = " ".join(c.text for c in msg.content if isinstance(c, TextContent))
    meta = next((c.metadata for c in msg.content if isinstance(c, MetadataContent)), None)
    card = (meta["card_kind"], json.loads(meta["card_payload"])) if meta else (None, None)
    return text, card


@pytest.fixture
def chat(monkeypatch):
    monkeypatch.delenv("ASI_ONE_API_KEY", raising=False)
    monkeypatch.setattr(coach_mod, "SPECIALIST_TIMEOUT_S", 1)
    desk = FakeDesk("twitchy")
    set_desk(desk)
    coach = Coach(None, ROLES)
    ctx = Ctx(coach)

    def say(text):
        asyncio.run(coach.handle_text(ctx, "user1", text))
        return last(ctx)

    yield say, ctx, desk
    set_desk(None)


def test_setup_needs_approval_then_applies(chat):
    say, ctx, desk = chat
    text, (kind, card) = say("set up DESK for subway surfers")
    assert kind == "review" and "Nothing changes until you tap Apply" in text
    assert desk.controller.config.keys.forward == "w"  # not applied yet
    text, (kind, card) = say(json.dumps(card["approve_cta"]["selection"]))
    assert desk.controller.config.keys.forward == "up"
    assert "Setup agent" in text and kind == "detail"
    assert ctx.delegated == ["setup", "setup", "validator"]


def test_planner_prose_tap_still_applies_pending_profile(chat):
    say, _, desk = chat
    say("configure it for racing")
    say("User selected desk_apply_profile on the card")
    assert desk.controller.config.lr_on_threshold_deg == 18


def test_unknown_game_asks_with_a_form_then_custom_setup(chat):
    say, _, desk = chat
    _, (kind, card) = say("set me up for chess game")
    assert kind == "form"
    say(json.dumps({"action": "desk_custom_setup", "key_style": "arrows", "sensitivity": "low"}))
    assert desk.controller.config.keys.left == "left" and desk.controller.config.on_threshold_deg == 22


def test_twitchy_steering_is_tuned_from_live_data_and_can_be_undone(chat):
    say, ctx, desk = chat
    text, (kind, card) = say("the steering is way too twitchy")
    assert kind == "detail" and card["title"] == "Sensitivity tuned"
    assert "Tuning agent" in text and "frames" in text
    assert desk.controller.config.lr_on_threshold_deg > 15
    assert desk.controller.config.on_threshold_deg == 15
    say("undo")
    assert desk.controller.config.lr_on_threshold_deg in (None, 15)


def test_diagnose(chat):
    say, ctx, _ = chat
    text, (kind, card) = say("it keeps stopping, what's wrong?")
    assert ctx.delegated == ["doctor"] and card["title"] == "DESK health check"


def test_pause_resume_and_status(chat):
    say, _, desk = chat
    say("pause")
    assert not desk.controller.enabled
    _, (_, card) = say("show my settings")
    assert any(r["value"].startswith("disabled") for r in card["summary_rows"])
    say("resume")
    assert desk.controller.enabled


def test_help_shows_menu(chat):
    say, _, _ = chat
    _, (kind, card) = say("hi")
    assert kind == "carousel" and len(card["items"]) >= 4


def test_offline_desk_gives_honest_error(monkeypatch):
    set_desk(DeskLink("ws://127.0.0.1:9/ws/control", timeout_s=0.5))
    coach = Coach(None, ROLES)
    ctx = Ctx(coach)
    asyncio.run(coach.handle_text(ctx, "u", "the steering is twitchy"))
    text, _ = last(ctx)
    assert "couldn't reach DESK" in text
    set_desk(None)
