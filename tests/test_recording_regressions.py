"""Recording regressions: late masks, class flicker, and contaminated flow anchors."""
import time
import cv2
import numpy as np
import pytest
from tracking2d.tracker import Tracker,TrackingTuning
from vision.objects import align_detection
from vision.live import LiveSession

rng=np.random.default_rng(59)
patch=rng.integers(40,220,(70,50,3),dtype=np.uint8)

def scene(x=130):
    f=np.full((240,360,3),35,np.uint8);f[80:150,x:x+50]=patch
    mask=np.zeros(f.shape[:2],np.uint8);mask[80:150,x:x+50]=255
    return f,dict(label='cup',score=.9,bbox=[x,80,x+50,150],mask=mask,center=[x+25,115],contour=[])

def jpeg(f):return cv2.imencode('.jpg',f)[1].tobytes()

def test_delayed_mask_follows_actual_reversal_not_predicted_position():
    source,d=scene(130);current,_=scene(110)
    s=LiveSession();s._job_result=([d],5,None,s.generation,time.monotonic(),source)
    assert s._collect_detection(current)
    assert s.detections[0]['bbox'][0]==pytest.approx(110,abs=2)
    assert s.detections[0]['center'][0]==pytest.approx(134.5,abs=2)

def test_old_mask_cannot_reseed_a_fully_covered_object():
    source,d=scene()
    assert align_detection(d,source,np.full_like(source,35)) is None

def test_dropout_keeps_measured_feature_anchors(monkeypatch):
    frame,d=scene();t=Tracker(TrackingTuning.responsive())
    o=t.select(frame,'top',150,110,100,'v',mask=d['mask'])
    target=t.targets['top',o['object_id']];target.velocity=np.array([1.,0.])
    before=(target.mask.copy(),target.points.copy(),target.gray.copy())
    monkeypatch.setattr(t,'_flow',lambda *args:(None,None))
    out=t.update(np.full_like(frame,35),'top',180,'v',recover_lost=False)
    assert out[0]['tracking_state']=='predicted'
    for actual,expected in zip((target.mask,target.points,target.gray),before):
        assert np.array_equal(actual,expected),'prediction must not turn background into measured feature anchors'

def test_overhead_lid_label_flicker_keeps_one_id(monkeypatch):
    clock=[100.];monkeypatch.setattr('vision.live.time.monotonic',lambda:clock[0])
    class Labels:
        label='disk'
        def detect(self,frame):
            _,d=scene();return [dict(d,label=self.label)]
    engine=Labels();s=LiveSession('top',engine);s.overhead=s.workspace_multi=True
    for _ in range(3):clock[0]+=.2;s.receive(jpeg(scene()[0]))
    original=list(s.objects)
    assert len(original)==1
    for label in ['cup','bottle','disk','can','cup']:
        engine.label=label;clock[0]+=.2;r=s.receive(jpeg(scene()[0]))
        assert list(s.objects)==original
        assert r['objects'][0]['observation']['tracking_state']=='tracked'
        assert r['objects'][0]['object_label']=='disk'

def test_unrelated_distant_disk_does_not_attach_to_can(monkeypatch):
    clock=[100.];monkeypatch.setattr('vision.live.time.monotonic',lambda:clock[0])
    class Labels:
        label='can';x=80
        def detect(self,frame):
            _,d=scene(self.x);return [dict(d,label=self.label)]
    e=Labels();s=LiveSession('top',e);s.overhead=s.workspace_multi=True
    for _ in range(3):clock[0]+=.2;s.receive(jpeg(scene(80)[0]))
    oid=next(iter(s.objects));e.label='disk';e.x=250
    frame,_=scene(80);frame[80:150,250:300]=patch
    clock[0]+=.2;r=s.receive(jpeg(frame))
    original=next(o for o in r['objects'] if o['observation']['object_id']==oid)
    assert original['observation']['bbox_xyxy'][0]<150
