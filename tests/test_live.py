"""JPEG-to-observation smoke tests; no physical camera is simulated as live."""
from contextlib import contextmanager
import http.client
import json
import threading

import cv2
import numpy as np
import pytest

from vision.demo import fixture
from vision.live import LiveSession, LiveServer


def jpeg(frame):
    ok, data = cv2.imencode('.jpg',frame)
    assert ok
    return data.tobytes()


def test_live_selection_motion_loss_and_return():
    session=LiveSession()
    first=session.receive(jpeg(fixture()[0]))
    selected=session.select(first['frame_id'],[80,70,160,150])
    oid=selected['observation']['object_id']
    for i in range(1,8):
        result=session.receive(jpeg(fixture(i)[0]))
    assert result['observation']['object_id']==oid
    assert result['observation']['tracking_state']=='tracked'
    assert result['motion']['displacement_px'][0]==pytest.approx(7,abs=1)
    lost=session.receive(jpeg(np.zeros((240,320,3),np.uint8)))
    assert lost['observation']['tracking_state']=='lost'
    assert lost['motion'] is None
    assert session.receive(jpeg(fixture(40)[0]))['observation']['tracking_state']=='lost'
    returned=session.receive(jpeg(fixture(40)[0]))
    assert returned['observation']['tracking_state']=='tracked'
    assert returned['observation']['object_id']==oid
    assert returned['motion']['speed_px_s'] is None
    assert session.clear()['observation'] is None


def test_stale_selection_and_bad_frames_do_not_replace_target():
    session=LiveSession()
    old=session.receive(jpeg(fixture()[0]))
    first=session.select(old['frame_id'],[80,70,160,150])
    session.receive(jpeg(fixture(1)[0]))
    with pytest.raises(ValueError,match='Preview changed'):
        session.select(old['frame_id'],[80,70,160,150])
    with pytest.raises(ValueError):
        session.receive(b'not a jpeg')
    for box in [None,[0,0,1,1],[-1,0,10,10],[1,1,20,float('nan')]]:
        with pytest.raises(ValueError):
            session.select(session.frame_id,box)
    assert session.observation['object_id']==first['observation']['object_id']
    changed=session.receive(jpeg(np.zeros((480,640,3),np.uint8)))
    assert changed['selection_reset']
    assert changed['observation'] is None


@contextmanager
def running_server():
    server=LiveServer(('127.0.0.1',0))
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3)


def test_http_live_pipeline_and_origin_rejection():
    with running_server() as server:
        connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
        connection.request('GET','/')
        response=connection.getresponse()
        assert response.status==200 and b'Start overhead webcam' in response.read()
        connection.request('POST','/api/frame',jpeg(fixture()[0]),{'Content-Type':'image/jpeg'})
        response=connection.getresponse();assert response.status==200
        first=json.loads(response.read())
        connection.request('POST','/api/select',json.dumps({'frame_id':first['frame_id'],'bbox':[80,70,160,150]}),{'Content-Type':'application/json'})
        response=connection.getresponse();assert response.status==200
        assert json.loads(response.read())['observation']['tracking_state']=='tracked'
        connection.request('POST','/api/frame',jpeg(fixture(4)[0]),{'Content-Type':'image/jpeg'})
        response=connection.getresponse();assert response.status==200
        assert json.loads(response.read())['motion']['displacement_px'][0]==pytest.approx(4,abs=1)
        connection.request('POST','/api/clear','{}',{'Content-Type':'application/json','Origin':'https://unrelated.example'})
        response=connection.getresponse();assert response.status==403;response.read()
        connection.close()


def test_automatic_acquisition_without_click_and_same_id_after_loss():
    session=LiveSession()
    blank=np.zeros((240,320,3),np.uint8)
    for _ in range(20):
        result=session.receive(jpeg(blank))
        assert result['observation'] is None
    for i in range(12):
        result=session.receive(jpeg(fixture(i*2)[0]))
        if result['observation']:
            break
    assert result['selection_source']=='automatic_motion'
    assert result['observation']['tracking_state']=='tracked'
    oid=result['observation']['object_id']
    lost=session.receive(jpeg(blank))
    assert lost['observation']['tracking_state']=='lost'
    for _ in range(3):
        assert session.receive(jpeg(blank))['observation']['object_id']==oid
    session.receive(jpeg(fixture(i*2+20)[0]))
    returned=session.receive(jpeg(fixture(i*2+20)[0]))
    assert returned['observation']['tracking_state']=='tracked'
    assert returned['observation']['object_id']==oid


