"""CanDetector lock-on, async model hand-off and ROI flow, without ultralytics (model stubbed)."""
import math
import time

import cv2
import numpy as np

from tilt_joystick.config import DetectorConfig
from tilt_joystick.detector import CanDetector, Detection, flow_polygon, polygon_features
from tilt_joystick.features import mask_features


def circle(cx, cy=120, r=30):
    return cv2.ellipse2Poly((int(cx), int(cy)), (r, r), 0, 0, 360, 8).astype(np.float32)


def det(cx, tid, score=.8, r=30):
    return Detection(circle(cx, r=r), score, tid)


def stub(detections_per_call, **cfg):
    d = CanDetector(DetectorConfig(**cfg), load_model=False)
    calls = iter(detections_per_call)
    d._model_detections = lambda frame: next(calls)
    return d


TEX = np.random.default_rng(0).integers(0, 255, (160, 160), dtype=np.uint8)
TEX = cv2.GaussianBlur(TEX, (0, 0), 1.2)


def scene(cx, cy=120, tilt_px=0.0, shape=(240, 320)):
    """Textured can top (disc) whose centre moves; tilt_px stretches it along +x."""
    img = np.full(shape + (3,), 40, np.uint8)
    m = np.zeros(shape, np.uint8)
    cv2.ellipse(m, (int(cx), int(cy)), (int(30 + tilt_px), 30), 0, 0, 360, 255, -1)
    sx = (60 + 2 * tilt_px) / 60
    M = np.float32([[sx, 0, cx - 60 * sx], [0, 1, cy - 60]])
    tex = cv2.warpAffine(TEX[:120, :120], M, shape[::-1])
    img[m > 0] = np.stack([tex] * 3, -1)[m > 0]
    return img, m


def test_polygon_moments_match_raster():
    _, m = scene(150, tilt_px=8)
    poly = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[0][0].reshape(-1, 2).astype(np.float32)
    a, b = polygon_features(poly), mask_features(m)
    assert abs(a.cx - b.cx) < .6 and abs(a.cy - b.cy) < .6
    assert abs(a.area / b.area - 1) < .05 and abs(a.cxx / b.cxx - 1) < .08


def test_flow_follows_shift_and_stretch():
    f0, m0 = scene(140)
    poly = cv2.findContours(m0, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[0][0].reshape(-1, 2).astype(np.float32)
    f1, m1 = scene(150, tilt_px=6)
    out = flow_polygon(cv2.cvtColor(f0, cv2.COLOR_BGR2GRAY), cv2.cvtColor(f1, cv2.COLOR_BGR2GRAY), poly)
    got, want = polygon_features(out), mask_features(m1)
    assert abs(got.cx - want.cx) < 1.5
    assert got.cxx > polygon_features(poly).cxx * 1.15  # the stretch is followed, not only the shift


def test_flow_is_cheap():
    f0, m0 = scene(140)
    g0 = cv2.cvtColor(cv2.resize(f0, (640, 480)), cv2.COLOR_BGR2GRAY)
    g1 = np.roll(g0, 4, 1)
    poly = circle(280, 240, 60)
    flow_polygon(g0, g1, poly)
    t = time.perf_counter()
    for _ in range(50):
        flow_polygon(g0, g1, poly)
    assert (time.perf_counter() - t) / 50 < 0.006


def test_locks_on_biggest_can_then_keeps_its_id():
    d = stub([[det(80, 1, r=20), det(220, 2, r=35)], [det(80, 1, r=20), det(222, 2, r=35)]], async_model=False,
             detect_every=1)
    a, _ = d.track(scene(100)[0])
    assert a.track_id == 2 and d.locked_id == 2
    b, _ = d.track(scene(100)[0])
    assert b.track_id == 2


def test_id_switch_rebinds_to_nearest_but_ignores_far_can():
    d = stub([[det(220, 2)], [det(80, 9), det(226, 7)], [det(80, 9)]], async_model=False)
    blank = np.zeros((240, 320, 3), np.uint8)
    d.track(blank)
    b, _ = d.track(blank)
    assert b.track_id == 7 and d.locked_id == 7
    c, f = d.track(blank)
    assert c is None and f is None  # the other can is not adopted


def test_sync_flow_between_model_runs():
    d = stub([[det(140, 1)]], async_model=False, detect_every=3)
    d.track(scene(140)[0])
    moved, f = d.track(scene(150)[0])
    assert moved.kind == 'flow' and abs(f.cx - 150) < 1.5


def test_async_model_result_is_flowed_to_the_current_frame():
    slow = []
    d = CanDetector(DetectorConfig(async_model=True), load_model=False)
    def model(frame):
        time.sleep(.05)  # a 50 ms model
        slow.append(1)
        return [det(140, 1)]
    d._model_detections = model
    first, _ = d.track(scene(140)[0])
    assert first is None  # nothing known yet; the model is working in the background
    time.sleep(.08)
    t = time.perf_counter()
    got, f = d.track(scene(146)[0])  # can moved 6 px while the model ran on the old frame
    assert time.perf_counter() - t < .03  # the frame was not blocked by the model
    assert got is not None and abs(f.cx - 146) < 1.5
    later, f2 = d.track(scene(152)[0])  # next frame: carried by flow while the model runs again
    assert later is not None and abs(f2.cx - 152) < 1.5
    d.close()
