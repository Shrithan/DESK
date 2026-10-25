import numpy as np
import pytest
from vision.action_runtime import ActionRuntime
from vision.desktop_actions import ActionRegistry
from vision.cover import CoverButton
from vision.morph import validate_plan, catalog

class Parameter:
    def __init__(self):self.value=.5;self.writes=[]
    def get_value(self):return self.value
    def set_value(self,value):self.value=value;self.writes.append(value)
class Events:
    def __init__(self):self.scrolls=[];self.presses=[]
    def scroll(self,value):self.scrolls.append(value)
    def press(self,key):self.presses.append(key)
class Hands:
    amount=0
    def coverage(self,*args):return self.amount
    def close(self):pass


def setup(output='desktop.scroll',controller='slider_y'):
    now=[100.];frame=np.full((100,100,3),60,np.uint8)
    sample=dict(tracked=True,bbox=[25,25,65,65],position=[.5,.5],stamp=now[0],frame_id=1,frame=frame)
    registry=ActionRegistry();parameter=Parameter()
    registry.register('test.synth_filter',dict(label='Synth filter',kind='continuous',controllers=['slider_x','slider_y'],bindings=dict(negative='decrease',positive='increase')),parameter)
    events=Events();hands=Hands()
    runtime=ActionRuntime(lambda *a:sample,registry=registry,events_factory=lambda:events,hand_factory=lambda:hands,trusted=lambda:True,clock=lambda:now[0],start_watchdog=False)
    bindings=dict(press='space') if controller=='cover_button' else dict(negative='up',positive='down') if output=='desktop.scroll' else dict(negative='decrease',positive='increase')
    mapping=dict(object_id='item',controller=controller,output=output,bindings=bindings,mode='game',deadzone=.18)
    token=runtime.arm(mapping)['token'];sequence=[0]
    def tick(dt=.1,enabled=True):
        now[0]+=dt;sample['stamp']=now[0];sample['frame_id']+=1;sequence[0]+=1
        return runtime.update(token,sequence[0],enabled)
    return runtime,events,parameter,now,sample,tick,hands,mapping


def test_scroll_is_movement_driven_not_stationary_repeat():
    r,e,p,n,s,t,h,m=setup();t();assert e.scrolls==[]
    s['position'][1]=.7;t();assert e.scrolls[-1]<0
    for _ in range(20):t()
    count=len(e.scrolls)
    for _ in range(20):t()
    assert len(e.scrolls)==count
    s['tracked']=False;s['position'][1]=.1;t();assert len(e.scrolls)==count
    r.close()


def test_generic_parameter_adapter_needs_no_target_specific_slider_code():
    r,e,p,n,s,t,h,m=setup('test.synth_filter')
    t();assert not p.writes
    s['position'][1]=.8
    for _ in range(15):t()
    assert .5<p.value<=1
    before=p.value;t(enabled=False);assert p.value==before
    n[0]+=.36;r.tick();assert not r.status()['armed']
    r.close()


def test_cover_requires_hand_change_dwell_and_uncover_to_repeat():
    r,e,p,n,s,t,h,m=setup('keyboard','cover_button')
    for _ in range(5):t()
    assert r.cover.phase=='ready'
    # Object merely disappears: not a button press.
    s['frame'][25:65,25:65]=220;s['tracked']=False
    for _ in range(4):t()
    assert not e.presses
    s['frame'][:]=60;s['tracked']=True
    for _ in range(5):t()
    h.amount=.9;s['frame'][25:65,25:65]=220;s['tracked']=False
    for _ in range(10):t()
    assert e.presses==['space']
    h.amount=0;s['frame'][:]=60;s['tracked']=True
    for _ in range(5):t()
    h.amount=.9;s['frame'][25:65,25:65]=220
    for _ in range(5):t()
    assert e.presses==['space','space']
    r.close()


def test_cover_jitter_frame_changes_disabled_focus_and_tokens():
    r,e,p,n,s,t,h,m=setup('keyboard','cover_button')
    for _ in range(5):t()
    h.amount=.9;s['frame'][25:65,25:65]=220;t();h.amount=0;t()
    assert not e.presses
    for _ in range(5):t(enabled=False)
    assert not e.presses
    with pytest.raises(PermissionError):r.update('wrong-owner',99,True)
    s['frame']=np.zeros((120,100,3),np.uint8)
    with pytest.raises(RuntimeError):t()
    assert not r.status()['armed']
    r.close()


def test_catalog_validation_of_dynamic_targets_and_unavailable_actions():
    r,e,p,n,s,t,h,m=setup('test.synth_filter');caps=catalog(r.registry.catalog(),True)
    objects=[dict(object_id='item',controllers=['slider_x','slider_y','cover_button'])]
    plan=dict(status='ready',message='Synth filter mapped',mapping=m)
    assert validate_plan(plan,objects,caps)==plan
    m['output']='invented.app.bass'
    with pytest.raises(ValueError):validate_plan(plan,objects,caps)
    m['output']='test.synth_filter';m['controller']='cover_button';m['bindings']=dict(press='space')
    with pytest.raises(ValueError):validate_plan(plan,objects,caps)
    r.close()


def test_brief_camera_gap_retains_mapping_and_rebases_parameter_on_recovery():
    r,e,p,n,s,t,h,m=setup('test.synth_filter')
    t();token=r.token
    n[0]+=.4
    state=r.update(token,2,True)
    assert state['armed'] and 'paused' in state['reason'] and not p.writes
    # Camera resumes with the same object in a new position: no brightness jump.
    s['position'][1]=.8;s['stamp']=n[0];s['frame_id']+=1
    state=r.update(token,3,True)
    assert state['armed'] and not p.writes
    s['position'][1]=.9
    for _ in range(10):t()
    assert p.value>.5
    r.close()


def test_short_snapshot_lock_contention_does_not_drop_mapping():
    r,e,p,n,s,t,h,m=setup('test.synth_filter')
    token=r.token;original=r.snapshot;r.snapshot=lambda *args:None
    assert r.update(token,1,True)['armed']
    n[0]+=2.1
    assert not r.update(token,2,True)['armed']
    r.close()


def test_slider_reentry_preserves_mapping_without_brightness_jump_or_filter_tail():
    r,e,p,n,s,t,h,m=setup('test.synth_filter')
    t();token=r.token;s['tracked']=False
    for _ in range(120):t()
    assert r.token==token and not p.writes
    s['tracked']=True;s['position'][1]=.9
    for _ in range(8):t()
    assert r.token==token and not p.writes,'returning at another edge must not change brightness'
    s['position'][1]=.95
    for _ in range(5):t()
    assert p.value>.5
    r.close()


def test_parameter_slider_has_doubled_gain_and_reaches_target_quickly():
    r,e,p,n,s,t,h,m=setup('test.synth_filter');t()
    s['position'][1]=.6
    for _ in range(8):t()
    assert p.value==pytest.approx(.8,abs=.005),'10% field travel should change the value by 30 percentage points'
    assert all(0<=value<=1 for value in p.writes)
    r.close()
