"""The standalone Coach must route to the separate specialist Bureau."""

import asyncio

from uagents.crypto import Identity
from uagents.dispatch import dispatcher

from agents.run import build_standalone_coach
from agents.specialists import HANDLERS


def test_coach_does_not_register_dormant_specialists(monkeypatch):
    asyncio.set_event_loop(asyncio.new_event_loop())
    monkeypatch.setenv("DESK_AGENT_SEED", "test-launcher-seed")
    monkeypatch.setenv("DESK_NO_MAILBOX", "1")
    coach = build_standalone_coach()
    for role in HANDLERS:
        address = Identity.from_seed(f"test-launcher-seed-{role}", 0).address
        assert coach._desk_coach.specialists[role] == address
        assert not dispatcher.contains(address)
