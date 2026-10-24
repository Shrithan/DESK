"""How the agents reach the running tilt-to-keys process.

DeskLink  : real connection, JSON over ws://127.0.0.1:8766/ws/control
            (start tilt-to-keys with --control).
FakeDesk  : the real ControlService + TiltKeyController + Telemetry, driven by a
            simulated player instead of cameras. Used by tests and by
            DESK_DEMO_MODE=1 so the agents can be tried with no hardware.
            Every reply from it is marked "simulated": true.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import math
import os
import random
import time
from typing import Any, Protocol

from backend.tilt_keys.config import TiltKeyConfig
from backend.tilt_keys.control import ControlService
from backend.tilt_keys.controller import TiltKeyController
from backend.tilt_keys.telemetry import Telemetry

DEFAULT_URL = "ws://127.0.0.1:8766/ws/control"


class DeskUnavailable(RuntimeError):
    pass


class DeskError(RuntimeError):
    pass


class Desk(Protocol):
    async def call(self, op: str, **params: Any) -> dict: ...


class DeskLink:
    def __init__(self, url: str | None = None, timeout_s: float = 3.0) -> None:
        self.url = url or os.environ.get("DESK_CONTROL_URL", DEFAULT_URL)
        self.timeout_s = timeout_s
        self._ids = itertools.count(1)

    async def call(self, op: str, **params: Any) -> dict:
        from websockets.asyncio.client import connect

        req_id = str(next(self._ids))
        try:
            async with asyncio.timeout(self.timeout_s):
                async with connect(self.url, proxy=None) as ws:  # local only; never via a proxy
                    await ws.send(json.dumps({"id": req_id, "op": op, **params}))
                    reply = json.loads(await ws.recv())
        except (OSError, TimeoutError, asyncio.TimeoutError) as exc:
            raise DeskUnavailable(
                f"can't reach tilt-to-keys at {self.url}. Is it running with --control? ({type(exc).__name__})"
            ) from exc
        if not reply.get("ok"):
            raise DeskError(reply.get("error", "unknown error"))
        return reply["result"]


class _NullBackend:
    def key_down(self, key: str) -> None: ...
    def key_up(self, key: str) -> None: ...
    def close(self) -> None: ...


class FakeDesk:
    """Simulated player. scenario: "twitchy" (steering wobble near the trigger),
    "dark" (camera keeps losing the can), or "calm"."""

    FPS = 30

    def __init__(self, scenario: str = "twitchy", seed: int = 7, start_s: float = 60.0) -> None:
        self.scenario = scenario
        self._rng = random.Random(seed)
        self._now_ms = 1_000_000
        clock = lambda: self._now_ms  # noqa: E731
        self.telemetry = Telemetry(clock_ms=clock)
        cfg = TiltKeyConfig(calibration_duration_ms=0)
        self.controller = TiltKeyController(cfg, _NullBackend(), clock_ms=clock,
                                            on_event=self.telemetry.on_event, on_sample=self.telemetry.on_sample)
        self.service = ControlService(self.controller, self.telemetry)
        self._t = 0.0
        self._wall = time.monotonic()
        self.advance(start_s)

    def advance(self, seconds: float) -> None:
        for _ in range(int(seconds * self.FPS)):
            self._t += 1 / self.FPS
            self._now_ms += 1000 // self.FPS
            self.controller.handle_message(self._frame(self._t), now_ms=self._now_ms)
            self.controller.tick(now_ms=self._now_ms)

    def _frame(self, t: float) -> dict:
        r = self._rng
        # gas: hold forward for 2 s out of every 5 s; steering: deliberate turns + wobble
        forward = (24.0 if (t % 5) < 2 else 0.0) + r.gauss(0, 1.5)
        turn = 26.0 if (t % 7) < 1 else (-26.0 if 3.5 < (t % 7) < 4.5 else 0.0)
        wobble = 13.5 * math.sin(2 * math.pi * 0.9 * t) if self.scenario == "twitchy" else 4 * math.sin(2 * math.pi * 0.9 * t)
        right = turn + wobble + r.gauss(0, 1.5)
        found = not (self.scenario == "dark" and (t % 4) < 0.7)
        return {"type": "tilt_update", "timestamp_ms": self._now_ms, "forward_deg": round(forward, 2),
                "right_deg": round(right, 2), "can_found": found}

    async def call(self, op: str, **params: Any) -> dict:
        # catch up on the "play" that happened since the last call (capped)
        now = time.monotonic()
        self.advance(min(60.0, now - self._wall))
        self._wall = now
        reply = self.service.handle({"id": "0", "op": op, **params})
        if op == "recalibrate":
            self.advance(self.controller.config.calibration_duration_ms / 1000 + 0.5)
        if not reply["ok"]:
            raise DeskError(reply["error"])
        result = reply["result"]
        if isinstance(result, dict):
            result["simulated"] = True
        return result


def make_desk() -> Desk:
    if os.environ.get("DESK_DEMO_MODE", "").lower() in ("1", "true", "yes"):
        return FakeDesk(os.environ.get("DESK_DEMO_SCENARIO", "twitchy"))
    return DeskLink()
