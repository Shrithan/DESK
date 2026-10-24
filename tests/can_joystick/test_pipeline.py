import json
import time

import pytest

from tests.can_joystick.synth import feats
from tilt_joystick.config import Config
from tilt_joystick.estimator import Direction
from tilt_joystick.pipeline import TiltPipeline, replay

DT = 33.3


class Recorder:
    def __init__(self):
        self.events, self.closed = [], False

    def key_down(self, k):
        self.events.append(('down', k))

    def key_up(self, k):
        self.events.append(('up', k))

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def no_direction_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def calibrated(direction=None, calibrate_direction=False, **kw):
    rec = Recorder()
    p = TiltPipeline(Config(), rec, direction=direction or Direction(), calibrate_direction=calibrate_direction)
    t = 0.0
    for _ in range(40):  # 1.3 s upright
        p.step(feats(**kw), t)
        t += DT
    assert p.estimator.phase in ('running', 'direction')
    return p, rec, t


def run(p, t, n, **kw):
    for _ in range(n):
        p.step(feats(**kw) if kw.get('present', True) else None, t)
        t += DT
    return t


def tilt(p, t, n, deg, toward):
    for _ in range(n):
        p.step(feats(tilt_deg=deg, toward_deg=toward), t)
        t += DT
    return t


def test_upright_presses_nothing():
    p, rec, t = calibrated()
    tilt(p, t, 30, 0, 0)
    assert rec.events == []


@pytest.mark.parametrize('toward,keys', [(0, {'w'}), (90, {'d'}), (180, {'s'}), (270, {'a'}), (45, {'w', 'd'})])
def test_tilt_direction_maps_to_key(toward, keys):
    p, rec, t = calibrated()
    tilt(p, t, 20, 25, toward)
    assert p.held == keys


def test_hold_three_seconds_is_one_press_no_flicker():
    p, rec, t = calibrated()
    t = tilt(p, t, 90, 25, 0)  # 3 s
    assert rec.events == [('down', 'w')]
    tilt(p, t, 30, 0, 0)
    assert rec.events == [('down', 'w'), ('up', 'w')]


def test_direction_change_releases_old_before_new():
    p, rec, t = calibrated()
    t = tilt(p, t, 20, 25, 0)
    tilt(p, t, 20, 25, 180)
    assert rec.events[0] == ('down', 'w')
    assert rec.events.index(('up', 'w')) < rec.events.index(('down', 's'))
    assert p.held == {'s'}


def test_small_tilt_stays_in_deadzone():
    p, rec, t = calibrated()
    tilt(p, t, 30, 3, 0)
    assert rec.events == []


def test_short_dropout_holds_long_dropout_releases():
    p, rec, t = calibrated()
    t = tilt(p, t, 20, 25, 0)
    for _ in range(6):  # 200 ms without the can
        p.step(None, t); t += DT
    assert p.held == {'w'} and p.state.status == 'holding'
    t = tilt(p, t, 5, 25, 0)
    assert rec.events == [('down', 'w')]
    for _ in range(10):  # 330 ms
        p.step(None, t); t += DT
    assert p.held == frozenset() and p.state.status == 'lost'


def test_hand_occlusion_area_drop_is_a_dropout():
    from tilt_joystick.features import MaskFeatures
    p, rec, t = calibrated()
    t = tilt(p, t, 20, 25, 0)
    f = feats(tilt_deg=25)
    small = MaskFeatures(f.cx, f.cy, f.area * .3, f.cxx, f.cxy, f.cyy)
    p.step(small, t)
    assert p.state.status == 'holding' and p.held == {'w'}


def test_single_frame_glitch_does_not_flicker():
    p, rec, t = calibrated()
    t = tilt(p, t, 15, 25, 0)
    p.step(feats(tilt_deg=25, toward_deg=180), t); t += DT  # one wild frame
    tilt(p, t, 10, 25, 0)
    assert rec.events == [('down', 'w')]


def test_pause_and_close_release_everything():
    p, rec, t = calibrated()
    t = tilt(p, t, 20, 25, 90)
    p.set_paused(True)
    assert rec.events == [('down', 'd'), ('up', 'd')]
    t = tilt(p, t, 10, 25, 90)
    assert p.held == frozenset()
    p.set_paused(False)
    tilt(p, t, 10, 25, 90)
    assert p.held == {'d'}
    p.close()
    assert rec.events[-1] == ('up', 'd') and rec.closed


@pytest.mark.parametrize('rotate,mirror', [(90, False), (-130, False), (40, True)])
def test_direction_calibration_fits_rotation_and_mirror(rotate, mirror):
    p, rec, t = calibrated(calibrate_direction=True, rotate_deg=rotate, mirror=mirror)
    def go(n, toward, deg=25):
        nonlocal t
        for _ in range(n):
            p.step(feats(tilt_deg=deg, toward_deg=toward, rotate_deg=rotate, mirror=mirror), t); t += DT
    go(25, 0)   # "tilt toward W"
    assert p.estimator.phase == 'direction_d'
    go(25, 90)  # "tilt toward D"
    assert p.estimator.phase == 'running'
    go(10, 0, 0)
    assert rec.events == []  # nothing pressed during calibration
    go(15, 90)
    assert p.held == {'d'}
    go(10, 0, 0); go(15, 270)
    assert p.held == {'a'}
    go(10, 0, 0); go(15, 0)
    assert p.held == {'w'}


def test_drift_recentering():
    p, rec, t = calibrated()
    t = run(p, t, 120, centre=(326, 240))  # can slid 6 px while upright
    anchor_x = p.estimator.anchor[0]
    assert anchor_x > 322
    assert rec.events == []


def test_replay_is_deterministic(tmp_path):
    rows, t = [], 0.0
    for i in range(160):
        f = feats(tilt_deg=25 if 50 <= i < 110 else 0, toward_deg=90)
        rows.append({'t_ms': t, 'f': f.to_dict()})
        t += DT
    path = tmp_path / 'r.jsonl'
    path.write_text('\n'.join(json.dumps(r) for r in rows))
    outs = []
    for _ in range(2):
        rec = Recorder()
        replay(path, TiltPipeline(Config(), rec, direction=Direction()))
        outs.append(rec.events)
    assert outs[0] == outs[1] == [('down', 'd'), ('up', 'd')]


def test_pipeline_step_is_fast():
    p, rec, t = calibrated()
    f = feats(tilt_deg=20)
    start = time.perf_counter()
    for i in range(500):
        p.step(f, t + i * DT)
    assert (time.perf_counter() - start) / 500 < 0.002
