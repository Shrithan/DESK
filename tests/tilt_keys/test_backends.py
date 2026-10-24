import io
import json

import pytest

from backend.tilt_keys.backends import (
    CompositeKeyBackend,
    LogKeyBackend,
    PynputKeyBackend,
    WebSocketKeyBackend,
    parse_backend_names,
)
from shared.contracts.tilt import KeyState


class FakePynputController:
    """Stands in for pynput.keyboard.Controller so tests never press real keys."""

    def __init__(self):
        self.calls = []

    def press(self, key):
        self.calls.append(("press", key))

    def release(self, key):
        self.calls.append(("release", key))


def test_log_backend_prints_events():
    buf = io.StringIO()
    be = LogKeyBackend(buf)
    be.key_down("w")
    be.key_down("a")
    be.key_up("w")
    lines = buf.getvalue().splitlines()
    assert "KEY DOWN w" in lines[0] and "held=['w']" in lines[0]
    assert "held=['a', 'w']" in lines[1]
    assert "KEY UP   w" in lines[2]


def test_pynput_backend_uses_press_release_and_named_keys():
    pytest.importorskip("pynput")
    from pynput.keyboard import Key

    fake = FakePynputController()
    be = PynputKeyBackend(controller=fake)
    be.key_down("w")
    be.key_down("up")
    be.key_up("w")
    assert fake.calls == [("press", "w"), ("press", Key.up), ("release", "w")]
    be.close()  # releases the still-pressed "up"
    assert fake.calls[-1] == ("release", Key.up)


def test_pynput_backend_rejects_unknown_key_name():
    pytest.importorskip("pynput")
    be = PynputKeyBackend(controller=FakePynputController())
    with pytest.raises(ValueError, match="unknown key name"):
        be.key_down("notakey")


def test_websocket_backend_broadcasts_valid_key_state():
    sent = []
    be = WebSocketKeyBackend(sent.append, status_provider=lambda: (True, "active"))
    be.key_down("w")
    be.key_down("a")
    be.key_up("w")
    msgs = [KeyState.model_validate(json.loads(s)) for s in sent]
    assert [m.held for m in msgs] == [["w"], ["a", "w"], ["a"]]
    be.close()
    assert json.loads(sent[-1])["held"] == []


def test_composite_backend_continues_after_one_fails():
    class Broken:
        def key_down(self, k):
            raise RuntimeError

        def key_up(self, k):
            raise RuntimeError

        def close(self):
            raise RuntimeError

    buf = io.StringIO()
    log_be = LogKeyBackend(buf)
    comp = CompositeKeyBackend([Broken(), log_be])
    comp.key_down("w")
    comp.key_up("w")
    comp.close()
    assert "KEY DOWN w" in buf.getvalue() and "KEY UP" in buf.getvalue()


def test_parse_backend_names():
    assert parse_backend_names("log") == ["log"]
    assert parse_backend_names("pynput, websocket") == ["pynput", "websocket"]
    with pytest.raises(ValueError):
        parse_backend_names("xdotool")
