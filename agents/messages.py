"""Agent-to-agent messages between the Coach and the specialists."""

from __future__ import annotations

from uagents import Model


class TaskRequest(Model):
    request_id: str
    user: str  # the ASI:One user this work is for (used for per-user memory)
    kind: str  # plan_setup | apply_setup | custom_setup | invert | tune | verify | diagnose
    params_json: str = "{}"


class TaskResult(Model):
    request_id: str
    ok: bool
    agent: str
    narration: str
    steps: list[str] = []  # what the specialist actually did, shown to the user
    card_kind: str | None = None
    card_json: str | None = None
    validation_json: str | None = None
