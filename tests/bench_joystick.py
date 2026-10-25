"""Joystick latency benchmark: Aadi's web can-joystick logic vs tilt_joystick, same simulated tilts.

Simulates an overhead 640x360 camera at 30 fps (the size the web UI sends), with sub-pixel
silhouette noise. A can tilts to `--deg` in 120 ms in each of 8 directions, holds 1 s, returns.
Measures LOGIC latency (filter + continuity + key thresholds + loop ticks): tilt start -> correct
key(s) down, return start -> all keys up, and extra key transitions (flicker). Camera exposure/USB,
model and transport costs are measured separately (`--costs`).

    python tests/bench_joystick.py
"""
from __future__ import annotations

import argparse
import io
import math
import os
import sys
import tempfile
import time
from dataclasses import replace

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tilt_joystick.config import Config, FilterConfig, load_config  # noqa: E402
from tilt_joystick.estimator import Direction  # noqa: E402
from tilt_joystick.features import mask_features  # noqa: E402
from tilt_joystick.pipeline import TiltPipeline  # noqa: E402

W, H, R, CAN_H = 640, 360, 25, 92  # px: ~66 mm can, 120 mm tall, C270 at ~0.9 m, 640 px wide
FPS = 30.0
DIRS = [0, 45, 90, 135, 180, 225, 270, 315]
KEYS8 = {0: {'w'}, 45: {'w', 'd'}, 90: {'d'}, 135: {'s', 'd'}, 180: {'s'}, 225: {'s', 'a'}, 270: {'a'}, 315: {'w', 'a'}}


NOISE = float(os.environ.get("BENCH_NOISE", .6))


def render(tilt_deg, toward_deg, rng, noise=None):
    """Overhead silhouette, 1/16 px precision, centre/edge noise of ~noise px."""
    noise = NOISE if noise is None else noise
    a = math.radians(toward_deg)
    s = CAN_H * math.sin(math.radians(tilt_deg))
    jx, jy = rng.normal(0, noise, 2)
    base = (W / 2 + jx, H / 2 + jy)
    top = (base[0] + s * math.sin(a), base[1] - s * math.cos(a))
    m = np.zeros((H, W), np.uint8)
    r = R + rng.normal(0, noise / 2)
    for c in (base, top):
        cv2.circle(m, (int(c[0] * 16), int(c[1] * 16)), int(r * 16), 255, -1, cv2.LINE_8, 4)
    cv2.fillConvexPoly(m, cv2.convexHull(cv2.findNonZero(m)), 255)
    return m


def scenario(deg, ramp_ms=120, hold_ms=1000, rest_ms=600):
    """Yields (t_ms, tilt, toward, event) — event marks ramp starts."""
    t, dt = 0.0, 1000 / FPS
    def seg(duration, f, toward, event=None):
        nonlocal t
        start = t
        first = True
        while t < start + duration:
            yield t, f((t - start) / duration), toward, (event if first else None)
            first = False
            t += dt
    yield from seg(1500, lambda u: 0, 0)  # calibration time
    for d in DIRS:
        yield from seg(ramp_ms, lambda u: deg * u, d, ('tilt', d))
        yield from seg(hold_ms, lambda u: deg, d)
        yield from seg(ramp_ms, lambda u: deg * (1 - u), d, ('return', d))
        yield from seg(rest_ms, lambda u: 0, d)


# ----------------------------------------------------------------- Aadi's logic (port of the JS)
def euro_step(state, value, stamp, min_cutoff, beta, d_cutoff=1.0):
    if not state or stamp <= state['stamp'] or stamp - state['stamp'] > 250:
        return {'value': value, 'raw': value, 'derivative': 0.0, 'stamp': stamp}
    dt = (stamp - state['stamp']) / 1000
    alpha = lambda c: 1 / (1 + 1 / (2 * math.pi * c * dt))
    deriv = state['derivative'] + alpha(d_cutoff) * ((value - state['raw']) / dt - state['derivative'])
    filtered = state['value'] + alpha(min_cutoff + beta * abs(deriv)) * (value - state['value'])
    return {'value': filtered, 'raw': value, 'derivative': deriv, 'stamp': stamp}


