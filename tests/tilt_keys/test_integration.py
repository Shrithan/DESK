"""Smoke tests across process / network boundaries."""

import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path

from backend.tilt_keys.backends import WebSocketKeyBackend
from backend.tilt_keys.config import TiltKeyConfig
from backend.tilt_keys.controller import TiltKeyController
from backend.tilt_keys.run import KEYS_PATH, TILT_PATH, WebSocketHub, run_controller
from backend.tilt_keys.simulator import scripted_frames

ROOT = Path(__file__).resolve().parents[2]


def key_events(text):
    return re.findall(r"KEY (DOWN|UP)\s+(\w+)", text)


EXPECTED_SCRIPTED = [("DOWN", "w"), ("UP", "w"), ("DOWN", "a"), ("DOWN", "w"), ("UP", "a"), ("UP", "w")]


def test_scripted_simulator_through_stdin_pipe():
    """simulator | runner as real subprocesses, with jitter and a calibration bias."""
    sim = subprocess.Popen(
        [sys.executable, "-m", "backend.tilt_keys.simulator", "scripted", "--noise", "0.5",
         "--bias-forward", "2", "--bias-right", "-1"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    run = subprocess.run(
        [sys.executable, "-m", "backend.tilt_keys.run", "--input", "stdin", "--backend", "log"],
        cwd=ROOT, stdin=sim.stdout, capture_output=True, text=True, timeout=60,
    )
    sim.wait(timeout=5)
    assert run.returncode == 0, run.stderr
    assert key_events(run.stdout) == EXPECTED_SCRIPTED, run.stdout
    assert "calibration_complete" in run.stdout


def test_websocket_input_and_key_state_output():
    """Producer -> /ws/tilt -> controller -> websocket backend -> /ws/keys subscriber."""
    from websockets.asyncio.client import connect

    async def scenario():
        hub = WebSocketHub("127.0.0.1", 0)
        hub.accept_input = True
        controller = TiltKeyController(
            TiltKeyConfig(calibration_duration_ms=0, filter_enabled=False),
            WebSocketKeyBackend(hub.broadcast),
        )
        received = []

        async def client(ctl):
            await hub.ready.wait()
            base = f"ws://127.0.0.1:{hub.bound_port}"
            async with connect(base + KEYS_PATH) as keys, connect(base + TILT_PATH) as tilt:
                await asyncio.sleep(0.05)  # let the subscriber register
                frames = [m for _, _, m in scripted_frames(rate_hz=30)][75:150]  # 20 deg forward + 12 deg segments
                for msg in frames:
                    await tilt.send(json.dumps(msg))
                    await asyncio.sleep(0.005)
                received.append(json.loads(await asyncio.wait_for(keys.recv(), 2)))
                # stop sending: stale watchdog must release W within ~200 ms
                received.append(json.loads(await asyncio.wait_for(keys.recv(), 2)))

        await run_controller(controller, [hub.serve_forever, client], install_signal_handlers=False)
        return received

    received = asyncio.run(scenario())
    assert received[0]["type"] == "key_state" and received[0]["held"] == ["w"]
    assert received[1]["held"] == []
