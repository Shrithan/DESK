import numpy as np
import pytest
from vision.button_inputs import ObjectButtons

class Hand:
    amount=0.
    def coverage(self,*args):return self.amount
    def close(self):pass

def setup():
    now=[100.];hand=Hand();frame=np.full((180,240,3),140,np.uint8)
    sample=dict(frame=frame,bbox=[80,60,120,100],tracked=True,stamp=now[0],frame_id=1)
    monitor=ObjectButtons(lambda *args:sample,lambda:hand,lambda:now[0]);monitor.add('detected-can')
    def step(covered=False,tracked=True):
        now[0]+=.1;sample['stamp']=now[0];sample['frame_id']+=1;sample['tracked']=tracked
        frame[:]=140
        if covered:frame[60:100,80:120]=30
        hand.amount=.9 if covered else 0.
        return monitor.update(['detected-can'])['buttons']['detected-can']
    return monitor,sample,now,hand,step

def test_detected_object_produces_sustained_binary_state_through_occlusion():
    m,s,n,h,step=setup()
    for _ in range(5):assert step()['value']==0
    values=[step(True,False)['value'] for _ in range(10)]
    assert values[-1]==1 and sum(values)>4
    assert m.buttons['detected-can']['button'].count==1
    assert step(False,True)['value']==0
    for _ in range(6):state=step(False,True)
    assert state['value']==0 and state['phase']=='ready'
    for _ in range(5):state=step(True,False)
    assert state['value']==1 and state['presses']==2
    m.close()

def test_missing_object_without_a_hand_never_becomes_one():
    m,s,n,h,step=setup()
    for _ in range(5):step()
    s['frame'][:]=30;s['tracked']=False;h.amount=0.
    for _ in range(8):
        n[0]+=.1;s['stamp']=n[0];s['frame_id']+=1
        assert m.update(['detected-can'])['buttons']['detected-can']['value']==0
    assert m.buttons['detected-can']['button'].count==0

def test_stale_camera_clears_pressed_value():
    m,s,n,h,step=setup()
    for _ in range(5):step()
    for _ in range(5):state=step(True,False)
    assert state['value']==1
    n[0]+=.5
    assert m.update(['detected-can'])['buttons']['detected-can']['value']==0

def test_visible_object_motion_updates_the_object_anchor():
    m,s,n,h,step=setup()
    for _ in range(5):step()
    s['bbox']=[140,60,180,100]
    step()
    assert m.buttons['detected-can']['button'].bbox==(140,60,180,100)
    assert m.buttons['detected-can']['state']['value']==0

def test_mapping_requires_detected_uncovered_object():
    m,s,n,h,step=setup();s['tracked']=False
    with pytest.raises(ValueError):m.add('other')
    s['tracked']=True;h.amount=.9
    with pytest.raises(ValueError):m.add('other')
    assert m.update([])['buttons']=={}
