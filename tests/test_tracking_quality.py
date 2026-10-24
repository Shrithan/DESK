"""Regression guard for tracking smoothness (see tests/bench_tracking.py for the full benchmark)."""
import bench_tracking as B


def test_can_stays_inside_the_box_up_to_1000_px_per_s():
    s = B.run(seconds=8.0, detect_every=.12)
    buckets = s['buckets']
    for name in ('slow <500', 'fast 500-1000'):
        if name in buckets:
            n, inside = buckets[name]
            assert inside / n >= .97, f'{name}: can inside the box only {inside}/{n} frames'
    assert len(s['ids']) == 1, 'the can changed identity'
    assert s['inside'] / s['frames'] >= .9
