"""Unit tests for each pipeline stage in isolation."""

import math

import pytest

from backend.tilt_keys.calibration import CalibrationSample, apply_offset, compute_neutral_offset
from backend.tilt_keys.config import KeyBindings, TiltKeyConfig
from backend.tilt_keys.hysteresis import desired_keys, hysteresis_step
from backend.tilt_keys.one_euro import OneEuroFilter
from backend.tilt_keys.output import EdgeTriggeredOutput, key_edges

CAL = dict(min_samples=10, min_valid_fraction=0.8, max_std_deg=1.5, max_range_deg=5.0)


# ------------------------------------------------------------- calibration
def samples(values, start=0):
    return [CalibrationSample(start + i * 33, f, r) for i, (f, r) in enumerate(values)]


def test_calibration_averages_still_can():
    res = compute_neutral_offset(samples([(2.0 + 0.1 * (i % 3), -1.0) for i in range(60)]), **CAL)
    assert res.ok
    assert res.forward_offset_deg == pytest.approx(2.1, abs=1e-9)
    assert res.right_offset_deg == pytest.approx(-1.0)


def test_calibration_rejects_moving_can():
    res = compute_neutral_offset(samples([(i * 0.5, 0.0) for i in range(60)]), **CAL)
    assert not res.ok
    assert "moving" in res.reason


def test_calibration_rejects_single_bump_via_range():
    vals = [(0.0, 0.0)] * 59 + [(8.0, 0.0)]
    res = compute_neutral_offset(samples(vals), **CAL)
    assert not res.ok and "range" in res.reason


def test_calibration_rejects_when_can_mostly_missing():
    vals = [(0.0, 0.0)] * 20 + [(None, None)] * 40
    res = compute_neutral_offset(samples(vals), **CAL)
    assert not res.ok and "missing" in res.reason


def test_calibration_rejects_too_few_samples():
    res = compute_neutral_offset(samples([(0.0, 0.0)] * 3), **CAL)
    assert not res.ok and "usable readings" in res.reason


def test_apply_offset():
    assert apply_offset(20.0, 3.0) == 17.0
    assert apply_offset(None, 3.0) is None


# ------------------------------------------------------------- one euro
def test_one_euro_first_sample_passthrough_and_converges():
    f = OneEuroFilter(min_cutoff_hz=1.0, beta=0.05, d_cutoff_hz=1.0)
    assert f(0.0, 0) == 0.0
    out = [f(20.0, 33 * i) for i in range(1, 60)]
    assert out[0] < 20.0  # smoothed, not instant
    assert out[-1] == pytest.approx(20.0, abs=0.1)
    assert all(a <= b + 1e-9 for a, b in zip(out, out[1:]))  # monotone step response


def test_one_euro_reduces_jitter():
    f = OneEuroFilter(min_cutoff_hz=1.0, beta=0.05, d_cutoff_hz=1.0)
    raw = [5.0 + (1.0 if i % 2 else -1.0) for i in range(120)]
    out = [f(x, 33 * i) for i, x in enumerate(raw)]
    tail = out[60:]
    assert max(tail) - min(tail) < 0.5  # raw peak-to-peak is 2.0


def test_one_euro_beta_reduces_lag():
    slow = OneEuroFilter(1.0, 0.0, 1.0)
    fast = OneEuroFilter(1.0, 0.5, 1.0)
    slow(0.0, 0), fast(0.0, 0)
    assert fast(20.0, 33) > slow(20.0, 33)


def test_one_euro_ignores_non_increasing_time():
    f = OneEuroFilter(1.0, 0.05, 1.0)
    f(1.0, 100)
    assert f(50.0, 100) == 1.0
    assert not math.isnan(f(2.0, 133))


def test_one_euro_reset():
    f = OneEuroFilter(1.0, 0.05, 1.0)
    f(0.0, 0), f(10.0, 33)
    f.reset()
    assert f(7.0, 66) == 7.0


