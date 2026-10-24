"""The DESK agent control API on the real camera joystick pipeline (synthetic can silhouettes)."""
import asyncio
import socket

import pytest

from agents.desk_link import DeskError, DeskLink
from tests.can_joystick.synth import feats
from tilt_joystick.agent_control import HEADROOM, JoystickControlService, serve_control
from tilt_joystick.config import Config
from tilt_joystick.estimator import Direction
from tilt_joystick.pipeline import TiltPipeline

DT = 33.3


class Recorder:
    def __init__(self):
        self.events = []

    def key_down(self, k):
        self.events.append(('down', k))

    def key_up(self, k):
        self.events.append(('up', k))

    def close(self):
        pass


@pytest.fixture(autouse=True)
def no_direction_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


class Rig:
    def __init__(self):
        self.rec = Recorder()
        self.p = TiltPipeline(Config(), self.rec, direction=Direction())
        self.t = 0.0
        self.svc = JoystickControlService(self.p, clock_ms=lambda: int(self.t))
        self.run(40)  # upright: neutral calibration
        assert self.p.estimator.phase == 'running'

    def run(self, n, deg=0.0, toward=0.0, present=True):
        for _ in range(n):
            self.p.step(feats(tilt_deg=deg, toward_deg=toward) if present else None, self.t)
            self.t += DT

    def call(self, op, **params):
        reply = self.svc.handle({'id': '1', 'op': op, **params})
        if not reply['ok']:
            raise DeskError(reply['error'])
        return reply['result']


@pytest.fixture
def rig():
    return Rig()


def test_status_reports_joystick_settings_in_degrees(rig):
    s = rig.call('status')
    assert s['mode'] == 'active' and s['calibrated'] and s['enabled']
    assert s['config']['keys'] == {'forward': 'w', 'back': 's', 'left': 'a', 'right': 'd'}
    assert s['config']['forward_back']['on_deg'] == pytest.approx(0.35 * 22, abs=0.1)
    assert s['calibration_offsets_deg'] == {'forward': None, 'right': None}


def test_telemetry_counts_tilt_and_key_presses(rig):
    rig.run(30, 25, 0)  # hold forward ~1 s
    rig.run(20, 0, 0)
    tel = rig.call('telemetry', window_s=60)
    assert tel['frames'] > 0
    assert tel['forward']['max_pos_deg'] > 10
    assert tel['keys']['w']['presses'] == 1 and tel['keys']['w']['flickers'] == 0


def test_profile_patch_remaps_keys_and_releases_held(rig):
    rig.run(20, 25, 0)
    assert rig.p.held == {'w'}
    change = rig.call('set_config', actor='setup-agent', reason='profile subway', profile='subway-surfers', patch={
        'keys': {'forward': 'up', 'back': 'down', 'left': 'left', 'right': 'right'},
        'on_threshold_deg': 12, 'off_threshold_deg': 8})
    assert rig.p.held == frozenset()  # released during the switch
    assert ('up', 'w') in rig.rec.events
    assert change['after']['keys']['forward'] == 'up'
    rig.run(20, 0, 0)
    rig.run(20, 25, 0)
    assert rig.p.held == {'up'}
    assert rig.call('status')['profile'] == 'subway-surfers'


def test_separate_left_right_trigger_uses_axis_gain(rig):
    rig.call('set_config', patch={'lr_on_threshold_deg': 15.4, 'lr_off_threshold_deg': 10})
    fwd = rig.call('status')['config']['forward_back']
    lr = rig.call('status')['config']['left_right']
    assert rig.p.gain_x == pytest.approx(fwd['on_deg'] / 15.4)
    assert lr['on_deg'] == 15.4
    assert lr['off_deg'] == pytest.approx(fwd['off_deg'] * 15.4 / fwd['on_deg'], abs=0.1)  # truthful, derived


def test_invert_forward_swaps_w_and_s(rig):
    rig.call('set_config', patch={'invert_forward': True})
    rig.run(20, 25, 0)  # tilt toward image-up
    assert rig.p.held == {'s'}


