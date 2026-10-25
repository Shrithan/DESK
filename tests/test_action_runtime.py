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
    assert e.presses==['space'],'confirmed cover triggers immediately'
    for _ in range(5):t(enabled=False)
    assert e.presses==['space']
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
    assert r.update(token,2,True)['armed']
    n[0]+=.5;r.tick()
    assert not r.status()['armed']
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

def test_missing_snapshot_retains_activation_while_heartbeats_continue():
    r,e,p,n,s,t,h,m=setup('test.synth_filter')
    t();token=r.token;r.snapshot=lambda *args:None
    for _ in range(50):t()
    assert r.token==token and r.status()['armed']
    assert not p.writes
    r.snapshot=lambda *args:s
    s['position'][1]=.9
    for _ in range(5):t()
    assert r.token==token and not p.writes
    n[0]+=.5;r.tick()
    assert not r.status()['armed'],'lost heartbeat still disarms'
    r.close()

def test_immediate_cover_uses_small_center_and_tracking_loss_alone_never_fires():
    r,e,p,n,s,t,h,m=setup('keyboard','cover_button')
    assert r.cover.bbox==(33,33,57,57)
    for _ in range(5):t()
    s['tracked']=False;s['frame'][:]=0
    t();assert not e.presses
    s['tracked']=True;s['frame'][:]=60
    for _ in range(5):t()
    h.amount=.9;s['tracked']=False;s['frame'][33:57,33:57]=230
    t();assert e.presses==['space']
    assert r.details['evidence']=='covered'
    for _ in range(10):t()
    assert len(e.presses)==1
    r.close()


def test_action_group_keeps_independent_mappings_active(monkeypatch):
    import vision.action_runtime as module
    made=[]
    class Runtime:
        def __init__(self,*a,**kw):self.token=None;made.append(self)
        def arm(self,m):self.mapping=m;self.token=str(len(made));return dict(token=self.token,armed=True)
        def status(self):return dict(armed=bool(self.token))
        def update(self,*a):return self.status()
        def close(self):self.token=None
    monkeypatch.setattr(module,'ActionRuntime',Runtime)
    group=module.ActionGroup(None,None)
    a=group.arm(dict(object_id='a',output='audio.volume'))
    b=group.arm(dict(object_id='b',output='display.brightness'))
    assert group.update(a['token'],1,True)['armed']
    assert group.update(b['token'],1,True)['armed']
    group.stop(a['token'])
    assert group.update(b['token'],2,True)['armed']
    group.close();assert not made[1].token

def test_detected_occluding_object_can_press_without_a_hand():
    r,e,p,n,s,t,h,m=setup('keyboard','cover_button')
    for _ in range(5):t()
    s['tracked']=False;s['frame'][25:65,25:65]=230
    s['occluders']=[[28,28,62,62]]
    t();assert e.presses==['space']
    r.close()
