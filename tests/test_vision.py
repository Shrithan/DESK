import numpy as np
import pytest
from tracking2d import Tracker
from vision.demo import fixture
from vision.association import associate


def test_translation_identity_loss_and_no_reacquisition():
    tracker = Tracker()
    frame, mask = fixture()
    initial = tracker.select(frame,'a',110,100,1000,'v1',mask)
    for i in range(1,11):
        obs = tracker.update(fixture(i)[0],'a',1000+i*33,'v1')[0]
        assert obs['object_id'] == initial['object_id']
        assert obs['tracking_state'] == 'tracked'
    a = {f['track_id']:f['pixel_xy'] for f in initial['features']}
    displacements = [f['pixel_xy'][0]-a[f['track_id']][0] for f in obs['features']]
    assert np.median(displacements) == pytest.approx(10,abs=.5)
    obs = tracker.update(np.zeros_like(frame),'a',1400,'v1')[0]
    assert obs['tracking_state'] == 'lost'
    assert not obs['features']
    assert tracker.update(frame,'a',1500,'v1')[0]['tracking_state'] == 'lost'


def test_multiple_ids_and_validation():
    tracker = Tracker()
    frame, mask = fixture()
    a = tracker.select(frame,'a',110,100,1000,'v1',mask)
    b = tracker.select(frame,'a',110,100,1000,'v1',mask)
    assert a['object_id'] != b['object_id']
    with pytest.raises(ValueError):
        tracker.update(frame,'a',1000,'v1')
    assert tracker.deselect('a',a['object_id'])
    with pytest.raises(ValueError):
        tracker.select(frame,'a',-1,10,1000,'v1')


def test_association_epipolar_and_skew():
    frame, mask = fixture()
    other,_ = fixture(10)
    F = np.array([[0,0,0],[0,0,-1],[0,1,0]],float)
    result = associate(frame,mask,other,F,timestamp_a_ms=1000,timestamp_b_ms=1000,
                       calibration_version='v1')
    assert result['state'] == 'needs_confirmation'
    assert len(result['matches']) >= 6
    assert all(m['sampson_error_px2'] <= 2.25 for m in result['matches'])
    bad = np.array([[0,0,0],[0,0,-1],[0,1,80]],float)
    assert not associate(frame,mask,other,bad,timestamp_a_ms=1000,timestamp_b_ms=1000,
                         calibration_version='v1')['matches']
    assert associate(frame,mask,other,F,timestamp_a_ms=1000,timestamp_b_ms=1100,
                      calibration_version='v1')['reason'] == 'timestamp_skew'
