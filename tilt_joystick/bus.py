"""Tiny in-process event bus: joystick {x,y,mag}, key_down/key_up {key}, status {...}.

The repo had no event bus in this path (the web UI polls HTTP), so this is the one the
tilt joystick publishes on. Subscribers get (name, payload); a failing subscriber is logged
and never stops the control loop.
"""
from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from typing import Callable, TextIO

log = logging.getLogger(__name__)
Handler = Callable[[str, dict], None]


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, name: str, handler: Handler) -> None:
        """name '*' receives every event."""
        self._subs[name].append(handler)

    def publish(self, name: str, payload: dict) -> None:
        for handler in self._subs.get(name, []) + self._subs.get('*', []):
            try:
                handler(name, payload)
            except Exception:
                log.exception('event handler failed for %s', name)


class JsonlSink:
    """Writes every event as a JSON line (used for --events-log)."""

    def __init__(self, stream: TextIO) -> None:
        self.stream = stream

    def __call__(self, name: str, payload: dict) -> None:
        self.stream.write(json.dumps({'t': round(time.time(), 4), 'event': name, **payload}) + '\n')
        self.stream.flush()


class BusKeyBackend:
    """KeyBackend wrapper: forwards to a real backend, then publishes key_down/key_up."""

    def __init__(self, inner, bus: EventBus) -> None:
        self.inner, self.bus = inner, bus

    def key_down(self, key: str) -> None:
        self.inner.key_down(key)
        self.bus.publish('key_down', {'key': key})

    def key_up(self, key: str) -> None:
        try:
            self.inner.key_up(key)
        finally:
            self.bus.publish('key_up', {'key': key})

    def close(self) -> None:
        self.inner.close()
