"""One Euro filter (Casiez, Roussel, Vogel, CHI 2012).

Low cutoff when the signal is slow (kills jitter), higher cutoff when it moves
fast (keeps lag low). min_cutoff trades jitter vs. lag at rest; beta controls
how quickly the cutoff opens up with speed.
"""

from __future__ import annotations

import math


def smoothing_alpha(cutoff_hz: float, dt_s: float) -> float:
    tau = 1.0 / (2.0 * math.pi * cutoff_hz)
    return 1.0 / (1.0 + tau / dt_s)


class OneEuroFilter:
    def __init__(self, min_cutoff_hz: float, beta: float, d_cutoff_hz: float) -> None:
        self.min_cutoff_hz = min_cutoff_hz
        self.beta = beta
        self.d_cutoff_hz = d_cutoff_hz
        self.reset()

    def reset(self) -> None:
        self._x: float | None = None
        self._dx = 0.0
        self._t_ms: int | None = None

    def __call__(self, x: float, t_ms: int) -> float:
        if self._x is None or self._t_ms is None:
            self._x, self._t_ms = x, t_ms
            return x
        dt_s = (t_ms - self._t_ms) / 1000.0
        if dt_s <= 0:
            return self._x
        dx = (x - self._x) / dt_s
        self._dx += smoothing_alpha(self.d_cutoff_hz, dt_s) * (dx - self._dx)
        cutoff = self.min_cutoff_hz + self.beta * abs(self._dx)
        self._x += smoothing_alpha(cutoff, dt_s) * (x - self._x)
        self._t_ms = t_ms
        return self._x
