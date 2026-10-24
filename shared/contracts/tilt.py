"""Tilt-to-keys wire contract (schema version 1.x).

Sign conventions (viewed from the user's seat, looking at the can):
  forward_deg  + = top of the can leans AWAY from the user
               - = top of the can leans TOWARD the user
  right_deg    + = top of the can leans to the user's RIGHT
               - = top of the can leans to the user's LEFT
Angles are degrees of tilt from the camera-estimated vertical. A null angle or
can_found=false means "measurement unavailable" -- never "0 degrees".

See docs/protocol.md for the full description.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

TILT_SCHEMA_VERSION = "1.0.0"
TILT_SCHEMA_MAJOR = 1

# Physically a can past +-90 deg has fallen over; anything beyond +-180 is garbage.
MAX_ABS_ANGLE_DEG = 180.0


def _check_major(version: str) -> str:
    try:
        major = int(version.split(".", 1)[0])
    except ValueError as exc:
        raise ValueError(f"schema_version must look like 'MAJOR.MINOR.PATCH', got {version!r}") from exc
    if major != TILT_SCHEMA_MAJOR:
        raise ValueError(f"unsupported schema major version {major}; this build speaks {TILT_SCHEMA_MAJOR}.x")
    return version


class _TiltMessage(BaseModel):
    # Unknown extra fields are ignored so producers can add optional fields in
    # minor versions without breaking consumers.
    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)

    schema_version: str = Field(
        default=TILT_SCHEMA_VERSION,
        description="Semantic version of this contract. Optional on the wire; defaults to the current version.",
    )
    timestamp_ms: int = Field(gt=0, description="Unix epoch milliseconds when the measurement was taken.")

    @field_validator("schema_version")
    @classmethod
    def _major_supported(cls, v: str) -> str:
        return _check_major(v)


class TiltUpdate(_TiltMessage):
    """One tilt measurement of the can, produced by the vision agent."""

    type: Literal["tilt_update"] = "tilt_update"
    forward_deg: float | None = Field(
        ge=-MAX_ABS_ANGLE_DEG,
        le=MAX_ABS_ANGLE_DEG,
        description="+ = top leans away from the user, - = toward the user. null = unavailable.",
    )
    right_deg: float | None = Field(
        ge=-MAX_ABS_ANGLE_DEG,
        le=MAX_ABS_ANGLE_DEG,
        description="+ = top leans right, - = leans left. null = unavailable.",
    )
    can_found: bool = Field(description="false means the whole measurement is unavailable; angles are ignored.")

    def usable_forward(self) -> float | None:
        return self.forward_deg if self.can_found else None

    def usable_right(self) -> float | None:
        return self.right_deg if self.can_found else None


class TiltCommand(_TiltMessage):
    """Control message for the tilt-to-keys mapper (from UI, voice, or CLI)."""

    type: Literal["tilt_command"] = "tilt_command"
    command: Literal["recalibrate", "enable", "disable", "toggle"]


class KeyState(_TiltMessage):
    """Broadcast by the websocket key backend whenever the held-key set changes."""

    type: Literal["key_state"] = "key_state"
    held: list[str] = Field(description="Keys currently held down, sorted.")
    enabled: bool = True
    mode: Literal["calibrating", "active", "disabled"] = "active"


TILT_MODELS: dict[str, type[_TiltMessage]] = {
    "tilt_update": TiltUpdate,
    "tilt_command": TiltCommand,
    "key_state": KeyState,
}


def parse_tilt_message(data: dict) -> TiltUpdate | TiltCommand | KeyState:
    """Validate a decoded JSON object into the matching model by its ``type`` field."""
    msg_type = data.get("type")
    model = TILT_MODELS.get(msg_type)  # type: ignore[arg-type]
    if model is None:
        raise ValueError(f"unknown tilt message type {msg_type!r}; expected one of {sorted(TILT_MODELS)}")
    return model.model_validate(data)  # type: ignore[return-value]