# ------------------------------------------------------------- hysteresis
@pytest.mark.parametrize(
    "held,value,expected",
    [
        (False, 14.9, False),
        (False, 15.0, False),  # strictly greater than ON
        (False, 15.1, True),
        (True, 12.0, True),
        (True, 10.0, True),  # release only strictly below OFF
        (True, 9.9, False),
        (True, None, False),
        (False, None, False),
    ],
)
def test_hysteresis_step(held, value, expected):
    assert hysteresis_step(held, value, 15.0, 10.0) is expected


def test_desired_keys_directions_and_diagonal():
    cfg = TiltKeyConfig()
    none = frozenset()
    assert desired_keys(20, 0, none, cfg) == {"w"}
    assert desired_keys(-20, 0, none, cfg) == {"s"}
    assert desired_keys(0, 20, none, cfg) == {"d"}
    assert desired_keys(0, -20, none, cfg) == {"a"}
    assert desired_keys(20, -20, none, cfg) == {"w", "a"}
    assert desired_keys(-20, 20, none, cfg) == {"s", "d"}
    assert desired_keys(None, -20, frozenset({"w"}), cfg) == {"a"}


def test_desired_keys_uses_bindings():
    cfg = TiltKeyConfig(keys=KeyBindings(forward="up", back="down", left="left", right="right"))
    assert desired_keys(20, 20, frozenset(), cfg) == {"up", "right"}


# ------------------------------------------------------------- config
def test_config_rejects_off_above_on():
    with pytest.raises(ValueError):
        TiltKeyConfig(on_threshold_deg=10, off_threshold_deg=15)


def test_config_rejects_duplicate_bindings():
    with pytest.raises(ValueError):
        TiltKeyConfig(keys=KeyBindings(forward="w", back="w"))


def test_config_from_dict_and_unknown_key(tmp_path):
    cfg = TiltKeyConfig.from_dict({"on_threshold_deg": 20, "off_threshold_deg": 12, "keys": {"forward": "i"}})
    assert cfg.keys.forward == "i" and cfg.keys.back == "s"
    with pytest.raises(ValueError, match="unknown"):
        TiltKeyConfig.from_dict({"on_threshhold": 1})
    path = tmp_path / "c.toml"
    path.write_text('stale_timeout_ms = 300\n[keys]\nleft = "j"\n')
    assert TiltKeyConfig.from_file(path).keys.left == "j"


def test_shipped_example_config_loads():
    from pathlib import Path

    example = Path(__file__).resolve().parents[2] / "backend" / "tilt_keys" / "tilt_keys.example.toml"
    assert TiltKeyConfig.from_file(example) == TiltKeyConfig()


# ------------------------------------------------------------- edges
def test_key_edges():
    assert key_edges(frozenset("wa"), frozenset("wd")) == (["d"], ["a"])
    assert key_edges(frozenset("w"), frozenset("w")) == ([], [])


def test_edge_output_never_repeats_key_down():
    from tests.tilt_keys.conftest import RecordingBackend

    be = RecordingBackend()
    out = EdgeTriggeredOutput(be)
    for _ in range(5):
        out.set_held(frozenset({"w"}))
    out.set_held(frozenset({"w", "a"}))
    out.set_held(frozenset({"w", "a"}))
    out.release_all()
    assert be.events == [("down", "w"), ("down", "a"), ("up", "a"), ("up", "w")]


def test_edge_output_survives_backend_errors():
    class Flaky:
        def __init__(self):
            self.ups = []

        def key_down(self, key):
            if key == "a":
                raise RuntimeError("boom")

        def key_up(self, key):
            self.ups.append(key)
            raise RuntimeError("boom")

        def close(self):
            pass

    be = Flaky()
    out = EdgeTriggeredOutput(be)
    out.set_held(frozenset({"w", "a"}))
    assert out.held == {"w"}  # failed press not marked held
    out.release_all()
    assert out.held == frozenset() and be.ups == ["w"]