class AadiWeb:
    """vision/web/flat-input.js + stick.js, top camera path: centroid -> euro(3, 25) -> canStick(gain 30)
    -> stickContinuity -> stickKeys(.18/.12), evaluated on a free-running 33 ms setInterval tick."""
    name = "Aadi web joystick"

    def __init__(self, transport_ms=0.0):
        self.filters, self.origin, self.keys = {}, None, {}
        self.cont = {}
        self.latest = None  # (sample_stamp, value)
        self.transport_ms = transport_ms
        self.next_tick = 0.0

    def frame(self, t_ms, mask):
        m = cv2.moments(mask, binaryImage=True)
        cx, cy = m['m10'] / m['m00'], m['m01'] / m['m00']
        self.latest = (t_ms, t_ms + self.transport_ms, {'x': cx / W, 'y': 1 - cy / H})

    def tick(self, now):
        """Returns held key set (lower-case, our W/A/S/D naming in image space)."""
        target, sample = None, None
        if self.latest and self.latest[1] <= now and now - self.latest[1] < 250:
            stamp, _, v = self.latest
            if self.filters.get('stamp') != stamp:
                for k in ('x', 'y'):
                    self.filters[k] = euro_step(self.filters.get(k), v[k], stamp, 3, 25)
                self.filters['stamp'] = stamp
            v = {k: self.filters[k]['value'] for k in ('x', 'y')}
            if self.origin is None:
                self.origin = (v['x'], v['y'])
            x, y = (v['x'] - self.origin[0]) * 30, (v['y'] - self.origin[1]) * 30
            n = max(1, math.hypot(x, y))
            target, sample = {'x': x / n, 'y': y / n}, stamp  # (mounting remap omitted: same timing)
        if target:
            self.cont['last'], self.cont['seen'] = target, sample
        age = now - self.cont.get('seen', -1e9)
        scale = 1 if age <= 130 else max(0, 1 - (age - 130) / 170)
        stick = None if not self.cont.get('last') or not scale else {k: self.cont['last'][k] * scale for k in 'xy'}
        if stick is None:
            self.keys = {}
            return set()
        p = lambda key, val: val > (.12 if self.keys.get(key) else .18)
        self.keys = {'w': p('w', stick['y']), 'a': p('a', -stick['x']), 's': p('s', -stick['y']), 'd': p('d', stick['x'])}
        return {k for k, on in self.keys.items() if on}


class AadiWebSectors(AadiWeb):
    """Same as AadiWeb but with the new stick.js stickKeys: 8 sectors, .18/.12, 10 deg hysteresis."""

    def __init__(self):
        super().__init__()
        from tilt_joystick.config import KeyConfig
        from tilt_joystick.keymap import SectorKeyMapper
        self.mapper = SectorKeyMapper(KeyConfig(press=.18, release=.12))

    def tick(self, now):
        keys = super().tick(now)  # runs the filter/continuity state; keys recomputed from the stick below
        last, seen = self.cont.get('last'), self.cont.get('seen', -1e9)
        age = now - seen
        scale = 1 if age <= 130 else max(0, 1 - (age - 130) / 170)
        if not last or not scale:
            return set(self.mapper.update(0, 0, False))
        return set(self.mapper.update(last['x'] * scale, last['y'] * scale))


class Recorder:
    def __init__(self):
        self.held = set()
    def key_down(self, k): self.held.add(k)
    def key_up(self, k): self.held.discard(k)
    def close(self): pass


class Ours:
    def __init__(self, cfg: Config, name):
        self.name = name
        self.rec = Recorder()
        self.p = TiltPipeline(cfg, self.rec, direction=Direction())

    def frame(self, t_ms, mask):
        self.p.step(mask_features(mask), t_ms)

    def tick(self, now):
        return set(self.rec.held)


def run(method, deg, seed=1, tick_ms=None, tick_phase=0.0):
    rng = np.random.default_rng(seed)
    events, log = [], []  # log: (t, keys) at every change
    frames = list(scenario(deg))
    keys = set()
    next_tick = tick_phase
    for t, tilt, toward, ev in frames:
        if ev:
            events.append((t, ev))
        method.frame(t, render(tilt, toward, rng))
        if tick_ms is None:  # keys evaluated as soon as the frame is processed
            new = method.tick(t)
            if new != keys:
                log.append((t, new)); keys = new
        else:
            while next_tick < t + 1000 / FPS:
                if next_tick >= t:
                    new = method.tick(next_tick)
                    if new != keys:
                        log.append((next_tick, new)); keys = new
                next_tick += tick_ms
    # metrics
    press, release, extra = [], [], 0
    for (t0, (kind, d)), nxt in zip(events, events[1:] + [(1e12, None)]):
        window = [(t, k) for t, k in log if t0 <= t < nxt[0]]
        if kind == 'tilt':
            want = KEYS8[d]
            hit = next((t for t, k in window if k == want), None)
            press.append(None if hit is None else hit - t0)
            extra += max(0, len(window) - 1)
        else:
            hit = next((t for t, k in window if not k), None)
            release.append(None if hit is None else hit - t0)
            extra += max(0, len(window) - 1)
    return press, release, extra


