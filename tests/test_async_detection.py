"""The segmentation model must not stall per-frame tracking, and stale masks must not drag boxes back."""
import time

import numpy as np

from test_fast_motion import jpeg, scene
from vision.live import LiveSession


class SlowModel:
    """Stand-in for a heavy segmentation model: 300 ms per call, sees the frame it was given."""
    def __init__(self):
        self.calls = 0
    def detect(self, frame):
        self.calls += 1
        time.sleep(.3)
        gray = frame.max(axis=2)
        xs = np.nonzero((gray > 120).any(axis=0))[0]
        if not len(xs):
            return []
        x = int(xs.min())
        _, mask, box = scene(x)
        return [dict(label='can', score=.9, bbox=box, mask=mask, center=[x + 40, 160], contour=[])]


def test_tracking_frames_never_wait_for_the_model_and_boxes_stay_on_target():
    s = LiveSession(engine=SlowModel(), async_detection=True)
    for _ in range(40):  # acquire while stationary
        s.receive(jpeg(scene(40)[0]))
        time.sleep(.03)
        if s.objects:
            break
    assert s.objects, 'object never acquired'
    oid = next(iter(s.objects))
    latencies, errors = [], []
    x = 40
    for _ in range(60):  # ~2 s of steady motion at ~200 px/s
        x += 6
        t0 = time.perf_counter()
        r = s.receive(jpeg(scene(x)[0]))
        latencies.append(time.perf_counter() - t0)
        obs = r['objects'][0]['observation']
        if obs['bbox_xyxy']:
            errors.append(abs(obs['bbox_xyxy'][0] - x))
        time.sleep(.025)
    assert s.engine.calls >= 3, 'background detection never ran'
    assert np.percentile(latencies, 95) < .1, f'frames waited for the model: p95 {np.percentile(latencies, 95):.3f} s'
    assert list(s.objects) == [oid]
    assert np.median(errors[-20:]) < 15, f'box lags the object by {np.median(errors[-20:]):.0f} px'
