import time

import pytest

from camera.ingest import CameraHub, CameraWorker
from camera.rig import load_rig
from camera.sources import SyntheticPatternSource

IDS = ["cam_1", "cam_2", "cam_3"]


def synthetic_rig():
    return load_rig(overrides={c: {"kind": "synthetic"} for c in IDS})


def test_newest_frame_policy_bounds_frame_age_for_a_slow_consumer():
    rig = synthetic_rig()
    with CameraHub(rig) as hub:
        assert hub.wait_until_streaming(5)
        sub = hub.subscribe("cam_1")
        ages = []
        for _ in range(8):
            time.sleep(0.25)  # consumer is ~8x slower than the 30 fps camera
            f = sub.get(timeout=1)
            ages.append(f.age_ms())
        assert max(ages) < 100, ages  # never a backlog, only the newest frame
        assert sub.dropped > 30


def test_reconnect_keeps_camera_id_and_resumes():
    rig = synthetic_rig()
    spec = rig.camera("cam_2")
    epoch = time.monotonic_ns()
    attempts = []

    def factory():
        attempts.append(1)
        # first connection "unplugs" after 10 frames, later ones keep streaming
        return SyntheticPatternSource("cam_2", 64, 36, 60, time.monotonic_ns(), fail_after=10 if len(attempts) == 1 else None)

    w = CameraWorker(spec, factory, reconnect_backoff_s=(0.05, 0.1))
    w.start()
    try:
        end = time.monotonic() + 5
        while time.monotonic() < end and not (w.stats.reconnects >= 1 and w.stats.frames > 20):
            time.sleep(0.02)
        assert w.stats.reconnects >= 1 and w.stats.frames > 20
        assert w.latest().camera_id == "cam_2"
        assert w.health()["state"] == "streaming"
    finally:
        w.stop()
    del epoch


def test_dead_camera_degrades_gracefully_without_reordering_ids():
    rig = synthetic_rig()

    def broken():
        raise OSError("device not present")

    with CameraHub(rig, source_factories={"cam_3": broken}) as hub:
        assert all(hub.workers[c].stats.frames >= 0 for c in IDS)
        end = time.monotonic() + 5
        while time.monotonic() < end and not (hub.workers["cam_1"].stats.frames > 3 and hub.workers["cam_2"].stats.frames > 3):
            time.sleep(0.02)
        h = hub.health()
        assert h["status"] == "degraded" and h["multiview_available"]
        assert h["streaming_cameras"] == ["cam_1", "cam_2"]
        assert h["cameras"]["cam_3"]["state"] in ("connecting", "disconnected")
        fs = hub.frameset()
        assert set(fs.frames) == {"cam_1", "cam_2"} and fs.missing == ("cam_3",)
        assert [c["camera_id"] for c in hub.inventory()["cameras"]] == IDS


def test_unknown_camera_id_raises():
    hub = CameraHub(synthetic_rig())
    with pytest.raises(KeyError):
        hub.latest("cam_9")
