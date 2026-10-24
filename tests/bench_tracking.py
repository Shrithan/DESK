"""Tracking benchmark: a can-like object moving fast over a textured table, with motion blur.

Measures, per analysed frame: whether the true object is inside the reported box (containment),
centre error, tracking state and processing time. Used before/after tracker changes.
    python tests/bench_tracking.py
"""
import time

import cv2
import numpy as np

from vision.live import LiveSession

W, H, FPS = 640, 360, 15.0
rng = np.random.default_rng(7)
TABLE = np.clip(np.array([60, 95, 140], np.float32) + cv2.GaussianBlur(rng.normal(0, 1, (H, W)).astype(np.float32), (0, 0), 3)[..., None] * 30, 0, 255).astype(np.uint8)
CAN = np.zeros((110, 60, 3), np.uint8)
CAN[:, :] = (200, 160, 60)
CAN[20:55] = (40, 40, 210)
CAN[55:90] = (230, 230, 230)
CAN = np.clip(CAN.astype(int) + rng.integers(-30, 30, CAN.shape), 0, 255).astype(np.uint8)
for i in range(12):
    cv2.putText(CAN, 'Bull'[i % 4], (5 + (i % 3) * 18, 15 + (i // 3) * 26), cv2.FONT_HERSHEY_SIMPLEX, .5, (20, 20, 20), 1)


def path(t):
    """Circle + figure-eight; peak speed ~1500 px/s."""
    w = 2 * np.pi * (.35 + .25 * np.sin(.5 * t))
    return np.array([W / 2 - 30 + 200 * np.sin(w * t), H / 2 - 55 + 90 * np.sin(2 * w * t)])


def render(t, dt):
    p0, p1 = path(t - dt * .5), path(t)
    f = TABLE.copy()
    steps = max(1, int(np.linalg.norm(p1 - p0) / 3))
    acc = np.zeros_like(f, np.float32)
    for k in range(steps):  # motion blur during a ~half-frame exposure
        x, y = (p0 + (p1 - p0) * (k + .5) / steps).astype(int)
        g = TABLE.copy()
        x = int(np.clip(x, 0, W - 60)); y = int(np.clip(y, 0, H - 110))
        g[y:y + 110, x:x + 60] = CAN
        acc += g
    f = (acc / steps).astype(np.uint8)
    x, y = np.clip(p1, [0, 0], [W - 60, H - 110]).astype(int)
    return f, [x, y, x + 60, y + 110]


class Detector:
    """Ideal segmentation (true mask of the current frame), like a good model."""
    def __init__(self):
        self.box = None
    def detect(self, frame):
        x, y, x2, y2 = self.box
        m = np.zeros((H, W), np.uint8)
        m[y:y2, x:x2] = 1
        return [dict(label='can', score=.9, bbox=list(self.box), mask=m, center=[(x + x2) / 2, (y + y2) / 2], contour=[])]


def run(seconds=12.0, detect_every=.3, seed_clock=100.):
    import vision.live as L
    clock = [seed_clock]
    real = L.time.monotonic
    L.time.monotonic = lambda: clock[0]
    try:
        det = Detector()
        s = LiveSession(engine=det)
        s.tuning  # noqa
        s.last_detection = 0
        stats = dict(frames=0, inside=0, tracked=0, err=[], ms=[], lost=0, ids=set())
        last_det = -1e9
        n = int(seconds * FPS)
        for i in range(-6, n):
            t = max(0, i) / FPS
            frame, box = render(t, 1 / FPS) if i >= 0 else render(0, 1 / FPS)
            det.box = box
            clock[0] = seed_clock + (i + 6) / FPS
            # Detection cadence: emulate a slow model by only allowing it every `detect_every` s.
            s.last_detection = clock[0] if clock[0] - last_det < detect_every else 0
            if s.last_detection == 0:
                last_det = clock[0]
            a = time.perf_counter()
            r = s.receive(cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes())
            ms = (time.perf_counter() - a) * 1000
            if i < 0:
                continue
            stats['frames'] += 1
            stats['ms'].append(ms)
            obj = r['objects'][0] if r['objects'] else None
            for o in r['objects']:
                stats['ids'].add(o['observation']['object_id'])
            if not obj or not obj['observation']['bbox_xyxy']:
                stats['lost'] += 1
                continue
            st = obj['observation']['tracking_state']
            stats['tracked'] += st == 'tracked'
            b0 = obj['observation']['bbox_xyxy']  # score the box as drawn (fusion.js displayBox margin)
            pw, ph = max(6, .08 * (b0[2] - b0[0])), max(6, .08 * (b0[3] - b0[1]))
            bx = [b0[0] - pw, b0[1] - ph, b0[2] + pw, b0[3] + ph]
            ix = max(0, min(bx[2], box[2]) - max(bx[0], box[0])) * max(0, min(bx[3], box[3]) - max(bx[1], box[1]))
            contain = ix / ((box[2] - box[0]) * (box[3] - box[1]))
            stats['inside'] += contain >= .9
            spd = np.linalg.norm(path(t) - path(t - 1 / FPS)) * FPS
            bucket = 'slow <500' if spd < 500 else 'fast 500-1000' if spd < 1000 else 'very fast >1000'
            b = stats.setdefault('buckets', {}).setdefault(bucket, [0, 0])
            b[0] += 1; b[1] += contain >= .9
            stats['err'].append(np.hypot((bx[0] + bx[2] - box[0] - box[2]) / 2, (bx[1] + bx[3] - box[1] - box[3]) / 2))
        return stats
    finally:
        L.time.monotonic = real


def report(s):
    f = s['frames']
    e = np.array(s['err']) if s['err'] else np.array([np.inf])
    return (f"can >=90% inside box: {100 * s['inside'] / f:.1f}% | tracked: {100 * s['tracked'] / f:.1f}% | no box: {s['lost']} "
            f"| centre err median {np.median(e):.1f}px p95 {np.percentile(e, 95):.1f}px | ids {len(s['ids'])} "
            f"| frame ms median {np.median(s['ms']):.1f} p95 {np.percentile(s['ms'], 95):.1f}")


if __name__ == '__main__':
    for every in (.3, .12):
        st = run(detect_every=every)
        print(f'model every {every}s: ' + report(st))
        print('   by speed (px/s): ' + ', '.join(f"{k}: {100 * v[1] / v[0]:.0f}% of {v[0]}" for k, v in sorted(st['buckets'].items())))
