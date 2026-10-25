"""Temporal scheduling/lifetime tests, without downloading or running neural weights."""
import threading
import time
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from vision.temporal import TemporalCamera
from vision.live import LiveSession

torch = pytest.importorskip('torch')

class Predictor:
    image_size = 32
    def init_state(self, directory, **kwargs):
        return dict(obj_ids=[], video_height=64, video_width=64, images={}, num_frames=1, masks=[])
    def add_new_mask(self, state, frame_idx, obj_id, mask):
        state['obj_ids'].append(obj_id)
        state['masks'].append(mask)
    def propagate_in_video(self, state, start_frame_idx, max_frame_num_to_track):
        yield start_frame_idx, state['obj_ids'], torch.tensor(np.array(state['masks']))[:,None].float()*2-1

class Detector:
    def __init__(self): self.calls=0
    def detect(self, frame): self.calls+=1;return []

def camera():
    return TemporalCamera(SimpleNamespace(torch=torch,lock=threading.Lock(),predictor=Predictor()),Detector())

def inputs():
    frame=np.zeros((64,64,3),np.uint8)
    mask=np.zeros((64,64),np.uint8);mask[15:35,15:35]=255
    return frame,[dict(track_id='original',label='can',mask=mask)]

def test_discovery_enrollment_and_identity_survive_missing_flow():
    c=camera();frame,seeds=inputs()
    assert c.detect(frame,seeds)==[] and c.detector.calls==1
    assert c.detect(frame,seeds)==[] # prompt is not tracking evidence
    seeds[0]['tracked']=False
    result=c.detect(frame,seeds)
    assert result[0]['track_id']=='original'
    assert result[0]['bbox']==[15,15,35,35]
    assert list(c.state['images'])==[1] # retain only current source image

def test_camera_memories_are_independent_and_bounded():
    a,b=camera(),camera();frame,seeds=inputs()
    a.last_semantic=time.monotonic();a.detect(frame,seeds)
    a.max_steps=2
    a.detect(frame,seeds)
    assert a.steps==2
    assert a.detect(frame,seeds)==[] and a.steps==1
    assert b.state is None
    assert a.state['obj_ids']==['original']

def test_new_identity_reenrolls_instead_of_reusing_old_memory():
    c=camera();frame,seeds=inputs();c.last_semantic=time.monotonic()
    c.detect(frame,seeds)
    seeds[0]['track_id']='replacement'
    assert c.detect(frame,seeds)==[]
    assert c.state['obj_ids']==['replacement']

def test_reset_and_old_work_are_rejected():
    s=LiveSession();frame,_=inputs();generation=s.generation
    s.reset()
    s._job_result=([dict(label='can')],1,None,generation,time.monotonic())
    assert not s._collect_detection(frame)
    s._job_result=([dict(label='can')],1,None,s.generation,time.monotonic()-1)
    assert not s._collect_detection(frame)

def test_background_correction_does_not_wait_on_camera_thread():
    entered,release=threading.Event(),threading.Event()
    class Slow:
        def detect(self,frame,seeds):
            entered.set();release.wait(2);return []
    s=LiveSession(engine=Detector(),async_detection=True)
    s.temporal=Slow();frame,_=inputs()
    try:
        s._submit_detection(frame)
        assert entered.wait(1)
        assert s._job is not None
        assert s._collect_detection(frame) is False
    finally:
        release.set()
        job=s._job
        if job:job.join(2)

def test_temporal_failure_keeps_async_discovery():
    class Broken:
        def detect(self,frame,seeds):raise RuntimeError('test failure')
    s=LiveSession(engine=Detector(),async_detection=True)
    s.temporal=Broken();frame,_=inputs()
    s._submit_detection(frame)
    job=s._job
    if job:job.join(2)
    assert s.temporal is None
    assert s.async_detection
    assert 'test failure' in s.detector_error

def test_unknown_temporal_id_cannot_enroll_an_object():
    frame,seeds=inputs()
    mask=seeds[0]['mask']
    class TemporalOnly:
        def detect(self,frame):
            return [dict(track_id='not-enrolled',label='can',score=.99,
                         bbox=[15,15,35,35],mask=mask,center=[25,25],contour=[])]
    s=LiveSession(engine=TemporalOnly())
    for _ in range(3):
        s.last_detection=0
        ok,jpeg=cv2.imencode('.jpg',frame)
        assert ok
        assert s.receive(jpeg.tobytes())['objects']==[]
