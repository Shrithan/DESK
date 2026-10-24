"""Shared simulated DESK for demos: serves the FakeDesk player on the same
control API the real tilt-to-keys uses (ws://127.0.0.1:8766/ws/control).

Run this once, then start the agents WITHOUT DESK_DEMO_MODE so the Coach and
the specialists (in separate processes) all see the SAME simulated player:

    python -m agents.demo_desk            # scenario from DESK_DEMO_SCENARIO (default "twitchy")
"""

from __future__ import annotations

import asyncio
import json
import os

from agents.desk_link import DeskError, FakeDesk


async def main(host: str = "127.0.0.1", port: int = 8766) -> None:
    from websockets.asyncio.server import serve

    desk = FakeDesk(os.environ.get("DESK_DEMO_SCENARIO", "twitchy"))

    async def handler(ws) -> None:
        async for raw in ws:
            try:
                req = json.loads(raw)
                rid, op = req.pop("id", None), req.pop("op")
                result = await desk.call(op, **req)
                reply = {"id": rid, "ok": True, "result": result}
            except (DeskError, KeyError, ValueError, TypeError) as exc:
                reply = {"id": None, "ok": False, "error": str(exc)}
            await ws.send(json.dumps(reply))

    async with serve(handler, host, port) as server:
        print(f"Simulated DESK ({desk.scenario}) serving ws://{host}:{port}/ws/control  (Ctrl+C to stop)")
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
