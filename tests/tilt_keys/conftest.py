from dataclasses import replace

import pytest

from backend.tilt_keys.config import TiltKeyConfig
from backend.tilt_keys.controller import TiltKeyController
from shared.contracts.tilt import TiltUpdate

FRAME_MS = 33  # ~30 Hz
T0_MS = 1_792_820_000_000


class RecordingBackend:
    """Records every key event; fails the test on a duplicate edge."""

    def __init__(self):
        self.events: list[tuple[str, str]] = []
        self.down: set[str] = set()
        self.closed = False

    def key_down(self, key):
        assert key not in self.down, f"key_down({key!r}) sent twice in a row"
        self.down.add(key)
        self.events.append(("down", key))

    def key_up(self, key):
        assert key in self.down, f"key_up({key!r}) for a key that is not down"
        self.down.discard(key)
        self.events.append(("up", key))

    def close(self):
        self.closed = True


class Rig:
    """Controller + fake backend + fake clock. Feeds updates at 30 Hz."""

    def __init__(self, config: TiltKeyConfig):
        self.backend = RecordingBackend()
        self.events: list[tuple[str, dict]] = []
        self.now_ms = 0
        self.ts_ms = T0_MS
        self.ctl = TiltKeyController(
            config, self.backend, clock_ms=lambda: self.now_ms, on_event=lambda n, d: self.events.append((n, d))
        )

    def feed(self, forward, right, *, frames=1, can_found=True):
        for _ in range(frames):
            self.now_ms += FRAME_MS
            self.ts_ms += FRAME_MS
            self.ctl.handle_update(
                TiltUpdate(timestamp_ms=self.ts_ms, forward_deg=forward, right_deg=right, can_found=can_found)
            )
            self.ctl.tick()

    def advance(self, ms):
        self.now_ms += ms
        self.ctl.tick()

    @property
    def held(self):
        return self.ctl.held

    def event_names(self):
        return [n for n, _ in self.events]


NO_FILTER_NO_CAL = TiltKeyConfig(filter_enabled=False, calibration_duration_ms=0)


@pytest.fixture
def rig():
    return Rig(NO_FILTER_NO_CAL)


@pytest.fixture
def make_rig():
    def _make(**overrides):
        return Rig(replace(NO_FILTER_NO_CAL, **overrides))

    return _make