def test_auto_disabled_and_global_change_does_not_acquire():
    session=LiveSession()
    session.set_auto(False)
    blank=np.zeros((240,320,3),np.uint8)
    for _ in range(20):session.receive(jpeg(blank))
    for i in range(10):
        assert session.receive(jpeg(fixture(i)[0]))['observation'] is None
    session.set_auto(True)
    for _ in range(20):session.receive(jpeg(blank))
    for _ in range(4):
        changed=session.receive(jpeg(np.full_like(blank,255)))
        assert changed['observation'] is None
    with pytest.raises(ValueError):session.set_auto('true')


def test_two_camera_http_sessions_stay_independent():
    with running_server() as server:
        connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
        results={}
        for role,dx in [('front',0),('top',30)]:
            headers={'Content-Type':'image/jpeg','X-Camera-Id':role,'X-Capture-Sample-Ms':'1000'}
            connection.request('POST','/api/frame',jpeg(fixture(dx)[0]),headers)
            response=connection.getresponse();assert response.status==200
            frame=json.loads(response.read())
            headers={'Content-Type':'application/json','X-Camera-Id':role}
            connection.request('POST','/api/select',json.dumps({'frame_id':frame['frame_id'],'bbox':[80+dx,70,160+dx,150]}),headers)
            response=connection.getresponse();assert response.status==200
            results[role]=json.loads(response.read())
        assert results['front']['observation']['object_id']!=results['top']['observation']['object_id']
        assert results['front']['observation']['camera_id']=='front'
        assert results['top']['observation']['camera_id']=='top'
        connection.request('GET','/api/world')
        response=connection.getresponse();assert response.status==200
        mapped=json.loads(response.read())
        assert mapped['views']['front']['tracked'] and mapped['views']['top']['tracked']
        assert mapped['world'] is None  # No box-center triangulation or guessed Z.
        connection.request('POST','/api/clear','{}',{'Content-Type':'application/json','X-Camera-Id':'front'})
        response=connection.getresponse();assert response.status==200;response.read()
        assert server.sessions['top'].observation is not None
        connection.close()


class SegmentationFixture:
    """Known object masks let acquisition policy be tested independently of ML."""
    def __init__(self):
        self.visible=True
    def detect(self,frame):
        if not self.visible:return []
        _,mask=fixture()
        return [dict(label='can',score=.9,bbox=[80,70,160,150],mask=mask,
                     center=[120,110],contour=[[80,70],[160,70],[160,150],[80,150]])]


def test_ai_acquires_stationary_object_without_background_motion(monkeypatch):
    clock=[100.]
    monkeypatch.setattr('vision.live.time.monotonic',lambda:clock[0])
    engine=SegmentationFixture();session=LiveSession(engine=engine)
    frame=jpeg(fixture()[0])
    first=session.receive(frame)
    assert first['observation'] is None
    assert first['auto_status']=='confirming_object'
    clock[0]+=.3
    second=session.receive(frame)
    assert second['selection_source']=='semantic_object'
    assert second['object_label']=='can'
    assert second['observation']['bbox_xyxy']==[80,70,160,150]
    oid=second['observation']['object_id']
    clock[0]+=.3
    assert session.receive(frame)['observation']['object_id']==oid


def test_ai_does_not_fall_back_to_random_motion_or_track_without_model_support(monkeypatch):
    clock=[100.]
    monkeypatch.setattr('vision.live.time.monotonic',lambda:clock[0])
    engine=SegmentationFixture();engine.visible=False
    session=LiveSession(engine=engine)
    for i in range(30):
        clock[0]+=.3
        result=session.receive(jpeg(fixture(i)[0]))
        assert result['observation'] is None
    engine.visible=True
    for _ in range(2):
        clock[0]+=.3
        result=session.receive(jpeg(fixture()[0]))
    assert result['observation']['tracking_state']=='tracked'
    engine.visible=False
    clock[0]+=2.0
    result=session.receive(jpeg(fixture()[0]))
    assert result['observation']['tracking_state']=='lost'


