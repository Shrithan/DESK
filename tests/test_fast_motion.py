"""Fast moves (boxes no longer overlap between frames) must keep the same object ID."""
import cv2
import numpy as np

from vision.live import LiveSession

RNG = np.random.default_rng(3)
# A can-like label: solid colour bands (what survives motion blur) plus fine print (what flow tracks).
PATCH = np.zeros((80, 80, 3), np.uint8)
PATCH[:, :30] = (40, 40, 200)   # red band (BGR)
PATCH[:, 30:55] = (200, 120, 30)  # blue band
PATCH[:, 55:] = (230, 230, 230)  # white band
PATCH = np.clip(PATCH.astype(int) + RNG.integers(-35, 35, PATCH.shape), 0, 255).astype(np.uint8)


def scene(x, y=120, w=640, h=360, blur=0):
    frame = np.full((h, w, 3), 90, np.uint8)
    frame[y:y + 80, x:x + 80] = PATCH
    if blur:  # horizontal motion blur, as from a fast hand move during the exposure
        k = np.zeros((1, blur), np.float32); k[0] = 1 / blur
        frame = cv2.filter2D(frame, -1, k)
    mask = np.zeros((h, w), np.uint8)
    mask[y:y + 80, x:x + 80] = 1
    return frame, mask, [x, y, x + 80, y + 80]


class MovingCan:
    def __init__(self):
        self.x = 40
    def detect(self, frame):
        _, mask, box = scene(self.x)
        return [dict(label='can', score=.9, bbox=box, mask=mask,
                     center=[(box[0] + box[2]) / 2, (box[1] + box[3]) / 2], contour=[])]


def jpeg(frame):
    return cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 95])[1].tobytes()


def run(steps, monkeypatch, dt=.15):
    clock = [100.]
    monkeypatch.setattr('vision.live.time.monotonic', lambda: clock[0])
    engine = MovingCan()
    s = LiveSession(engine=engine)
    ids = []
    prev = steps[0]
    for x in steps:
        engine.x = x
        clock[0] += dt
        r = s.receive(jpeg(scene(x, blur=min(41, abs(x - prev) // 3 * 2 + 1))[0]))
        prev = x
        ids += [o['observation']['object_id'] for o in r['objects']]
    return s, ids, r


def test_fast_sweep_keeps_one_id(monkeypatch):
    # settle, then jump 130 px per analysed frame (~870 px/s) with motion blur: boxes never overlap
    steps = [40, 40, 40] + list(range(170, 540, 130)) + list(range(410, 40, -130))
    s, ids, last = run(steps, monkeypatch)
    assert len(s.objects) == 1, f'{len(s.objects)} objects created'
    assert len(set(ids)) == 1
    assert last['objects'][0]['observation']['tracking_state'] in ('tracked', 'predicted')


def test_reappearing_after_brief_loss_keeps_id(monkeypatch):
    clock = [100.]
    monkeypatch.setattr('vision.live.time.monotonic', lambda: clock[0])
    engine = MovingCan()
    s = LiveSession(engine=engine)
    engine.x = 200
    for _ in range(3):
        clock[0] += .15
        s.receive(jpeg(scene(200)[0]))
    first = next(iter(s.objects))
    blank = np.full((360, 640, 3), 90, np.uint8)
    real = engine.detect
    engine.detect = lambda f: []
    for _ in range(8):  # ~2.4 s gone (hand over it)
        clock[0] += .3
        s.receive(jpeg(blank))
    engine.detect = real
    engine.x = 300  # comes back 100 px away
    for _ in range(3):
        clock[0] += .15
        r = s.receive(jpeg(scene(300)[0]))
    assert list(s.objects) == [first]
    assert r['objects'][0]['observation']['tracking_state'] == 'tracked'


def test_identical_neighbour_does_not_steal_the_id(monkeypatch):
    """Two same-looking cans: a fast move of one must not hand its ID to the other."""
    clock = [100.]
    monkeypatch.setattr('vision.live.time.monotonic', lambda: clock[0])

    class TwoCans:
        def __init__(self):
            self.xs = [60, 420]
        def detect(self, frame):
            out = []
            for x in self.xs:
                _, mask, box = scene(x)
                out.append(dict(label='can', score=.9, bbox=box, mask=mask,
                                center=[(box[0] + box[2]) / 2, (box[1] + box[3]) / 2], contour=[]))
            return out

    def frame(xs, blur=0):
        f = np.full((360, 640, 3), 90, np.uint8)
        for x in xs:
            f[120:200, x:x + 80] = PATCH
        if blur:
            k = np.zeros((1, blur), np.float32); k[0] = 1 / blur
            f = cv2.filter2D(f, -1, k)
        return f

    e = TwoCans()
    s = LiveSession(engine=e)
    for _ in range(3):
        clock[0] += .15
        s.receive(jpeg(frame(e.xs)))
    ids = {}
    for oid, meta in s.objects.items():
        ids[oid] = meta['bbox'][0]
    parked = min(ids, key=ids.get)  # the can at x=60 never moves
    for x in (300, 180):            # the right can sweeps toward it fast
        e.xs = [60, x]
        clock[0] += .15
        r = s.receive(jpeg(frame(e.xs, blur=31)))
    by_id = {o['observation']['object_id']: o['observation'] for o in r['objects']}
    assert by_id[parked]['bbox_xyxy'][0] < 120, 'parked can lost its ID to the moving one'
    assert len(s.objects) == 2