def summary(name, press, release, extra):
    ok = [p for p in press if p is not None]
    rl = [r for r in release if r is not None]
    miss = sum(p is None for p in press)
    fmt = lambda v: f"{np.mean(v):5.0f} / {np.max(v):4.0f}" if v else "    -"
    print(f"{name:34s} press ms mean/max {fmt(ok)}  release {fmt(rl)}  "
          f"wrong/missed dirs {miss}/8  extra transitions {extra}")


def costs():
    rng = np.random.default_rng(0)
    img = (rng.random((360, 640, 3)) * 255).astype(np.uint8)
    img = cv2.GaussianBlur(img, (0, 0), 3)
    big = cv2.resize(img, (1280, 720))
    def t(f, n=200):
        f(); s = time.perf_counter()
        for _ in range(n): f()
        return (time.perf_counter() - s) / n * 1000
    enc = t(lambda: cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 85]))
    buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 85])[1]
    dec = t(lambda: cv2.imdecode(buf, cv2.IMREAD_COLOR))
    mask = render(15, 30, rng)
    poly = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0][0]
    raster_big = t(lambda: (lambda m: (cv2.fillPoly(m, [poly * 2], 255), cv2.moments(m, True)))(np.zeros((720, 1280), np.uint8)))
    polym = t(lambda: cv2.moments(poly.astype(np.float32)))
    rec = Recorder(); p = TiltPipeline(Config(), rec, direction=Direction()); f = mask_features(mask)
    for i in range(40): p.step(f, i * 33.3)
    step = t(lambda: p.step(f, time.perf_counter() * 1000), 2000)
    g0 = cv2.cvtColor(big, cv2.COLOR_BGR2GRAY); g1 = np.roll(g0, 3, 1)
    m720 = cv2.resize(mask, (1280, 720), interpolation=cv2.INTER_NEAREST)
    def flow():
        pts = cv2.goodFeaturesToTrack(g0, 60, .01, 4, mask=m720)
        cv2.calcOpticalFlowPyrLK(g0, g1, pts, None, winSize=(21, 21), maxLevel=3)
    fl = t(flow, 50)
    print(f"640x360 JPEG encode q85 {enc:.2f} ms, decode {dec:.2f} ms (web path, per frame, plus HTTP + JSON)")
    print(f"mask moments: raster 1280x720 fill+moments {raster_big:.2f} ms vs polygon moments {polym:.3f} ms")
    print(f"tilt pipeline step (estimate+filter+keys) {step:.3f} ms; LK flow on 1280x720 mask {fl:.2f} ms")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--deg', type=float, nargs='*', default=[12, 20])
    ap.add_argument('--config')
    ap.add_argument('--costs', action='store_true')
    a = ap.parse_args()
    os.chdir(tempfile.mkdtemp())
    for deg in a.deg:
        print(f"\n== tilt {deg:.0f} deg, ramp 120 ms, 30 fps, logic latency only ==")
        res = [run(AadiWeb(), deg, s) for s in (1, 2, 3)]
        summary("Aadi web stick (before)", *merge(res))
        res = [run(AadiWebSectors(), deg, s) for s in (1, 2, 3)]
        summary("Aadi web stick + sector keys (now)", *merge(res))
        cfg = load_config(a.config) if a.config else Config()
        res = [run(Ours(cfg, 'ours'), deg, s) for s in (1, 2, 3)]
        summary("tilt_joystick (config)", *merge(res))
        global NOISE
        noise, NOISE = NOISE, 0.0
        ideal = replace(cfg, filter=FilterConfig(min_cutoff_hz=1e4, beta=0), tilt=replace(cfg.tilt, lead_ms=0))
        summary("ideal: same thresholds, no noise/filter", *merge([run(Ours(ideal, 'ideal'), deg, 1)]))
        NOISE = noise
    if a.costs:
        print(); costs()


def merge(res):
    return [x for r in res for x in r[0]], [x for r in res for x in r[1]], sum(r[2] for r in res)



