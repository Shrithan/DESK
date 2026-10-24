"""Run tilt-to-keys.

    # one command, built-in scripted simulator, log backend (no real presses)
    python -m backend.tilt_keys.run --simulate

    # read tilt_update JSON lines from another process
    python -m backend.tilt_keys.simulator scripted | python -m backend.tilt_keys.run --input stdin

    # accept tilt_update/tilt_command on ws://HOST:PORT/ws/tilt; key_state is served on /ws/keys
    python -m backend.tilt_keys.run --input ws --backend pynput,websocket

    # also serve the agent control API on ws://HOST:PORT/ws/control (used by the DESK Fetch.ai agents)
    python -m backend.tilt_keys.run --input ws --backend pynput,websocket --control

Backend: --backend or TILT_KEYS_BACKEND (default "log"). Config: --config or TILT_KEYS_CONFIG.
All keys are released on exit, Ctrl+C, SIGTERM, stale input, and crashes.
"""

from __future__ import annotations

import argparse
import asyncio
import atexit
import json
import logging
import os
import signal
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import replace

from backend.tilt_keys.backends import (
    CompositeKeyBackend,
    LogKeyBackend,
    PynputKeyBackend,
    WebSocketKeyBackend,
    parse_backend_names,
)
from backend.tilt_keys.config import TiltKeyConfig
from backend.tilt_keys.control import ControlService
from backend.tilt_keys.controller import TiltKeyController
from backend.tilt_keys.output import KeyBackend
from backend.tilt_keys.telemetry import Telemetry

log = logging.getLogger("tilt_keys.run")

Source = Callable[[TiltKeyController], Awaitable[None]]
TILT_PATH = "/ws/tilt"
KEYS_PATH = "/ws/keys"
CONTROL_PATH = "/ws/control"


# ------------------------------------------------------------------ run loop
async def watchdog(controller: TiltKeyController) -> None:
    period = controller.config.watchdog_period_ms / 1000
    while True:
        controller.tick()
        await asyncio.sleep(period)


async def run_controller(
    controller: TiltKeyController,
    sources: list[Source],
    *,
    install_signal_handlers: bool = True,
) -> None:
    """Run input sources + watchdog until a source ends, a signal arrives, or
    something raises. Always releases every key on the way out."""
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    signals = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP) if install_signal_handlers else ()
    for sig in signals:
        loop.add_signal_handler(sig, stop.set)
    tasks: list[asyncio.Task] = []
    try:
        tasks = [asyncio.create_task(src(controller)) for src in sources]
        tasks.append(asyncio.create_task(watchdog(controller)))
        stopper = asyncio.create_task(stop.wait())
        tasks.append(stopper)
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            if task is not stopper:
                task.result()  # re-raise a source crash
        log.info("stopping: %s", "signal received" if stopper in done else "input source finished")
    finally:
        controller.shutdown("exit")
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for sig in signals:
            loop.remove_signal_handler(sig)


# ------------------------------------------------------------------ sources
async def stdin_source(controller: TiltKeyController) -> None:
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin)
    while line := await reader.readline():
        if line.strip():
            controller.handle_message(line)


def simulated_source(noise: float, bias_forward: float, bias_right: float) -> Source:
    from backend.tilt_keys.simulator import scripted_frames

    async def source(controller: TiltKeyController) -> None:
        t0 = time.monotonic()
        for t, label, msg in scripted_frames(noise_deg=noise, bias_forward_deg=bias_forward, bias_right_deg=bias_right):
            await asyncio.sleep(max(0.0, t0 + t - time.monotonic()))
            if label:
                print(f"--- sim: {label}", flush=True)
            controller.handle_message(msg)

    return source


