import json

import numpy as np

from tests.can_joystick.synth import can_mask, feats
from tilt_joystick.__main__ import main
from tilt_joystick.config import Config, load_config
from tilt_joystick.detector import Detection
from tilt_joystick.estimator import TiltEstimator
from tilt_joystick.overlay import Overlay


def test_shipped_config_loads_and_matches_defaults():
    assert load_config('tilt_joystick/tilt_joystick.toml') == Config()


def test_overlay_draws(tmp_path):
    cfg = Config()
    est = TiltEstimator(cfg.tilt, cfg.filter)
    for i in range(40):
        state = est.update(feats(), i * 33.3)
    state = est.update(feats(tilt_deg=20), 40 * 33.3)
    m = can_mask(tilt_deg=20)
    img = Overlay(cfg.keys).draw(np.zeros((480, 640, 3), np.uint8), Detection(m, .9, 1, (0, 0, 1, 1)), est, state,
                                 frozenset({'w'}), False, {'fps': 30})
    assert img.shape[0] == 480 and img.shape[1] > 640


def test_cli_replay_dry_run(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rows = [{'t_ms': i * 33.3, 'f': feats(tilt_deg=25 if 40 <= i < 80 else 0, toward_deg=270).to_dict()} for i in range(120)]
    (tmp_path / 'r.jsonl').write_text('\n'.join(map(json.dumps, rows)))
    assert main(['--replay', 'r.jsonl', '--config', 'missing.toml', '--events-log', 'ev.jsonl']) == 0
    out = capsys.readouterr().out
    assert 'KEY DOWN a' in out and 'KEY UP   a' in out
    events = [json.loads(l)['event'] for l in (tmp_path / 'ev.jsonl').read_text().splitlines()]
    assert events.count('key_down') == 1 and events.count('key_up') == 1 and 'joystick' in events
