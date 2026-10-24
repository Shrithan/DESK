"""Per-key hysteresis and the angle -> desired-key-set mapping."""

from __future__ import annotations

from backend.tilt_keys.config import TiltKeyConfig


def hysteresis_step(held: bool, value: float | None, on_threshold: float, off_threshold: float) -> bool:
    """Press above ``on_threshold``; release only below ``off_threshold``.

    ``value`` is the signed angle in the key's own direction (e.g. -forward for
    S). None (unavailable) always releases.
    """
    if value is None:
        return False
    if held:
        return value >= off_threshold
    return value > on_threshold


def desired_keys(
    forward: float | None,
    right: float | None,
    held: frozenset[str],
    config: TiltKeyConfig,
) -> frozenset[str]:
    """Evaluate the four keys independently so diagonals hold two keys."""
    k = config.keys
    fwd_on, fwd_off = config.thresholds("forward")
    lr_on, lr_off = config.thresholds("right")
    directional = (
        (k.forward, forward, fwd_on, fwd_off),
        (k.back, None if forward is None else -forward, fwd_on, fwd_off),
        (k.right, right, lr_on, lr_off),
        (k.left, None if right is None else -right, lr_on, lr_off),
    )
    return frozenset(
        key
        for key, value, on, off in directional
        if hysteresis_step(key in held, value, on, off)
    )