def test_new_same_class_object_keeps_independent_identity_and_motion(monkeypatch):
    clock=[100.]
    monkeypatch.setattr('vision.live.time.monotonic',lambda:clock[0])
    class TwoObjects:
        boxes=[]
        def detect(self,frame):
            result=[]
            for x,y in reversed(self.boxes):
                mask=np.zeros(frame.shape[:2],np.uint8);mask[y:y+60,x:x+60]=255
                result.append(dict(label='can',score=.9,bbox=[x,y,x+60,y+60],mask=mask,center=[x+30,y+30],contour=[]))
            return result
    engine=TwoObjects();session=LiveSession(engine=engine)
    rng=np.random.default_rng(42)
    patches=[rng.integers(0,256,(60,60,3),dtype=np.uint8) for _ in range(2)]
    def step(boxes):
        clock[0]+=.3;engine.boxes=boxes
        frame=np.zeros((240,320,3),np.uint8)
        for patch,(x,y) in zip(patches,boxes):frame[y:y+60,x:x+60]=patch
        return session.receive(jpeg(frame))
    step([(30,60)])
    first=step([(30,60)]);oid=first['objects'][0]['observation']['object_id']
    step([(32,60),(210,120)])
    both=step([(34,60),(210,118)])
    assert len(both['objects'])==2
    ids=[o['observation']['object_id'] for o in both['objects']]
    assert len(set(ids))==2 and ids[0]==oid
    moved=step([(38,60),(210,113)])
    assert [o['observation']['object_id'] for o in moved['objects']]==ids
    assert all(o['observation']['tracking_state']=='tracked' for o in moved['objects'])
    assert moved['objects'][0]['motion']['displacement_px'][0]==pytest.approx(8,abs=1)
    assert moved['objects'][1]['motion']['displacement_px'][1]==pytest.approx(-5,abs=1)
    # Losing the second object does not interrupt the first or create duplicates.
    for _ in range(8):last=step([(38,60)])
    assert len(last['objects'])==2
    assert last['objects'][0]['observation']['tracking_state']=='tracked'
    assert last['objects'][1]['observation']['tracking_state']=='lost'


def test_single_target_mode_never_adds_second_identity_and_restores_same_target(monkeypatch):
    clock=[100.]
    monkeypatch.setattr('vision.live.time.monotonic',lambda:clock[0])
    engine=SegmentationFixture();session=LiveSession(engine=engine);session.single_target=True
    def step(frame):
        clock[0]+=.3
        return session.receive(jpeg(frame))
    step(fixture()[0]);result=step(fixture()[0]);oid=result['objects'][0]['observation']['object_id']
    original=engine.detect
    def extra(frame):
        ds=original(frame)
        if ds:
            other=dict(ds[0]);other.update(label='book',bbox=[200,70,280,150],mask=np.roll(ds[0]['mask'],120,axis=1))
            ds.append(other)
        return ds
    engine.detect=extra
    for _ in range(4):assert len(step(fixture()[0])['objects'])==1
    engine.visible=False;clock[0]+=2
    assert step(np.zeros((240,320,3),np.uint8))['observation']['tracking_state']=='lost'
    engine.visible=True
    returned=step(fixture()[0])
    assert returned['observation']['tracking_state']=='tracked'
    assert returned['observation']['object_id']==oid
    assert len(returned['objects'])==1


def test_sensitive_continuation_does_not_seed_low_confidence_noise(monkeypatch):
    clock=[100.]
    monkeypatch.setattr('vision.live.time.monotonic',lambda:clock[0])
    engine=SegmentationFixture();original=engine.detect;score=[.15]
    def detect(frame):
        ds=original(frame)
        for d in ds:d['score']=score[0]
        return ds
    engine.detect=detect
    session=LiveSession(engine=engine);session.single_target=True
    def step():
        clock[0]+=.3
        return session.receive(jpeg(fixture()[0]))
    for _ in range(3):assert step()['observation'] is None
    score[0]=.4;step();acquired=step();oid=acquired['observation']['object_id']
    score[0]=.15
    for _ in range(8):
        result=step()
        assert result['observation']['object_id']==oid
        assert result['observation']['tracking_state']=='tracked'


def test_motion_required_acquisition_ignores_stationary_background(monkeypatch):
    clock=[100.]
    monkeypatch.setattr('vision.live.time.monotonic',lambda:clock[0])
    engine=SegmentationFixture();original=engine.detect;offset=[0]
    def detect(frame):
        ds=original(frame)
        for d in ds:
            d['mask']=np.roll(d['mask'],offset[0],axis=1)
            d['bbox']=[80+offset[0],70,160+offset[0],150]
        return ds
    engine.detect=detect;session=LiveSession(engine=engine);session.single_target=True;session.motion_required=True
    for _ in range(4):
        clock[0]+=.3
        assert session.receive(jpeg(fixture()[0]))['observation'] is None
    offset[0]=8;clock[0]+=.3
    result=session.receive(jpeg(fixture(8)[0]))
    assert result['observation']['tracking_state']=='tracked'


