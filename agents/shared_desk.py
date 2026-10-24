"""One Desk connection shared by every agent in the process (so demo mode has one shared simulated DESK)."""

from __future__ import annotations

from agents.desk_link import Desk, make_desk

_desk: Desk | None = None


def get_desk() -> Desk:
    global _desk
    if _desk is None:
        _desk = make_desk()
    return _desk


def set_desk(desk: Desk) -> None:
    global _desk
    _desk = desk