# ----------------------------------------------------------------- full detector path (stub model)
def textured_frame(tilt, toward, rng, tex):
    m = render(tilt, toward, rng, noise=0.3)
    img = np.full((H, W, 3), 60, np.uint8)
    a = math.radians(toward)
    s = CAN_H * math.sin(math.radians(tilt)) / 2
    M = np.float32([[1, 0, s * math.sin(a)], [0, 1, -s * math.cos(a)]])
    t = cv2.warpAffine(tex, M, (W, H), borderMode=cv2.BORDER_REFLECT)
    img[m > 0] = t[m > 0]
    return img, m


def detector_path(async_model, model_ms, deg=15, seed=1):
    """Frame -> CanDetector (stub model that sleeps model_ms and returns the true outline of the frame
    it was given) -> pipeline. Frames arrive every 33 ms in real time. Returns press/release delays vs
    the same pipeline fed perfect per-frame outlines, and mean per-frame compute."""
    from tilt_joystick.config import DetectorConfig
    from tilt_joystick.detector import CanDetector, Detection, polygon_features
    rng = np.random.default_rng(seed)
    tex = cv2.cvtColor(cv2.GaussianBlur((rng.random((H, W, 3)) * 255).astype(np.uint8), (0, 0), 1.5), cv2.COLOR_BGR2BGR555)
    tex = cv2.cvtColor(tex, cv2.COLOR_BGR5552BGR)
    truth = {}

    def model(frame):
        time.sleep(model_ms / 1000)
        m = truth[id(frame)]
        c = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0][0].reshape(-1, 2).astype(np.float32)
        return [Detection(c, .9, 1)]

    d = CanDetector(DetectorConfig(async_model=async_model), load_model=False)
    d._model_detections = model
    ours, ideal = Ours(Config(), 'det'), Ours(Config(), 'ideal')
    frames = list(scenario(deg, rest_ms=500))
    compute, log_o, log_i, events = [], [], [], []
    ko = ki = set()
    keep = []
    t_start = time.perf_counter()
    for i, (t, tilt, toward, ev) in enumerate(frames):
        # real-time pacing: frame i arrives at t
        while (time.perf_counter() - t_start) * 1000 < t:
            time.sleep(0.0005)
        if ev:
            events.append((t, ev))
        img, m = textured_frame(tilt, toward, rng, tex)
        truth[id(img)] = m
        keep.append(img)
        ideal.p.step(mask_features(m), t)
        if (time.perf_counter() - t_start) * 1000 > t + 1000 / FPS:
            continue  # a newer frame already exists: the app's newest-frame grabber drops this one
        c0 = time.perf_counter()
        _, f = d.track(img)
        ours.p.step(f, t)
        now_ms = (time.perf_counter() - t_start) * 1000  # when the keys were actually sent
        compute.append((time.perf_counter() - c0) * 1000)
        if set(ours.rec.held) != ko:
            ko = set(ours.rec.held); log_o.append((now_ms, ko))
        if set(ideal.rec.held) != ki:
            ki = set(ideal.rec.held); log_i.append((t, ki))
        if len(keep) > 40:
            truth.pop(id(keep.pop(0)), None)
    d.close()

    def times(log):
        out = []
        for (t0, (kind, dd)), nxt in zip(events, events[1:] + [(1e12, None)]):
            want = KEYS8[dd] if kind == 'tilt' else set()
            out.append(next((t for t, k in log if t0 <= t < nxt[0] and k == want), None))
        return out
    a, b = times(log_o), times(log_i)
    delay = [x - y for x, y in zip(a, b) if x is not None and y is not None]
    missed = sum(x is None for x in a)
    return delay, missed, compute


def bench_detector():
    print("\n== full detector path, frames in real time at 30 fps, stub model (true outline after model_ms) ==")
    print("   delay = when keys were actually sent, minus when perfect per-frame outlines would send them")
    for async_model, model_ms in ((False, 30), (True, 30), (False, 60), (True, 60)):
        delay, missed, compute = detector_path(async_model, model_ms)
        tag = 'async model + ROI flow (new)' if async_model else 'model in frame->key path (old)'
        print(f"{tag:32s} model {model_ms:2d} ms: key delay mean {np.mean(delay):5.1f} ms, max {np.max(delay):5.1f} ms, "
              f"missed {missed}, per-frame compute mean {np.mean(compute):4.1f} ms p95 {np.percentile(compute, 95):4.1f} ms")


if __name__ == '__main__':
    if '--detector' in sys.argv:
        bench_detector()
    else:
        main()
