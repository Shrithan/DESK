"""One Euro (agent 3's backend.tilt_keys.one_euro) plus access to its filtered velocity."""
from backend.tilt_keys.one_euro import OneEuroFilter


class OneEuro(OneEuroFilter):
    @property
    def velocity(self) -> float:
        """Filtered derivative, units per second (0 until two samples have arrived)."""
        return self._dx