def test_workspace_multi_acquires_small_overhead_objects_and_keeps_existing_ids(monkeypatch):
    clock=[100.]
    monkeypatch.setattr('vision.live.time.monotonic',lambda:clock[0])
    class Engine:
        boxes=[]
        def detect(self,frame):
            ds=[]
            for x,y in self.boxes:
                mask=np.zeros(frame.shape[:2],np.uint8);mask[y:y+24,x:x+24]=255
                ds.append(dict(label='can',score=.8,bbox=[x,y,x+24,y+24],mask=mask,center=[x+12,y+12],contour=[]))
            return ds
    engine=Engine();session=LiveSession('top',engine);session.workspace_multi=True;session.motion_required=True;session.overhead=True
    rng=np.random.default_rng(91);patches=[rng.integers(0,255,(24,24,3),dtype=np.uint8) for _ in range(2)]
    def step(boxes):
        engine.boxes=boxes;clock[0]+=.4
        frame=np.zeros((240,320,3),np.uint8)
        for patch,(x,y) in zip(patches,boxes):frame[y:y+24,x:x+24]=patch
        return session.receive(jpeg(frame))
    for _ in range(3):assert not step([(40,80)])['objects']
    first=step([(46,80)]);oid=first['objects'][0]['observation']['object_id']
    step([(46,80),(220,120)])
    result=step([(46,80),(226,120)])
    assert len(result['objects'])==2
    assert result['objects'][0]['observation']['object_id']==oid
    assert all(o['observation']['tracking_state']=='tracked' for o in result['objects'])


def test_workspace_restores_original_id_after_moved_occlusion_and_label_flicker(monkeypatch):
    clock=[100.]
    monkeypatch.setattr('vision.live.time.monotonic',lambda:clock[0])
    class Engine:
        visible=True
        dx=0
        label='can'
        def detect(self,frame):
            if not self.visible:return []
            _,mask=fixture(self.dx)
            return [dict(label=self.label,score=.9,bbox=[80+self.dx,70,160+self.dx,150],mask=mask,center=[120+self.dx,110],contour=[])]
    engine=Engine();session=LiveSession(engine=engine);session.workspace_multi=True
    def step(blank=False):
        clock[0]+=.4
        return session.receive(jpeg(np.zeros((240,320,3),np.uint8) if blank else fixture(engine.dx)[0]))
    step();initial=step();oid=initial['objects'][0]['observation']['object_id']
    engine.visible=False;clock[0]+=2
    lost=step(True);assert lost['observation']['tracking_state']=='lost'
    engine.visible=True;engine.dx=65;engine.label='bottle'
    restored=step()
    assert len(restored['objects'])==1
    assert restored['observation']['object_id']==oid
    assert restored['observation']['tracking_state']=='tracked'
    assert restored['object_label']=='can','detector label flicker must not rename the established target'
    assert restored['motion']['displacement_px'][0]==pytest.approx(65,abs=1)


def test_workspace_ambiguous_return_does_not_spawn_duplicate_or_steal_identity(monkeypatch):
    clock=[100.]
    monkeypatch.setattr('vision.live.time.monotonic',lambda:clock[0])
    engine=SegmentationFixture();session=LiveSession(engine=engine);session.workspace_multi=True
    def step(frame):
        clock[0]+=.4
        return session.receive(jpeg(frame))
    step(fixture()[0]);initial=step(fixture()[0]);oid=initial['observation']['object_id']
    engine.visible=False;clock[0]+=2;step(np.zeros((240,320,3),np.uint8))
    _,mask=fixture(50)
    def duplicate(frame):
        return [dict(label='can',score=.9,bbox=[130,70,210,150],mask=mask.copy(),center=[170,110],contour=[]),
                dict(label='can',score=.89,bbox=[40,70,120,150],mask=np.roll(mask,-90,axis=1),center=[80,110],contour=[])]
    engine.detect=duplicate
    frame=np.zeros((240,320,3),np.uint8);patch=fixture()[0][70:150,80:160]
    frame[70:150,130:210]=patch;frame[70:150,40:120]=patch
    for _ in range(3):result=step(frame)
    assert len(result['objects'])==1
    assert result['observation']['object_id']==oid
    assert result['observation']['tracking_state']=='lost'


