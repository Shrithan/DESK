"""The three specialist agents. Each receives TaskRequest from the Coach, does
real work against tilt-to-keys (read telemetry, change settings), and answers
with a TaskResult that includes the steps it took and an ASI:One card."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Awaitable, Callable

from uagents import Agent, Context

from agents import cards
from agents.desk_link import DeskError, DeskUnavailable
from agents.doctor import diagnose
from agents.messages import TaskRequest, TaskResult
from agents.profiles import PROFILES, custom_profile, find_profile
from agents.shared_desk import get_desk
from agents.tuning import AXIS_NAME, compare, plan_tuning
from agents.validator import assess

log = logging.getLogger(__name__)
Handler = Callable[[Context, TaskRequest, dict], Awaitable[TaskResult]]


def _result(req: TaskRequest, agent: str, narration: str, card=None, steps=None, ok=True, validation=None) -> TaskResult:
    kind, payload = card if card else (None, None)
    return TaskResult(request_id=req.request_id, ok=ok, agent=agent, narration=narration, steps=steps or [],
                      card_kind=kind, card_json=None if payload is None else json.dumps(payload),
                      validation_json=None if validation is None else json.dumps(validation))


async def execute(name: str, handlers: dict[str, Handler], ctx: Context, req: TaskRequest) -> TaskResult:
    """Run one task; every failure becomes an honest TaskResult instead of silence."""
    handler = handlers.get(req.kind)
    try:
        if handler is None:
            raise DeskError(f"{name} can't do {req.kind!r}")
        return await handler(ctx, req, json.loads(req.params_json or "{}"))
    except DeskUnavailable as exc:
        return _result(req, name, f"I couldn't reach DESK on this computer: {exc}", ok=False)
    except DeskError as exc:
        return _result(req, name, f"DESK refused the change: {exc}", ok=False)
    except Exception as exc:
        log.exception("task failed")
        return _result(req, name, f"Something went wrong in the {name}: {exc}", ok=False)


def _make_agent(name: str, label: str, seed: str, handlers: dict[str, Handler], resolve=None) -> Agent:
    agent = Agent(name=name, seed=seed, **({"resolve": resolve} if resolve else {}))

    @agent.on_message(model=TaskRequest, replies=TaskResult)
    async def on_task(ctx: Context, sender: str, req: TaskRequest) -> None:
        ctx.logger.info("%s <- %s", label, req.kind)
        await ctx.send(sender, await execute(label, handlers, ctx, req))

    return agent


# ---------------------------------------------------------------- Setup agent
SETUP = "Setup agent"


async def plan_setup(ctx: Context, req: TaskRequest, p: dict) -> TaskResult:
    desk = get_desk()
    status = await desk.call("status")
    profile = find_profile(p.get("game") or p.get("text"))
    steps = ["Read DESK's current settings"]
    if profile is None:
        card = cards.form("Which keys does your game use?", [
            cards.select_field("key_style", "Keys", [("wasd", "W A S D"), ("arrows", "Arrow keys")]),
            cards.select_field("sensitivity", "Sensitivity", [("low", "Low (big tilts)"), ("normal", "Normal"), ("high", "High (small tilts)")]),
        ], cards.cta("Set up DESK", "desk_custom_setup", primary=True))
        return _result(req, SETUP, "I don't know that game yet. Tell me which keys it uses and how sensitive you want it.",
                       card, steps + ["Game not in my profiles, so I'm asking for its keys"])
    ctx.storage.set(f"pending_profile:{req.user}", profile.id)
    cur = status["config"]
    current = f"keys {'/'.join(cur['keys'][s] for s in ('forward', 'back', 'left', 'right')).upper()}, trigger {cur['forward_back']['on_deg']:g}°"
    card = cards.review(f"Set up DESK for {profile.name}?", profile.rows() + [("Right now", current)],
                        cards.cta("Apply", "desk_apply_profile", primary=True, profile=profile.id),
                        cards.cta("Cancel", "desk_cancel"))
    return _result(req, SETUP, f"Here's my plan for {profile.name}. {profile.why} Nothing changes until you tap Apply.",
                   card, steps + [f"Matched your game to the '{profile.id}' profile", "Built the plan; waiting for your approval"])


async def _apply(ctx: Context, req: TaskRequest, profile) -> TaskResult:
    desk = get_desk()
    baseline = await desk.call("telemetry", window_s=20)
    change = await desk.call("set_config", patch=profile.patch(), actor="setup-agent",
                             reason=f"profile {profile.id}", profile=profile.id)
    await desk.call("recalibrate")
    after = change["after"]
    card = cards.detail(f"DESK is set up for {profile.name}", profile.rows(), [
        cards.cta("Check health", "desk_diagnose", primary=True),
        cards.cta("Undo", "desk_undo"),
    ])
    return _result(req, SETUP,
                   "Done. Now stand the can upright and let go for 2 seconds so I can learn what 'straight' is. Then tilt to play.",
                   card, ["Validated the new settings (safe ranges, distinct keys)",
                          f"Applied: keys {'/'.join(after['keys'][s] for s in ('forward', 'back', 'left', 'right')).upper()}, "
                          f"forward/back {after['forward_back']['on_deg']:g}°, left/right {after['left_right']['on_deg']:g}°",
                          "Released all keys during the switch", "Started calibration"],
                   validation={"change_kind": "setup", "before": baseline, "revision": change["revision"]})


async def apply_setup(ctx: Context, req: TaskRequest, p: dict) -> TaskResult:
    pid = p.get("profile") or (find_profile(p.get("prose")) or PROFILES.get(ctx.storage.get(f"pending_profile:{req.user}") or ""))
    profile = PROFILES.get(pid) if isinstance(pid, str) else pid
    if profile is None:
        return _result(req, SETUP, "I lost track of which game we were setting up. Which game is it?", ok=False)
    return await _apply(ctx, req, profile)


async def custom_setup(ctx: Context, req: TaskRequest, p: dict) -> TaskResult:
    prose = (p.get("prose") or "").lower()
    style = p.get("key_style") or ("arrows" if "arrow" in prose else "wasd")
    sens = p.get("sensitivity") or next((s for s in ("low", "high") if s in prose), "normal")
    return await _apply(ctx, req, custom_profile(style, sens))


async def invert(ctx: Context, req: TaskRequest, p: dict) -> TaskResult:
    desk = get_desk()
    baseline = await desk.call("telemetry", window_s=20)
    axis = p.get("axis") or "forward"
    field = "invert_forward" if axis == "forward" else "invert_right"
    status = await desk.call("status")
    new = not status["config"][field]
    change = await desk.call("set_config", patch={field: new}, actor="setup-agent", reason=f"user asked to flip {AXIS_NAME[axis]}")
    return _result(req, SETUP, f"Flipped {AXIS_NAME[axis]}: it's now {'reversed' if new else 'normal'}.",
                   cards.detail("Direction flipped", [(AXIS_NAME[axis], "reversed" if new else "normal")], [cards.cta("Undo", "desk_undo")]),
                   ["Read current direction", f"Set {field} = {new}"],
                   validation={"change_kind": "invert", "before": baseline, "revision": change["revision"]})


# --------------------------------------------------------------- Tuning agent
TUNER = "Tuning agent"


async def tune(ctx: Context, req: TaskRequest, p: dict) -> TaskResult:
    desk = get_desk()
    tel = await desk.call("telemetry", window_s=60)
    plan = plan_tuning(tel, p.get("direction", "auto"), p.get("axis"))
    steps = [f"Read {tel['window_s']:g}s of live tilt data ({tel['frames']} frames)"]
    evidence = [e for c in plan.changes for e in c.evidence]
    if not plan.patch:
        card = cards.detail("No change needed", [("Finding", plan.summary)] + [("Data", e) for e in evidence], [
            cards.cta("Less sensitive anyway", "desk_tune_less"),
            cards.cta("More sensitive", "desk_tune_more"),
        ])
        return _result(req, TUNER, plan.summary + (" " + " ".join(plan.notes) if plan.notes else ""), card,
                       steps + ["Compared your tilts with the current triggers"])
    change = await desk.call("set_config", patch=plan.patch, actor="tuning-agent", reason=plan.summary)
    ctx.storage.set(f"baseline:{req.user}", json.dumps({"t": time.time(), "telemetry": tel}))
    rows = [(f"{AXIS_NAME[c.axis].capitalize()} trigger", f"{c.before[0]:g}° → {c.after[0]:g}° (release {c.before[1]:g}° → {c.after[1]:g}°)")
            for c in plan.changes if c.changed]
    rows += [("Why", e) for e in evidence]
    card = cards.detail("Sensitivity tuned", rows, [
        cards.cta("Check results", "desk_verify", primary=True),
        cards.cta("Undo", "desk_undo"),
    ])
    narration = plan.summary + " Play for 20–30 seconds, then tap Check results and I'll measure whether it helped."
    if plan.notes:
        narration += " " + " ".join(plan.notes)
    return _result(req, TUNER, narration, card, steps + [
        "Found where your normal wobble crosses the trigger",
        "Picked new triggers, kept within your full tilt range and safe limits",
        f"Applied the change at {change['time']}",
    ], validation={"change_kind": "tune", "before": tel, "revision": change["revision"]})


async def verify(ctx: Context, req: TaskRequest, p: dict) -> TaskResult:
    raw = ctx.storage.get(f"baseline:{req.user}")
    if not raw:
        return _result(req, TUNER, "I haven't tuned anything for you yet, so there's nothing to compare. Say 'it's twitchy' or 'tune it' first.")
    base = json.loads(raw)
    since = time.time() - base["t"]
    if since < 8:
        return _result(req, TUNER, f"It's only been {since:.0f} seconds. Play for at least 20 seconds, then check again.",
                       cards.detail("Too early to tell", [("Since change", f"{since:.0f}s")], [cards.cta("Check results", "desk_verify")]))
    after = await get_desk().call("telemetry", window_s=min(120, since))
    lines = compare(base["telemetry"], after)
    return _result(req, TUNER, "Here's how your play changed since I tuned DESK.",
                   cards.detail("Before vs after", [("Result", line) for line in lines],
                                [cards.cta("Tune again", "desk_tune_auto"), cards.cta("Undo", "desk_undo")]),
                   [f"Read the {min(120, since):.0f}s of play since the change", "Compared it with the data from before"])


# --------------------------------------------------------------- Doctor agent
DOCTOR = "Doctor agent"
VALIDATOR = "Validator agent"
ICON = {"ok": "✅", "warning": "⚠️", "problem": "❌"}


async def run_diagnosis(ctx: Context, req: TaskRequest, p: dict) -> TaskResult:
    desk = get_desk()
    status = await desk.call("status")
    tel = await desk.call("telemetry", window_s=60)
    findings = diagnose(status, tel)
    rows = [(f"{ICON[f.severity]} {f.title}", f.evidence) for f in findings]
    fixes = [f"• {fix}" for f in findings if f.severity != "ok" for fix in f.fixes]
    action_labels = {"desk_recalibrate": "Recalibrate", "desk_resume": "Resume", "desk_tune_auto": "Fix sensitivity"}
    ctas = [cards.cta(action_labels[a], a, primary=i == 0) for i, a in enumerate(dict.fromkeys(f.action for f in findings if f.action))]
    ctas.append(cards.cta("Check again", "desk_diagnose"))
    worst = max(findings, key=lambda f: ["ok", "warning", "problem"].index(f.severity))
    narration = ("Everything looks healthy." if worst.severity == "ok" else f"Main issue: {worst.title.lower()}.") + \
        ("\n\nHow to fix it:\n" + "\n".join(fixes) if fixes else "")
    return _result(req, DOCTOR, narration, cards.detail("DESK health check", rows, ctas),
                   ["Read DESK status", f"Read {tel['window_s']:g}s of telemetry", f"Checked {len(findings)} findings against known failure patterns"])


async def validate(ctx: Context, req: TaskRequest, p: dict) -> TaskResult:
    """Watch a fresh 20-second window and safely undo only the same revision."""
    import asyncio

    await asyncio.sleep(20)
    desk = get_desk()
    status = await desk.call("status")
    revision = p["revision"]
    if status.get("revision") != revision:
        return _result(req, VALIDATOR, "Settings changed again while I was watching, so I left the newer change alone.",
                       steps=["Checked the change revision", "Skipped an outdated validation"])
    after = await desk.call("telemetry", window_s=20)
    verdict, evidence = assess(p["before"], after, p["change_kind"])
    if verdict == "undo":
        await desk.call("undo_if_revision", revision=revision, actor="validator-agent")
        narration = "The change made play worse, so I restored the previous settings."
    elif verdict == "keep":
        narration = "The change held up during 20 seconds of play, so I kept it."
    else:
        narration = "I did not get enough play data to judge the change. I kept it for now; try playing and checking again."
    return _result(req, VALIDATOR, narration,
                   cards.detail("Automatic check: " + verdict, [("Evidence", line) for line in evidence],
                                [cards.cta("Check health", "desk_diagnose"), cards.cta("Undo", "desk_undo")]),
                   ["Watched a fresh 20-second play window", "Compared with the pre-change baseline", verdict])


HANDLERS: dict[str, tuple[str, dict[str, Handler]]] = {
    "setup": (SETUP, {"plan_setup": plan_setup, "apply_setup": apply_setup, "custom_setup": custom_setup, "invert": invert}),
    "tuner": (TUNER, {"tune": tune, "verify": verify}),
    "doctor": (DOCTOR, {"diagnose": run_diagnosis}),
    "validator": (VALIDATOR, {"validate": validate}),
}


def build_specialists(seed_base: str, resolve=None) -> dict[str, Agent]:
    return {role: _make_agent(f"desk-{role}", label, f"{seed_base}-{role}", handlers, resolve)
            for role, (label, handlers) in HANDLERS.items()}
