"""Mask -> shape statistics the tilt estimator needs. Also what record/replay stores."""
from __future__ import annotations

from dataclasses import asdict, dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class MaskFeatures:
    cx: float  # centroid, pixels
    cy: float
    area: float  # pixels
    cxx: float  # central second moments / area (pixels^2)
    cxy: float
    cyy: float
    confidence: float = 1.0

    @property
    def radius(self) -> float:
        return float(np.sqrt(self.area / np.pi))

    def cov(self) -> np.ndarray:
        return np.array([[self.cxx, self.cxy], [self.cxy, self.cyy]])

    def to_dict(self) -> dict:
        return {k: round(v, 3) for k, v in asdict(self).items()}


def mask_features(mask: np.ndarray, confidence: float = 1.0) -> MaskFeatures | None:
    m = cv2.moments(mask, binaryImage=True)
    if m['m00'] < 30:
        return None
    a = m['m00']
    return MaskFeatures(cx=m['m10'] / a, cy=m['m01'] / a, area=a,
                        cxx=m['mu20'] / a, cxy=m['mu11'] / a, cyy=m['mu02'] / a, confidence=float(confidence))