def test_textureless_disk_works_as_overhead_only_observation(monkeypatch):
    clock=[100.]
    monkeypatch.setattr('vision.live.time.monotonic',lambda:clock[0])
    class Engine:
        visible=True
        dx=0
        def detect(self,frame):
            if not self.visible:return []
            mask=np.zeros(frame.shape[:2],np.uint8);mask[80:130,100+self.dx:150+self.dx]=255
            return [dict(label='disk',score=.85,bbox=[100+self.dx,80,150+self.dx,130],mask=mask,center=[125+self.dx,105],contour=[])]
    engine=Engine();session=LiveSession('top',engine);session.workspace_multi=True;session.overhead=True
    def step():
        clock[0]+=.4
        frame=np.zeros((240,320,3),np.uint8);frame[80:130,100+engine.dx:150+engine.dx]=180
        return session.receive(jpeg(frame))
    step();first=step();oid=first['observation']['object_id']
    assert first['object_label']=='disk' and first['motion'] is not None
    engine.dx=5;result=step()
    assert result['observation']['object_id']==oid and result['observation']['tracking_state']=='tracked'
    assert result['motion']['center_px'][0]==pytest.approx(130,abs=1)
    engine.visible=False;result=step()
    assert result['observation']['tracking_state']=='lost' and result['motion'] is None


def test_voice_http_routes_and_camera_lock_independence():
    import io
    from vision.voice import CartesiaVoice
    audio=b'RIFF'+b'\x00'*4+b'WAVE'+b'fixture'
    with running_server() as server:
        server.voice=CartesiaVoice(config=lambda: {}, transport=lambda *a,**kw:pytest.fail('No key must never call Cartesia'))
        connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=2)
        connection.request('GET','/api/voice/status')
        response=connection.getresponse();assert response.status==200
        assert not json.loads(response.read())['configured']
        connection.request('POST','/api/voice/speak','{"event":"test"}',{'Content-Type':'application/json'})
        response=connection.getresponse();assert response.status==503;response.read()
        server.voice=CartesiaVoice(config=lambda: {'CARTESIA_API_KEY':'fixture'},transport=lambda *a,**kw:io.BytesIO(audio))
        with server.sessions['front'].lock,server.sessions['top'].lock:
            connection.request('POST','/api/voice/speak','{"event":"test"}',{'Content-Type':'application/json'})
            response=connection.getresponse();assert response.status==200
            assert response.getheader('Content-Type')=='audio/wav'
            assert response.read()==audio
        connection.request('GET','/.env')
        response=connection.getresponse();assert response.status==404;response.read()
        connection.request('POST','/api/voice/speak','{"event":"test"}',{'Content-Type':'application/json','Origin':'https://unrelated.example'})
        response=connection.getresponse();assert response.status==403;response.read()
        connection.close()


def test_usb_status_route_keeps_private_device_data_off_wire():
    class Guard:
        def status(self):return dict(required=True,verified=True,connected=False,phone_count=0,video_transport='unverified')
    with running_server() as server:
        server.usb_guard=Guard()
        connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=2)
        connection.request('GET','/api/iphone/usb')
        response=connection.getresponse()
        assert response.status==200 and not json.loads(response.read())['connected']
        connection.close()


def test_voice_command_and_keyboard_http_routes_use_separate_locks():
    from vision.keyboard import KeyboardOutput
    class Backend:
        def __init__(self):self.events=[]
        def event(self,*args):self.events.append(args)
    class Speech:
        def transcribe(self,body):return dict(transcript='map this can to a joystick',intent={'action':'map_joystick','label':'can','number':None})
    backend=Backend()
    with running_server() as server:
        server.keyboard.close()
        server.keyboard=KeyboardOutput(backend_factory=lambda:backend,trusted=lambda:True,visible=lambda oid:True,start_watchdog=False)
        server.speech_input=Speech()
        connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=2)
        connection.request('POST','/api/voice/transcribe',b'fixture clip',{'Content-Type':'audio/wav'})
        response=connection.getresponse();assert response.status==200
        assert json.loads(response.read())['intent']['action']=='map_joystick'
        with server.sessions['front'].lock,server.sessions['top'].lock:
            connection.request('POST','/api/keys/arm','{"object_id":"can"}',{'Content-Type':'application/json'})
            response=connection.getresponse();assert response.status==200;token=json.loads(response.read())['token']
            connection.request('POST','/api/keys/update',json.dumps(dict(token=token,keys=['w'],sequence=0)),{'Content-Type':'application/json'})
            response=connection.getresponse();assert response.status==200;assert json.loads(response.read())['held']==['w']
        connection.request('POST','/api/keys/stop','{}',{'Content-Type':'application/json'})
        response=connection.getresponse();assert response.status==200;assert not json.loads(response.read())['armed']
        connection.request('POST','/api/keys/arm','{"object_id":"can"}',{'Content-Type':'application/json','Origin':'https://unrelated.example'})
        response=connection.getresponse();assert response.status==403;response.read()
        connection.close()
    assert backend.events==[('w',True),('w',False)]


