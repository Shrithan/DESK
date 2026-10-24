import numpy as np
import pytest
from tracking2d import Tracker
from vision.demo import fixture
from vision.association import associate


def test_translation_identity_loss_and_reacquisition():
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
    recovered = tracker.update(frame,'a',1533,'v1')[0]
    assert recovered['tracking_state'] == 'tracked'
    assert recovered['object_id'] == initial['object_id']
    assert not set(a).intersection(f['track_id'] for f in recovered['features'])


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


def test_recovery_rejects_wrong_object_and_duplicate_appearance():
    tracker = Tracker()
    frame,mask = fixture()
    tracker.select(frame,'a',110,100,0,'v1',mask)
    blank = np.zeros_like(frame)
    tracker.update(blank,'a',33,'v1')
    rng = np.random.default_rng(999)
    wrong = blank.copy()
    wrong[70:150,80:160] = rng.integers(40,255,(80,80,3),dtype=np.uint8)
    for stamp in [66,99]:
        assert tracker.update(wrong,'a',stamp,'v1')[0]['tracking_state'] == 'lost'
    duplicate = frame.copy()
    duplicate[70:150,200:280] = frame[70:150,80:160]
    for stamp in [132,165]:
        assert tracker.update(duplicate,'a',stamp,'v1')[0]['tracking_state'] == 'lost'
    returned,_ = fixture(70)
    assert tracker.update(returned,'a',198,'v1')[0]['tracking_state'] == 'lost'
    assert tracker.update(returned,'a',231,'v1')[0]['tracking_state'] == 'tracked'


def test_responsive_tracking_bridges_brief_blur_but_expires_stale_points():
    from tracking2d.tracker import TrackingTuning
    tracker=Tracker(TrackingTuning.responsive())
    frame,mask=fixture()
    initial=tracker.select(frame,'a',110,100,1000,'v1',mask)
    blank=np.zeros_like(frame)
    uncertain=tracker.update(blank,'a',1100,'v1')[0]
    assert uncertain['tracking_state']=='predicted'
    assert uncertain['features']==[]  # Never present stale 2D points as measurements.
    assert uncertain['bbox_xyxy']==initial['bbox_xyxy']
    returned=tracker.update(fixture(8)[0],'a',1200,'v1')[0]
    assert returned['tracking_state']=='tracked'
    assert returned['object_id']==initial['object_id']
    assert tracker.update(blank,'a',1300,'v1')[0]['tracking_state']=='predicted'
    expired=tracker.update(blank,'a',1600,'v1')[0]
    assert expired['tracking_state']=='lost'
    assert expired['bbox_xyxy'] is None


def test_responsive_tracking_tolerates_partial_feature_dropout(monkeypatch):
    import cv2
    from tracking2d.tracker import TrackingTuning
    frame,mask=fixture()
    original=cv2.calcOpticalFlowPyrLK
    def dropout(*args,**kwargs):
        points,status,errors=original(*args,**kwargs)
        status[:int(len(status)*.6)]=0
        return points,status,errors
    monkeypatch.setattr(cv2,'calcOpticalFlowPyrLK',dropout)
    tracker=Tracker(TrackingTuning.responsive())
    initial=tracker.select(frame,'a',110,100,1000,'v1',mask)
    result=tracker.update(fixture(4)[0],'a',1033,'v1')[0]
    assert result['tracking_state']=='tracked'
    assert result['object_id']==initial['object_id']
    assert len(result['features'])>=6


def test_responsive_flow_tracks_fast_translation_without_identity_reset():
    from tracking2d.tracker import TrackingTuning
    tracker=Tracker(TrackingTuning.responsive())
    frame,mask=fixture()
    initial=tracker.select(frame,'fast',110,100,1000,'v1',mask)
    for i,dx in enumerate([22,44,66,88],1):
        obs=tracker.update(fixture(dx)[0],'fast',1000+i*33,'v1')[0]
        assert obs['tracking_state']=='tracked'
        assert obs['object_id']==initial['object_id']
        assert obs['bbox_xyxy'][0]==pytest.approx(80+dx,abs=2)
