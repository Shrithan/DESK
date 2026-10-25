import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from shared.contracts.export_schemas import SCHEMA_DIR, render_schemas
from shared.contracts.tilt import (
    TILT_SCHEMA_VERSION,
    KeyState,
    TiltCommand,
    TiltUpdate,
    parse_tilt_message,
)

FIXTURES = Path(__file__).resolve().parents[2] / "shared" / "contracts" / "fixtures" / "tilt"
VALID = sorted(p for p in FIXTURES.glob("*.json") if not p.name.startswith("invalid_"))
INVALID = sorted(FIXTURES.glob("invalid_*.json"))


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def test_fixture_sets_are_not_empty():
    assert len(VALID) >= 5
    assert len(INVALID) >= 3


@pytest.mark.parametrize("path", VALID, ids=lambda p: p.name)
def test_valid_fixtures_parse_and_round_trip(path):
    data = load(path)
    msg = parse_tilt_message(data)
    again = parse_tilt_message(json.loads(msg.model_dump_json()))
    assert again == msg


@pytest.mark.parametrize("path", INVALID, ids=lambda p: p.name)
def test_invalid_fixtures_are_rejected(path):
    with pytest.raises((ValidationError, ValueError)):
        parse_tilt_message(load(path))


def test_missing_schema_version_defaults_to_current():
    msg = parse_tilt_message(load(FIXTURES / "tilt_update_back_right_no_version.json"))
    assert msg.schema_version == TILT_SCHEMA_VERSION


def test_can_lost_makes_both_axes_unusable_even_if_angles_present():
    msg = TiltUpdate(timestamp_ms=1, forward_deg=30.0, right_deg=-30.0, can_found=False)
    assert msg.usable_forward() is None
    assert msg.usable_right() is None


def test_null_angle_is_unusable_only_on_that_axis():
    msg = parse_tilt_message(load(FIXTURES / "tilt_update_right_unavailable.json"))
    assert msg.usable_forward() == 16.0
    assert msg.usable_right() is None


def test_nan_and_inf_are_rejected():
    for bad in (float("nan"), float("inf")):
        with pytest.raises(ValidationError):
            TiltUpdate(timestamp_ms=1, forward_deg=bad, right_deg=0.0, can_found=True)


def test_unknown_type_rejected():
    with pytest.raises(ValueError, match="unknown tilt message type"):
        parse_tilt_message({"type": "world_state", "timestamp_ms": 1})


def test_extra_fields_ignored_for_forward_compat():
    msg = parse_tilt_message(
        {"type": "tilt_update", "timestamp_ms": 1, "forward_deg": 1.0, "right_deg": 2.0, "can_found": True, "confidence": 0.9}
    )
    assert isinstance(msg, TiltUpdate)


def test_parse_dispatches_by_type():
    assert isinstance(parse_tilt_message(load(FIXTURES / "tilt_command_recalibrate.json")), TiltCommand)
    assert isinstance(parse_tilt_message(load(FIXTURES / "key_state_forward_left.json")), KeyState)


def test_committed_json_schemas_match_models():
    for filename, text in render_schemas().items():
        committed = SCHEMA_DIR / filename
        assert committed.exists(), f"run: python -m shared.contracts.export_schemas ({filename} missing)"
        assert committed.read_text() == text, f"{filename} is stale; run: python -m shared.contracts.export_schemas"