def test_morph_http_uses_actual_fresh_snapshot_and_releases_camera_lock(monkeypatch):
    from vision.cover import HandDetector
    monkeypatch.setattr(HandDetector,"available",staticmethod(lambda:False))
    import time
    seen=[]
    with running_server() as server:
        top=server.sessions['top']
        top.last_received=time.monotonic()
        top.result=lambda:dict(objects=[dict(observation=dict(object_id='real-can',tracking_state='tracked'),object_label='cup',number=2,orientation=None)])
        class Planner:
            def status(self):return dict(configured=True)
            def plan(self,text,objects,selected,current):
                # Planning/network work must not block vision's lock.
                acquired=[]
                def probe():
                    ok=top.lock.acquire(timeout=.2);acquired.append(ok)
                    if ok:top.lock.release()
                t=threading.Thread(target=probe);t.start();t.join();assert acquired==[True]
                seen.append(objects)
                return dict(plan=dict(status='clarify',message='Which control?',mapping=None))
        server.morph=Planner()
        connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
        connection.request('GET','/api/morph/status');response=connection.getresponse();assert response.status==200;response.read()
        payload=json.dumps(dict(transcript='Map this',moved=['real-can'],objects=[dict(object_id='invented')]))
        connection.request('POST','/api/morph/plan',payload,{'Content-Type':'application/json'})
        response=connection.getresponse();assert response.status==200;assert json.loads(response.read())['plan']['status']=='clarify'
        assert seen[0]==[dict(object_id='real-can',label='cup',number=2,controllers=['joystick','slider_x','slider_y'],recently_moved=True)]
        connection.request('POST','/api/morph/plan',payload,{'Content-Type':'application/json','Origin':'https://unrelated.example'})
        response=connection.getresponse();assert response.status==403;response.read();connection.close()


def test_generic_action_http_and_registered_sticker():
    import time
    from vision.action_runtime import ActionRuntime
    with running_server() as server:
        connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
        connection.request('POST','/api/frame',jpeg(fixture()[0]),{'Content-Type':'image/jpeg','X-Camera-Id':'top'})
        response=connection.getresponse();assert response.status==200;response.read()
        connection.request('POST','/api/register-region',json.dumps(dict(bbox=[.25,.29,.5,.63])),{'Content-Type':'application/json','X-Camera-Id':'top'})
        response=connection.getresponse();assert response.status==200
        item=json.loads(response.read())['objects'][0];assert item['object_label']=='sticker'
        oid=item['observation']['object_id'];top=server.sessions['top']
        class Parameter:
            value=.5
            def get_value(self):return self.value
            def set_value(self,value):self.value=value
        parameter=Parameter()
        server.actions.registry.register('test.app.parameter',dict(label='App parameter',kind='continuous',controllers=['slider_x','slider_y'],bindings=dict(negative='decrease',positive='increase')),parameter)
        mapping=dict(object_id=oid,controller='slider_x',output='test.app.parameter',bindings=dict(negative='decrease',positive='increase'),deadzone=.18,mode='game')
        connection.request('POST','/api/actions/arm',json.dumps(dict(mapping=mapping)),{'Content-Type':'application/json'})
        response=connection.getresponse();assert response.status==200;token=json.loads(response.read())['token']
        connection.request('POST','/api/actions/update',json.dumps(dict(token=token,sequence=1,enabled=False)),{'Content-Type':'application/json'})
        response=connection.getresponse();assert response.status==200;assert json.loads(response.read())['armed'];assert parameter.value==.5
        connection.request('POST','/api/actions/update',json.dumps(dict(token='wrong',sequence=2,enabled=True)),{'Content-Type':'application/json'})
        response=connection.getresponse();assert response.status==403;response.read()
        connection.request('POST','/api/actions/stop','{}',{'Content-Type':'application/json'})
        response=connection.getresponse();assert response.status==200;assert not json.loads(response.read())['armed']
        mapping['output']='unregistered.app.parameter'
        connection.request('POST','/api/actions/arm',json.dumps(dict(mapping=mapping)),{'Content-Type':'application/json'})
        response=connection.getresponse();assert response.status==400;response.read();connection.close()
