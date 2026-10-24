"""DESK Coach: the agent people talk to in ASI:One.

Speaks the Agent Chat Protocol, reads the user's intent (ASI:One LLM with a
keyword fallback), does quick things itself (status, pause/resume, undo,
recalibrate) and hands real work to the specialists:

    Setup agent  - game profiles, key remaps, custom setups (asks before applying)
    Tuning agent - reads live telemetry, retunes triggers, verifies the result
    Doctor agent - diagnoses tracking/camera/calibration problems

Every specialist reply shows the steps it took and which agent did them.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from uagents import Agent, Context, Protocol
from uagents.context import DeliveryStatus
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    EndSessionContent,
    StartSessionContent,
    TextContent,
    chat_protocol_spec,
)

from agents import cards
from agents.desk_link import DeskError, DeskUnavailable
from agents.intent import Intent, parse_intent
from agents.messages import TaskRequest, TaskResult
from agents.shared_desk import get_desk
from agents.tuning import AXIS_NAME

log = logging.getLogger(__name__)

KNOWN_ACTIONS = {
    "desk_apply_profile", "desk_cancel", "desk_custom_setup", "desk_quick_setup", "desk_undo", "desk_verify",
    "desk_tune_less", "desk_tune_more", "desk_tune_auto", "desk_diagnose", "desk_recalibrate", "desk_resume",
    "desk_pause", "desk_status", "desk_help",
}
SPECIALIST_TIMEOUT_S = 20
VALIDATOR_TIMEOUT_S = 35
README = Path(__file__).with_name("COACH_README.md")


def _text(msg: ChatMessage) -> str:
    return " ".join(c.text for c in msg.content if isinstance(c, TextContent)).strip()


def help_card():
    return cards.carousel("What do you want to do?", [
        cards.item("racing", "Set up for a racing game", action="desk_quick_setup", cta_label="Set up", subtitle="Tilt = W A S D"),
        cards.item("subway-surfers", "Set up for Subway Surfers", action="desk_quick_setup", cta_label="Set up", subtitle="Tilt = arrow keys"),
        cards.item("tune", "Fix twitchy controls", action="desk_tune_less", cta_label="Tune", subtitle="Uses your live tilt data"),
        cards.item("doctor", "Something's not working", action="desk_diagnose", cta_label="Diagnose", subtitle="Health check"),
        cards.item("status", "Show my settings", action="desk_status", cta_label="Show"),
    ])


class Coach:
    def __init__(self, agent: Agent, specialists: dict[str, str]) -> None:
        self.agent = agent
        self.specialists = specialists  # role -> address
        self.pending: dict[str, tuple[str, float]] = {}  # request_id -> (user address, sent at)

    # ------------------------------------------------------------- plumbing
    async def reply(self, ctx: Context, user: str, narration: str, card=None) -> None:
        await ctx.send(user, cards.message(narration, card))

    async def delegate(self, ctx: Context, user: str, role: str, kind: str, **params) -> None:
        req_id = str(uuid4())
        self.pending[req_id] = (user, time.monotonic())
        ctx.logger.info("coach -> %s: %s %s", role, kind, params)
        status = await ctx.send(self.specialists[role], TaskRequest(request_id=req_id, user=user, kind=kind, params_json=json.dumps(params)))
        ctx.logger.info("send to %s: %s", role, status)
        if status is not None and status.status == DeliveryStatus.FAILED:
            self.pending.pop(req_id, None)
            await self.reply(ctx, user, f"The {role} agent could not be reached: {status.detail}")
            return

        async def watchdog() -> None:
            timeout = VALIDATOR_TIMEOUT_S if role == "validator" else SPECIALIST_TIMEOUT_S
            await asyncio.sleep(timeout)
            if self.pending.pop(req_id, None):
                message = ("The automatic check did not finish. You can ask me to check again."
                           if role == "validator" else f"The {role} agent didn't answer in {timeout}s. Check DESK's status before retrying.")
                await self.reply(ctx, user, message,
                                 cards.detail("Timed out", [("Agent", role), ("Task", kind)], [cards.cta("Health check", "desk_diagnose")]))

        asyncio.create_task(watchdog())

    async def on_result(self, ctx: Context, sender: str, res: TaskResult) -> None:
        entry = self.pending.pop(res.request_id, None)
        if entry is None:
            ctx.logger.warning("late or unknown result %s from %s", res.request_id, res.agent)
            return
        user, started = entry
        took = time.monotonic() - started
        narration = res.narration
        if res.steps:
            narration += f"\n\n🤖 {res.agent} ({took:.1f}s): " + " → ".join(res.steps)
        card = (res.card_kind, json.loads(res.card_json)) if res.card_kind and res.card_json else None
        await self.reply(ctx, user, narration, card)
        if res.ok and res.validation_json:
            await self.delegate(ctx, user, "validator", "validate", **json.loads(res.validation_json))

    # --------------------------------------------------------------- intents
    async def handle_text(self, ctx: Context, user: str, text: str) -> None:
        sel = cards.parse_selection(text, KNOWN_ACTIONS)
        if sel.get("action"):
            await self.handle_action(ctx, user, sel)
            return
        intent = await parse_intent(cards.strip_mention(text))
        ctx.logger.info("intent %s (via %s)", intent, intent.source)
        await self.handle_intent(ctx, user, intent, text)

    async def handle_intent(self, ctx: Context, user: str, it: Intent, text: str) -> None:
        if it.kind == "setup":
            await self.delegate(ctx, user, "setup", "plan_setup", game=it.game, text=text)
        elif it.kind == "tune":
            await self.delegate(ctx, user, "tuner", "tune", direction=it.direction, axis=it.axis)
        elif it.kind == "verify":
            await self.delegate(ctx, user, "tuner", "verify")
        elif it.kind == "diagnose":
            await self.delegate(ctx, user, "doctor", "diagnose")
        elif it.kind == "invert":
            await self.delegate(ctx, user, "setup", "invert", axis=it.axis)
        elif it.kind == "status":
            await self.status(ctx, user)
        elif it.kind == "recalibrate":
            await self.recalibrate(ctx, user)
        elif it.kind in ("pause", "resume"):
            await self.toggle(ctx, user, it.kind == "resume")
        elif it.kind == "undo":
            await self.undo(ctx, user)
        else:
            await self.reply(ctx, user, "Hi! I'm DESK Coach. DESK turns tilting a can into keyboard keys, so you can play games with "
                             "any object. I can set it up for your game, fix twitchy or unresponsive controls using your real "
                             "tilt data, and figure out what's wrong when it stops working.", help_card())

    async def handle_action(self, ctx: Context, user: str, sel: dict) -> None:
        a = sel["action"]
        prose = sel.get("prose")
        if a == "desk_apply_profile":
            await self.delegate(ctx, user, "setup", "apply_setup", profile=sel.get("profile"), prose=prose)
        elif a == "desk_quick_setup":
            await self.delegate(ctx, user, "setup", "plan_setup", game=sel.get("id"), text=prose or "")
        elif a == "desk_custom_setup":
            await self.delegate(ctx, user, "setup", "custom_setup", key_style=sel.get("key_style"),
                                sensitivity=sel.get("sensitivity"), prose=prose)
        elif a in ("desk_tune_less", "desk_tune_more", "desk_tune_auto"):
            await self.delegate(ctx, user, "tuner", "tune", direction=a.rsplit("_", 1)[1], axis=None)
        elif a == "desk_verify":
            await self.delegate(ctx, user, "tuner", "verify")
        elif a == "desk_diagnose":
            await self.delegate(ctx, user, "doctor", "diagnose")
        elif a == "desk_undo":
            await self.undo(ctx, user)
        elif a == "desk_recalibrate":
            await self.recalibrate(ctx, user)
        elif a in ("desk_resume", "desk_pause"):
            await self.toggle(ctx, user, a == "desk_resume")
        elif a == "desk_status":
            await self.status(ctx, user)
        elif a == "desk_cancel":
            await self.reply(ctx, user, "Cancelled. Nothing was changed.")
        else:
            await self.handle_intent(ctx, user, Intent("help"), "")

    # ------------------------------------------------------ coach's own tools
    async def status(self, ctx: Context, user: str) -> None:
        s = await get_desk().call("status")
        c = s["config"]
        k = c["keys"]
        rows = [
            ("State", s["mode"] + (" (simulated demo)" if s.get("simulated") else "")),
            ("Game profile", s.get("profile") or "default"),
            ("Keys (fwd/back/left/right)", " / ".join(k[x].upper() for x in ("forward", "back", "left", "right"))),
            ("Forward/back trigger", f"{c['forward_back']['on_deg']:g}° (release {c['forward_back']['off_deg']:g}°)"),
            ("Left/right trigger", f"{c['left_right']['on_deg']:g}° (release {c['left_right']['off_deg']:g}°)"),
            ("Keys held now", ", ".join(s["held"]).upper() or "none"),
        ]
        ctas = [cards.cta("Pause" if s["enabled"] else "Resume", "desk_pause" if s["enabled"] else "desk_resume"),
                cards.cta("Recalibrate", "desk_recalibrate"), cards.cta("Health check", "desk_diagnose")]
        await self.reply(ctx, user, "Here are DESK's current settings.", cards.detail("DESK status", rows, ctas))

    async def toggle(self, ctx: Context, user: str, on: bool) -> None:
        await get_desk().call("enable" if on else "disable")
        await self.reply(ctx, user, "Controls are back on. Tilt to play." if on else "Paused. All keys released and tilting does nothing until you resume.",
                         cards.detail("Controls " + ("on" if on else "paused"), [("Keys", "active" if on else "all released")],
                                      [cards.cta("Pause" if on else "Resume", "desk_pause" if on else "desk_resume")]))

    async def undo(self, ctx: Context, user: str) -> None:
        change = await get_desk().call("undo", actor="coach")
        b, a = change["before"], change["after"]
        rows = [(f"{AXIS_NAME['forward'].capitalize()} trigger", f"{b['forward_back']['on_deg']:g}° → {a['forward_back']['on_deg']:g}°"),
                (f"{AXIS_NAME['right'].capitalize()} trigger", f"{b['left_right']['on_deg']:g}° → {a['left_right']['on_deg']:g}°"),
                ("Keys", " / ".join(a["keys"][x].upper() for x in ("forward", "back", "left", "right")))]
        await self.reply(ctx, user, "Undone. DESK is back to the previous settings.", cards.info("Change undone", rows))

    async def recalibrate(self, ctx: Context, user: str) -> None:
        r = await get_desk().call("recalibrate")
        secs = r.get("duration_ms", 2000) / 1000
        await self.reply(ctx, user, f"Recalibrating: stand the can upright and let go for {secs:g} seconds. I'll tell you when it's done.")

        async def report() -> None:
            await asyncio.sleep(secs + 1.5)
            try:
                tel = await get_desk().call("telemetry", window_s=10)
                st = await get_desk().call("status")
            except (DeskUnavailable, DeskError) as exc:
                await self.reply(ctx, user, f"I couldn't check the calibration result: {exc}")
                return
            if st["calibrated"]:
                off = st.get("calibration_offsets_deg") or {}
                rows = [(label, f"{off[axis]:+.1f}°") for axis, label in (("forward", "Forward/back correction"),
                        ("right", "Left/right correction")) if isinstance(off.get(axis), (int, float))]
                await self.reply(ctx, user, "Calibrated. Tilt to play.", cards.info(
                    "Calibration complete", rows or [("Neutral", "Learned the can's upright pose from the overhead camera")]))
            else:
                last = tel.get("last_calibration") or {}
                await self.reply(ctx, user, "Calibration hasn't finished: " + (last.get("reason") or "the can was moving or not visible."),
                                 cards.detail("Calibration not done", [("Tip", "Hands off the can; keep it fully under the overhead camera")],
                                              [cards.cta("Try again", "desk_recalibrate"), cards.cta("Health check", "desk_diagnose")]))

        asyncio.create_task(report())


def build_coach(seed: str, specialists: dict[str, str], *, mailbox: bool, port: int | None = None, resolve=None) -> Agent:
    kwargs = dict(
        name="DESK Coach",
        seed=seed,
        mailbox=mailbox,
        description="Turn tilting a can into keyboard controls for any game. Sets up, tunes and fixes DESK from chat, using live tilt data.",
        publish_agent_details=True,
    )
    if README.exists():
        kwargs["readme_path"] = str(README)
    if port:
        kwargs["port"] = port
    if resolve:
        kwargs["resolve"] = resolve
    agent = Agent(**kwargs)
    coach = Coach(agent, specialists)
    chat = Protocol(spec=chat_protocol_spec)

    @chat.on_message(ChatMessage)
    async def on_chat(ctx: Context, sender: str, msg: ChatMessage) -> None:
        await ctx.send(sender, ChatAcknowledgement(timestamp=datetime.now(timezone.utc), acknowledged_msg_id=msg.msg_id))
        if any(isinstance(c, EndSessionContent) for c in msg.content):
            return
        text = _text(msg)
        if not text:
            if any(isinstance(c, StartSessionContent) for c in msg.content):
                return
            text = "help"
        try:
            await coach.handle_text(ctx, sender, text)
        except DeskUnavailable as exc:
            await coach.reply(ctx, sender, f"I can't reach DESK on the player's computer right now. {exc}",
                              cards.detail("DESK is offline", [("Fix", "Start python -m tilt_joystick --control (or DESK_DEMO_MODE=1), then try again")],
                                           [cards.cta("Try again", "desk_status", primary=True)]))
        except DeskError as exc:
            await coach.reply(ctx, sender, f"DESK refused that: {exc}")
        except Exception as exc:
            ctx.logger.exception("coach failed")
            await coach.reply(ctx, sender, f"Sorry, something went wrong on my side ({type(exc).__name__}). Nothing was changed.")

    @chat.on_message(ChatAcknowledgement)
    async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement) -> None:
        pass

    agent.include(chat, publish_manifest=True)

    @agent.on_message(model=TaskResult)
    async def on_result(ctx: Context, sender: str, res: TaskResult) -> None:
        await coach.on_result(ctx, sender, res)

    agent._desk_coach = coach  # for tests
    return agent
