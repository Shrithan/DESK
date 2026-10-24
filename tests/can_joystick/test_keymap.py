import math

import pytest

from tilt_joystick.config import KeyConfig
from tilt_joystick.keymap import SectorKeyMapper


def at(mag, deg):
    a = math.radians(deg)
    return mag * math.sin(a), mag * math.cos(a)


@pytest.fixture
def m():
    return SectorKeyMapper(KeyConfig())


def test_deadzone_and_press_threshold(m):
    assert m.update(*at(.30, 0)) == frozenset()
    assert m.update(*at(.34, 0)) == frozenset()
    assert m.update(*at(.36, 0)) == {'w'}


def test_magnitude_hysteresis(m):
    m.update(*at(.4, 0))
    assert m.update(*at(.30, 0)) == {'w'}  # between release and press: still held
    assert m.update(*at(.26, 0)) == {'w'}
    assert m.update(*at(.24, 0)) == frozenset()
    assert m.update(*at(.30, 0)) == frozenset()  # must exceed press again


@pytest.mark.parametrize('deg,keys', [(0, {'w'}), (45, {'w', 'd'}), (90, {'d'}), (135, {'s', 'd'}), (180, {'s'}),
                                      (225, {'s', 'a'}), (270, {'a'}), (315, {'w', 'a'})])
def test_eight_sectors(m, deg, keys):
    assert m.update(*at(.8, deg)) == keys


def test_sector_boundary_fresh_press(m):
    assert m.update(*at(.8, 22.4)) == {'w'}
    m.reset()
    assert m.update(*at(.8, 22.6)) == {'w', 'd'}


def test_sector_hysteresis_no_flicker_at_boundary(m):
    m.update(*at(.8, 10))
    for deg in (20, 25, 30, 32, 24, 31, 22.6):  # wobbling around the 22.5 deg edge
        assert m.update(*at(.8, deg)) == {'w'}
    assert m.update(*at(.8, 33)) == {'w', 'd'}  # past 22.5 + 10
    assert m.update(*at(.8, 15)) == {'w', 'd'}  # back inside WD's widened range
    assert m.update(*at(.8, 12)) == {'w'}


def test_wraparound_near_up(m):
    m.update(*at(.8, 355))
    assert m.update(*at(.8, 5)) == {'w'}
    assert m.update(*at(.8, 340)) == {'w'}  # 20 deg away < 32.5


def test_invalid_releases(m):
    m.update(*at(.8, 0))
    assert m.update(*at(.8, 0), valid=False) == frozenset()
    assert m.update(float('nan'), 0.0) == frozenset()


def test_four_way():
    m = SectorKeyMapper(KeyConfig(diagonals=False))
    assert m.update(*at(.8, 40)) == {'w'}
    assert m.update(*at(.8, 50)) == {'w'}  # hysteresis: 45 + 10
    assert m.update(*at(.8, 56)) == {'d'}


def test_bad_thresholds():
    with pytest.raises(ValueError):
        SectorKeyMapper(KeyConfig(press=.2, release=.3))
