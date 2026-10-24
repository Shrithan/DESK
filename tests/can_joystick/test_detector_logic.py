"""Lock-on and optical-flow logic of CanDetector without ultralytics (model replaced by a stub)."""
import numpy as np
import cv2

from tilt_joystick.config import DetectorConfig
from tilt_joystick.detector import CanDetector, Detection


def det(cx, tid, score=.8, r=30, shape=(240, 320)):
    m = np.zeros(shape, np.uint8)
    cv2.circle(m, (cx, 120), r, 255, -1)
    return Detection(m, score, tid, (cx - r, 120 - r, cx + r, 120 + r))


def stub(detections_per_call, detect_every=1):
    d = object.__new__(CanDetector)
    d.cfg = DetectorConfig(detect_every=detect_every)
    d.model_ms, d.frame_i = 0.0, 0
    d.reset_lock()
    calls = iter(detections_per_call)
    d._model_detections = lambda frame: next(calls)
    return d


def textured(cx):
    rng = np.random.default_rng(0)
    img = np.zeros((240, 320, 3), np.uint8)
    patch = rng.integers(0, 255, (60, 60, 3), dtype=np.uint8)
    img[90:150, cx - 30:cx + 30] = patch
    return img


def test_locks_on_biggest_can_then_keeps_its_id():
    d = stub([[det(80, 1, r=20), det(220, 2, r=35)], [det(80, 1, r=20), det(222, 2, r=35)]])
    a, _ = d.track(textured(100))
    assert a.track_id == 2 and d.locked_id == 2
    b, _ = d.track(textured(100))
    assert b.track_id == 2


def test_id_switch_rebinds_to_nearest_but_ignores_far_can():
    d = stub([[det(220, 2)], [det(80, 9), det(226, 7)], [det(80, 9)]])
    d.track(textured(100))
    b, _ = d.track(textured(100))
    assert b.track_id == 7 and d.locked_id == 7
    c, f = d.track(textured(100))
    assert c is None and f is None  # the other can is not adopted


def test_flow_carries_mask_between_model_runs():
    d = stub([[det(100, 1)]], detect_every=3)
    d.track(textured(100))
    moved, f = d.track(textured(110))
    assert moved.kind == 'flow' and abs(f.cx - 110) < 2
