"""Synthetic overhead view of a can: base disc + top disc swung out by the tilt."""
import math

import cv2
import numpy as np

from tilt_joystick.features import mask_features


def can_mask(tilt_deg=0.0, toward_deg=0.0, r=40, h=120, centre=(320, 240), shape=(480, 640), rotate_deg=0.0, mirror=False):
    """toward_deg: clockwise from image-up. rotate_deg/mirror simulate a differently mounted camera."""
    a = math.radians(toward_deg + rotate_deg)
    if mirror:
        a = -a
    s = h * math.sin(math.radians(tilt_deg))
    top = (centre[0] + s * math.sin(a), centre[1] - s * math.cos(a))
    m = np.zeros(shape, np.uint8)
    cv2.circle(m, (int(round(centre[0])), int(round(centre[1]))), r, 255, -1)
    cv2.circle(m, (int(round(top[0])), int(round(top[1]))), r, 255, -1)
    hull = cv2.convexHull(cv2.findNonZero(m))
    cv2.fillConvexPoly(m, hull, 255)
    return m


def feats(**kw):
    return mask_features(can_mask(**kw))
