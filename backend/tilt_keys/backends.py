"""Pluggable key output backends. All implement output.KeyBackend."""

from __future__ import annotations

import ctypes
import json
import logging
import sys
import time
from collections.abc import Callable
from datetime import datetime
from typing import TextIO

from backend.tilt_keys.output import KeyBackend
from shared.contracts.tilt import KeyState

log = logging.getLogger(__name__)

BACKEND_NAMES = ("log", "pynput", "websocket")


def now_unix_ms() -> int:
    return time.time_ns() // 1_000_000


class LogKeyBackend:
    """Prints key events with timestamps; never touches the real keyboard."""

    def __init__(self, stream: TextIO | None = None) -> None:
        self.stream = stream or sys.stdout
        self.held: set[str] = set()

    def _print(self, action: str, key: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"{stamp}  KEY {action:<4} {key:<6} held={sorted(self.held)}", file=self.stream, flush=True)

    def key_down(self, key: str) -> None:
        self.held.add(key)
        self._print("DOWN", key)

    def key_up(self, key: str) -> None:
        self.held.discard(key)
        self._print("UP", key)

    def close(self) -> None:
        if self.held:
            print(f"WARNING: log backend closed with keys still held: {sorted(self.held)}", file=self.stream, flush=True)


def macos_accessibility_trusted() -> bool | None:
    """True/False on macOS via AXIsProcessTrusted(); None elsewhere or if unknown."""
    if sys.platform != "darwin":
        return None
    try:
        lib = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
        lib.AXIsProcessTrusted.restype = ctypes.c_bool
        return bool(lib.AXIsProcessTrusted())
    except (OSError, AttributeError):
        return None


class PynputKeyBackend:
    """Real key presses via pynput.keyboard.Controller().press/release (pynput 1.7+).

    Keys are 1-character strings or names of pynput.keyboard.Key members
    ("up", "space", "shift", ...).
    """

    def __init__(self, controller=None) -> None:
        from pynput import keyboard  # imported lazily so tests/log mode never need it

        self._keyboard = keyboard
        self._controller = controller if controller is not None else keyboard.Controller()
        self._pressed: set[str] = set()
        trusted = macos_accessibility_trusted()
        if trusted is False:
            log.error(
                "macOS Accessibility permission is NOT granted to this terminal app: key presses will be "
                "silently dropped. Enable it in System Settings > Privacy & Security > Accessibility, then restart the terminal."
            )

    def resolve(self, key: str):
        if len(key) == 1:
            return key
        member = getattr(self._keyboard.Key, key, None)
        if member is None:
            raise ValueError(f"unknown key name {key!r}; use one character or a pynput Key name like 'up' or 'space'")
        return member

    def key_down(self, key: str) -> None:
        self._controller.press(self.resolve(key))
        self._pressed.add(key)

    def key_up(self, key: str) -> None:
        try:
            self._controller.release(self.resolve(key))
        finally:
            self._pressed.discard(key)

    def close(self) -> None:
        # Belt and braces: release anything we ever pressed and did not release.
        for key in list(self._pressed):
            try:
                self.key_up(key)
            except Exception:
                log.exception("failed to release %r on close", key)


class WebSocketKeyBackend:
    """Broadcasts a key_state message (shared.contracts.tilt.KeyState) on every change."""

    def __init__(
        self,
        broadcast: Callable[[str], None],
        status_provider: Callable[[], tuple[bool, str]] | None = None,
    ) -> None:
        self._broadcast = broadcast
        self._status_provider = status_provider
        self.held: set[str] = set()

    def message(self) -> str:
        enabled, mode = self._status_provider() if self._status_provider else (True, "active")
        return KeyState(timestamp_ms=now_unix_ms(), held=sorted(self.held), enabled=enabled, mode=mode).model_dump_json()

    def _send(self) -> None:
        try:
            self._broadcast(self.message())
        except Exception:
            log.exception("key_state broadcast failed")

    def key_down(self, key: str) -> None:
        self.held.add(key)
        self._send()

    def key_up(self, key: str) -> None:
        self.held.discard(key)
        self._send()

    def close(self) -> None:
        self.held.clear()
        self._send()


class CompositeKeyBackend:
    """Fans each event out to several backends; one failing does not stop the others."""

    def __init__(self, backends: list[KeyBackend]) -> None:
        self.backends = backends

    def _each(self, method: str, *args) -> None:
        errors = []
        for backend in self.backends:
            try:
                getattr(backend, method)(*args)
            except Exception as exc:
                log.exception("%s.%s failed", type(backend).__name__, method)
                errors.append(exc)
        if errors and method == "key_down" and len(errors) == len(self.backends):
            raise errors[0]

    def key_down(self, key: str) -> None:
        self._each("key_down", key)

    def key_up(self, key: str) -> None:
        self._each("key_up", key)

    def close(self) -> None:
        self._each("close")


def parse_backend_names(spec: str) -> list[str]:
    names = [n.strip() for n in spec.split(",") if n.strip()]
    bad = [n for n in names if n not in BACKEND_NAMES]
    if not names or bad:
        raise ValueError(f"backend must be a comma list of {BACKEND_NAMES}, got {spec!r}")
    return names


def json_line(obj: dict) -> str:
    return json.dumps(obj, separators=(",", ":"))
