"""Key backend interface and the edge-triggered output stage."""

from __future__ import annotations

import logging
from typing import Protocol

log = logging.getLogger(__name__)


class KeyBackend(Protocol):
    """Anything that can press and release a named key."""

    def key_down(self, key: str) -> None: ...
    def key_up(self, key: str) -> None: ...
    def close(self) -> None: ...


def key_edges(prev: frozenset[str], new: frozenset[str]) -> tuple[list[str], list[str]]:
    """Return (keys to press, keys to release), each sorted for determinism."""
    return sorted(new - prev), sorted(prev - new)


class EdgeTriggeredOutput:
    """Sends key_down only when a key starts and key_up only when it stops."""

    def __init__(self, backend: KeyBackend) -> None:
        self.backend = backend
        self._held: frozenset[str] = frozenset()

    @property
    def held(self) -> frozenset[str]:
        return self._held

    def set_held(self, new: frozenset[str]) -> None:
        downs, ups = key_edges(self._held, new)
        held = set(self._held)
        # Releases first so a remap or axis flip never has both keys down at once.
        for key in ups:
            try:
                self.backend.key_up(key)
            except Exception:
                log.exception("key_up(%r) failed; treating it as released", key)
            held.discard(key)
        for key in downs:
            try:
                self.backend.key_down(key)
            except Exception:
                log.exception("key_down(%r) failed; not marking it held", key)
                continue
            held.add(key)
        self._held = frozenset(held)

    def release_all(self) -> None:
        self.set_held(frozenset())