def test_high_trigger_raises_full_scale_so_it_stays_reachable(rig):
    rig.call('set_config', patch={'on_threshold_deg': 22, 'off_threshold_deg': 16})
    assert rig.p.config.keys.press <= HEADROOM + 1e-9
    assert rig.call('status')['degrees_per_full_push'] >= 22 / HEADROOM - 0.1


def test_unsafe_patch_is_refused_and_nothing_changes(rig):
    before = rig.p.config.keys
    with pytest.raises(DeskError, match='safe range'):
        rig.call('set_config', patch={'on_threshold_deg': 80})
    with pytest.raises(DeskError, match='distinct'):
        rig.call('set_config', patch={'keys': {'forward': 's'}})
    assert rig.p.config.keys == before


def test_undo_and_guarded_undo(rig):
    original = rig.p.config.keys
    first = rig.call('set_config', patch={'on_threshold_deg': 12, 'off_threshold_deg': 8})
    rig.call('set_config', patch={'on_threshold_deg': 14, 'off_threshold_deg': 9})
    with pytest.raises(DeskError, match='refusing'):
        rig.call('undo_if_revision', revision=first['revision'])
    rig.call('undo')
    rig.call('undo')
    assert rig.p.config.keys.press == pytest.approx(original.press)
    assert len(rig.call('history')['changes']) == 4


def test_pause_releases_keys_and_resume(rig):
    rig.run(20, 25, 90)
    assert rig.p.held == {'d'}
    rig.call('disable')
    assert rig.p.held == frozenset() and rig.call('status')['mode'] == 'disabled'
    rig.call('enable')
    rig.run(20, 25, 90)
    assert rig.p.held == {'d'}


def test_lost_can_is_reported(rig):
    rig.run(10, 0, 0)
    rig.run(15, present=False)  # ~0.5 s > hold_ms
    rig.run(10, 0, 0)
    tel = rig.call('telemetry', window_s=60)
    assert tel['tracking_lost'] == 1 and tel['tracking_restored'] == 1
    assert tel['unavailable_frames'] > 0


def test_recalibrate_reports_calibrating_then_complete(rig):
    r = rig.call('recalibrate')
    assert r['mode'] == 'calibrating' and r['duration_ms'] == 1000
    rig.run(40)
    assert rig.call('status')['calibrated']
    assert rig.call('telemetry', window_s=60)['last_calibration']['event'] == 'calibration_complete'


def test_agents_reach_it_over_websocket(rig):
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
    server = serve_control(rig.svc, port=port)
    try:
        link = DeskLink(f'ws://127.0.0.1:{port}/ws/control')
        status = asyncio.run(link.call('status'))
        assert status['source'] == 'camera can joystick'
        with pytest.raises(DeskError, match='unknown op'):
            asyncio.run(link.call('explode'))
    finally:
        server.shutdown()


def test_full_coach_conversation_drives_the_camera_joystick(rig, monkeypatch):
    """Coach + Setup + Tuner + Doctor against the real joystick pipeline, not the simulated player."""
    from tests.agents.test_coach_conversation import ROLES, Ctx, last
    from agents import coach as coach_mod
    from agents.coach import Coach
    from agents.shared_desk import set_desk

    class LocalDesk:
        async def call(self, op, **params):
            return rig.call(op, **params)

    monkeypatch.delenv('ASI_ONE_API_KEY', raising=False)
    monkeypatch.setattr(coach_mod, 'SPECIALIST_TIMEOUT_S', 1)
    set_desk(LocalDesk())
    try:
        coach = Coach(None, ROLES)
        ctx = Ctx(coach)

        def say(text):
            asyncio.run(coach.handle_text(ctx, 'user1', text))
            return last(ctx)

        text, card = say('set up DESK for subway surfers')
        assert 'Subway Surfers' in text and card[0] is not None
        say('{"action": "desk_apply_profile", "profile": "subway-surfers"}')
        assert rig.p.config.keys.up == 'up'
        rig.run(40)  # stand the can upright: the Setup agent started a recalibration
        rig.run(20, 25, 270)
        assert rig.p.held == {'left'}
        text, _ = say('what is wrong?')
        assert ctx.delegated[-1] == 'doctor'
        text, _ = say('show my settings')
        assert '↑' in text or 'settings' in text.lower()
    finally:
        set_desk(None)
