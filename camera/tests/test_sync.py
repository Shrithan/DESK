import numpy as np

from camera.frame import CameraFrame
from camera.sync import SyncMonitor, estimate_offset_ms, match_frameset

MS = 1_000_000


def frames(cid, times_ms):
    img = np.zeros((2, 2, 3), np.uint8)
    return [CameraFrame(cid, i, int(t * MS), int(t * MS) + MS, (2, 2), img) for i, t in enumerate(times_ms)]


def test_pairs_nearest_frames_to_the_laggard():
    recent = {"cam_1": frames("cam_1", [0, 33, 66, 100]), "cam_2": frames("cam_2", [10, 43, 76]), "cam_3": frames("cam_3", [5, 38, 71, 104])}
    fs = match_frameset(recent, 20 * MS)
    assert fs.complete
    assert fs.reference_time_monotonic_ns == 76 * MS  # cam_2 lags: its newest frame is the reference
    assert {k: f.capture_time_monotonic_ns // MS for k, f in fs.frames.items()} == {"cam_1": 66, "cam_2": 76, "cam_3": 71}
    assert fs.spread_ms == 10


def test_camera_outside_tolerance_is_reported_missing_not_silently_paired():
    recent = {"cam_1": frames("cam_1", [0, 33, 66]), "cam_2": frames("cam_2", [500, 533]), "cam_3": []}
    fs = match_frameset(recent, 20 * MS)
    assert not fs.complete
    assert set(fs.missing) == {"cam_2", "cam_3"}
    assert set(fs.frames) == {"cam_1"}


def test_monitor_summarises_spread():
    m = SyncMonitor(["a", "b"])
    for k in range(10):
        m.record(match_frameset({"a": frames("a", [k * 33]), "b": frames("b", [k * 33 + 5])}, 20 * MS))
    s = m.summary()
    assert s["complete_ratio"] == 1.0 and s["spread_ms"]["max"] == 5.0


def test_motion_offset_estimation_recovers_known_latency():
    rng = np.random.default_rng(0)
    t = np.arange(0, 6000, 1.0)  # ms
    events = np.convolve(rng.random(t.size) > 0.995, np.hanning(120), mode="same")
    ta = np.arange(0, 6000, 33.3)
    tb = np.arange(3, 6000, 33.3)
    sig_a = np.interp(ta, t, events)
    sig_b = np.interp(tb - 25.0, t, events)  # camera B stamps events 25 ms late
    off, corr = estimate_offset_ms((ta * 1e6).astype(np.int64), sig_a, (tb * 1e6).astype(np.int64), sig_b)
    assert abs(off - 25.0) <= 3.0 and corr > 0.8
