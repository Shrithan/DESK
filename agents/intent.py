"""Turn a chat message into a DESK intent.

Uses the ASI:One LLM (ASI1 API) when ASI_ONE_API_KEY is set, and a deterministic
keyword parser otherwise or whenever the LLM call fails. The LLM output is
validated against the same schema, so a bad answer can never become an action.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Literal

import httpx

from agents.profiles import PROFILES, find_profile

log = logging.getLogger(__name__)

Kind = Literal["setup", "tune", "diagnose", "status", "recalibrate", "pause", "resume", "undo", "invert", "verify", "help"]
KINDS = {"setup", "tune", "diagnose", "status", "recalibrate", "pause", "resume", "undo", "invert", "verify", "help"}
ASI1_URL = os.environ.get("ASI_ONE_BASE_URL", "https://api.asi1.ai/v1") + "/chat/completions"
ASI1_MODEL = os.environ.get("ASI_ONE_MODEL", "asi1-mini")


@dataclass
class Intent:
    kind: Kind
    game: str | None = None
    direction: Literal["less", "more", "auto"] = "auto"
    axis: Literal["forward", "right"] | None = None
    source: str = "keywords"
    extras: dict = field(default_factory=dict)


def _has(t: str, *words: str) -> bool:
    return any(re.search(rf"\b{re.escape(w)}", t) for w in words)


def _axis(t: str) -> str | None:
    if _has(t, "turn", "steer", "left", "right", "side", "a/d", "a and d", "lane"):
        return "right"
    if _has(t, "forward", "back", "gas", "brake", "accelerat", "speed", "jump", "w/s", "w and s", "up", "down", "roll"):
        return "forward"
    return None


def parse_keywords(text: str) -> Intent:
    t = (text or "").lower().strip()
    if _has(t, "undo", "revert", "go back", "put it back"):
        return Intent("undo")
    if _has(t, "recalibrat", "calibrat", "zero", "reset straight"):
        return Intent("recalibrate")
    if _has(t, "check result", "did it work", "better now", "verify", "compare"):
        return Intent("verify")
    # "it keeps stopping" is a problem report, not a pause request
    if _has(t, "not working", "doesn't work", "isn't working", "stopp", "keeps los", "lost", "broken", "why",
            "wrong", "diagnos", "doctor", "problem", "issue", "laggy", "lag", "glitch", "dead"):
        return Intent("diagnose")
    if _has(t, "twitch", "jitter", "flicker", "too sensitive", "less sensitive", "oversensitive", "jumpy", "shaky",
            "too easy", "by accident", "accidental"):
        return Intent("tune", direction="less", axis=_axis(t))
    if _has(t, "more sensitive", "not sensitive", "too much tilt", "tilt too far", "tilt too much", "have to tilt", "lean too much", "hard to", "barely", "unresponsive",
            "not responding", "doesn't respond", "too stiff", "harder than"):
        return Intent("tune", direction="more", axis=_axis(t))
    if _has(t, "tune", "sensitiv", "optimi", "adjust"):
        return Intent("tune", axis=_axis(t))
    if _has(t, "invert", "reverse", "swap", "backwards", "opposite"):
        return Intent("invert", axis=_axis(t) or "forward")
    if _has(t, "pause", "disable", "turn off", "stop"):
        return Intent("pause")
    if _has(t, "resume", "unpause", "enable", "turn on", "start again", "continue"):
        return Intent("resume")
    if _has(t, "status", "settings", "how is", "what are", "current"):
        return Intent("status")
    profile = find_profile(t)
    if profile or _has(t, "set up", "setup", "set me up", "configure", "controller for", "play", "game"):
        return Intent("setup", game=profile.id if profile else None)
    return Intent("help")


SYSTEM_PROMPT = (
    "You route messages for DESK, a system that turns the tilt of a can into keyboard keys (WASD or arrows). "
    "Reply with ONLY a JSON object: {\"kind\": one of " + json.dumps(sorted(KINDS)) + ", "
    "\"game\": one of " + json.dumps(sorted(PROFILES)) + " or null, "
    "\"direction\": \"less\"|\"more\"|\"auto\", \"axis\": \"forward\"|\"right\"|null}. "
    "kind meanings: setup=configure DESK for a game; tune=change sensitivity (less=twitchy/too sensitive, more=unresponsive); "
    "diagnose=something is broken or keeps stopping; status=show settings; recalibrate=reset what straight means; "
    "pause/resume=turn controls off/on; undo=revert last change; invert=flip a direction; verify=check whether the last tuning helped; help=anything else. "
    "axis: right = left/right steering, forward = forward/back."
)


async def parse_llm(text: str, api_key: str, timeout_s: float = 6.0) -> Intent | None:
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.post(ASI1_URL, headers={"Authorization": f"Bearer {api_key}"}, json={
                "model": ASI1_MODEL, "temperature": 0,
                "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": text[:500]}],
            })
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
        data = json.loads(content[content.index("{"): content.rindex("}") + 1])
        kind = data.get("kind")
        if kind not in KINDS:
            return None
        game = data.get("game") if data.get("game") in PROFILES else None
        direction = data.get("direction") if data.get("direction") in ("less", "more", "auto") else "auto"
        axis = data.get("axis") if data.get("axis") in ("forward", "right") else None
        return Intent(kind, game=game, direction=direction, axis=axis, source="asi1")
    except Exception as exc:  # network, quota, bad JSON: fall back
        log.warning("ASI1 intent parse failed, using keywords: %s", exc)
        return None


async def parse_intent(text: str) -> Intent:
    key = os.environ.get("ASI_ONE_API_KEY")
    if key:
        llm = await parse_llm(text, key)
        if llm is not None:
            # the keyword parser is better at spotting game names; merge it in
            if llm.kind == "setup" and llm.game is None:
                llm.game = parse_keywords(text).game
            return llm
    return parse_keywords(text)