class WebSocketHub:
    """Serves /ws/tilt (input) and /ws/keys (key_state subscribers) on one port."""

    def __init__(self, host: str, port: int) -> None:
        self.host, self.port = host, port
        self.key_clients: set = set()
        self.controller: TiltKeyController | None = None
        self.control: ControlService | None = None
        self.accept_input = False
        self.ready = asyncio.Event()
        self.bound_port: int | None = None

    def broadcast(self, message: str) -> None:
        from websockets.asyncio.server import broadcast

        broadcast(self.key_clients, message)

    async def _handler(self, connection) -> None:
        path = connection.request.path
        if path == KEYS_PATH:
            self.key_clients.add(connection)
            try:
                await connection.wait_closed()
            finally:
                self.key_clients.discard(connection)
        elif path == TILT_PATH and self.accept_input and self.controller is not None:
            log.info("tilt producer connected from %s", connection.remote_address)
            async for message in connection:
                self.controller.handle_message(message)
            log.info("tilt producer disconnected; stale watchdog will release keys")
        elif path == CONTROL_PATH and self.control is not None:
            log.info("control client connected from %s", connection.remote_address)
            async for message in connection:
                try:
                    request = json.loads(message)
                except ValueError:
                    request = None
                await connection.send(json.dumps(self.control.handle(request)))
        else:
            await connection.close(code=1008, reason=f"unknown path {path}")

    async def serve_forever(self, controller: TiltKeyController) -> None:
        from websockets.asyncio.server import serve

        self.controller = controller
        async with serve(self._handler, self.host, self.port) as server:
            self.bound_port = server.sockets[0].getsockname()[1]
            self.ready.set()
            log.info("websocket listening on ws://%s:%d (%s, %s)", self.host, self.bound_port, TILT_PATH, KEYS_PATH)
            await server.serve_forever()


# ------------------------------------------------------------------ CLI
def build_backend(names: list[str], hub: WebSocketHub | None, status) -> KeyBackend:
    backends: list[KeyBackend] = []
    for name in names:
        if name == "log":
            backends.append(LogKeyBackend())
        elif name == "pynput":
            backends.append(PynputKeyBackend())
        elif name == "websocket":
            assert hub is not None
            backends.append(WebSocketKeyBackend(hub.broadcast, status))
    return backends[0] if len(backends) == 1 else CompositeKeyBackend(backends)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--backend", default=os.environ.get("TILT_KEYS_BACKEND", "log"),
                   help="comma list of log, pynput, websocket (default: $TILT_KEYS_BACKEND or log)")
    p.add_argument("--input", choices=("stdin", "ws", "none"), default="stdin",
                   help="where tilt_update messages come from (default stdin)")
    p.add_argument("--simulate", action="store_true", help="feed the built-in scripted simulator (implies --input none)")
    p.add_argument("--noise", type=float, default=0.0, help="--simulate jitter std dev, degrees")
    p.add_argument("--bias-forward", type=float, default=0.0, help="--simulate constant lean, degrees")
    p.add_argument("--bias-right", type=float, default=0.0, help="--simulate constant lean, degrees")
    p.add_argument("--config", default=os.environ.get("TILT_KEYS_CONFIG"), help=".toml or .json config file")
    p.add_argument("--no-calibrate", action="store_true", help="skip neutral calibration (offset = 0)")
    p.add_argument("--control", action="store_true",
                   help=f"serve the agent control API on ws://HOST:PORT{CONTROL_PATH}")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8766)
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s.%(msecs)03d %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    config = TiltKeyConfig.from_file(args.config) if args.config else TiltKeyConfig()
    if args.no_calibrate:
        config = replace(config, calibration_duration_ms=0)
    names = parse_backend_names(args.backend)
    if args.simulate:
        args.input = "none"

    hub = WebSocketHub(args.host, args.port) if (args.input == "ws" or "websocket" in names or args.control) else None
    controller_ref: list[TiltKeyController] = []
    status = lambda: (controller_ref[0].enabled, controller_ref[0].mode) if controller_ref else (True, "calibrating")  # noqa: E731
    telemetry = Telemetry()
    controller = TiltKeyController(config, build_backend(names, hub, status),
                                   on_event=telemetry.on_event, on_sample=telemetry.on_sample)
    controller_ref.append(controller)
    if hub is not None and args.control:
        hub.control = ControlService(controller, telemetry)
    atexit.register(controller.shutdown, "atexit")  # last resort if the loop is torn down abnormally

    sources: list[Source] = []
    if args.input == "stdin":
        sources.append(stdin_source)
    if args.simulate:
        sources.append(simulated_source(args.noise, args.bias_forward, args.bias_right))
    if hub is not None:
        hub.accept_input = args.input == "ws"
        sources.append(hub.serve_forever)
    if not sources:
        p.error("no input: use --input stdin|ws or --simulate")

    log.info("tilt-to-keys starting: backend=%s input=%s config=%s", ",".join(names),
             "simulate" if args.simulate else args.input, json.dumps(config.to_dict(), separators=(",", ":")))
    try:
        asyncio.run(run_controller(controller, sources))
    except KeyboardInterrupt:
        pass
    finally:
        controller.shutdown("exit")


if __name__ == "__main__":
    main()
