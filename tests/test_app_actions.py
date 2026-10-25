import plistlib
from pathlib import Path
import pytest
from vision.app_actions import OpenApplication
from vision.morph import catalog,validate_plan,plan_format
from test_action_runtime import setup


def test_open_adapter_uses_registered_app_path_without_shell(tmp_path):
    app=tmp_path/'Example App.app';(app/'Contents').mkdir(parents=True)
    (app/'Contents/Info.plist').write_bytes(plistlib.dumps(dict(CFBundleIdentifier='test.example')))
    calls=[];a=OpenApplication('test.example',app,runner=lambda *args,**kwargs:calls.append((args,kwargs)))
    a.trigger()
    assert calls[0][0][0]==['/usr/bin/open','-a',str(app)]
    assert calls[0][1]['shell'] is False
    (app/'Contents/Info.plist').write_bytes(plistlib.dumps(dict(CFBundleIdentifier='changed')))
    with pytest.raises(RuntimeError):a.trigger()
    assert len(calls)==1


def test_cover_trigger_runs_once_per_cover_without_keyboard_permission():
    r,e,p,n,s,t,h,m=setup('keyboard','cover_button')
    class Task:
        calls=0
        def trigger(self):self.calls+=1
    task=Task();r.stop();r.trusted=lambda:False
    r.registry.register('app.open.test',dict(label='Open Test',kind='trigger',controllers=['cover_button'],bindings=dict(press='open')),task)
    m.update(output='app.open.test',bindings=dict(press='open'));token=r.arm(m)['token'];sequence=[0]
    def t():
        n[0]+=.1;s['stamp']=n[0];s['frame_id']+=1;sequence[0]+=1
        return r.update(token,sequence[0],True)
    for _ in range(6):t()
    h.amount=.9;s['frame'][25:65,25:65]=220;s['tracked']=False
    for _ in range(12):t()
    assert task.calls==1 and r.details['value']==1 and e.presses==[]
    h.amount=0;s['frame'][:]=60;s['tracked']=True
    for _ in range(6):t()
    assert r.details['value']==0
    h.amount=.9;s['frame'][25:65,25:65]=220
    for _ in range(6):t()
    assert task.calls==2
    r.close()


def test_registry_schema_groups_app_targets_and_rejects_unknown_tasks():
    targets={f'app.open.{i}':dict(label=f'Open App {i}',kind='trigger',controllers=['cover_button'],available=True,bindings=dict(press='open')) for i in range(30)}
    caps=catalog(targets,True);objects=[dict(object_id='b',controllers=['cover_button'])]
    plan=dict(status='ready',message='Open app.',mapping=dict(object_id='b',controller='cover_button',output='app.open.4',bindings=dict(press='open'),deadzone=.18,mode='game'))
    assert validate_plan(plan,objects,caps)==plan
    variants=plan_format(objects,caps)['json_schema']['schema']['properties']['mapping']['anyOf']
    assert len(variants)==2 and len(variants[1]['properties']['output']['enum'])==30
    plan['mapping']['output']='shell.run'
    with pytest.raises(ValueError):validate_plan(plan,objects,caps)


def test_this_button_resolves_unique_assigned_input_before_provider_call():
    import io,json
    from vision.morph import MorphPlanner
    requests=[]
    result=dict(status='ready',message='Open app.',mapping=dict(object_id='assigned',controller='cover_button',output='app.open.test',bindings=dict(press='open'),deadzone=.18,mode='game'))
    targets={'app.open.test':dict(label='Open Test',kind='trigger',controllers=['cover_button'],available=True,bindings=dict(press='open'))}
    def transport(request,timeout):
        requests.append(json.loads(request.data));return io.BytesIO(json.dumps(dict(choices=[dict(finish_reason='stop',message=dict(content=json.dumps(result)))])).encode())
    planner=MorphPlanner(config=lambda:{'ASI1_API_KEY':'fixture'},transport=transport,catalog_provider=lambda:catalog(targets,True))
    objects=[dict(object_id='assigned',label='can',controllers=['cover_button'],assigned_controller='cover_button'),dict(object_id='other',label='cup',controllers=['cover_button'])]
    assert planner.plan('When I cover this button, open Test.',objects)['plan']==result
    context=json.loads(requests[0]['messages'][1]['content'])
    assert context['selected_object_id']=='assigned'


def test_only_server_generated_agent_replies_can_be_spoken():
    import json,http.client
    from test_live import running_server
    with running_server() as server:
        server.mapping_objects=lambda:[]
        class Planner:
            def plan(self,*args):return dict(plan=dict(status='clarify',message='Which app should the button open?',mapping=None))
        server.morph=Planner();spoken=[]
        class Speech:
            def speak(self,text):spoken.append(text);return b'RIFF0000WAVEfixture'
        server.reply_speech=Speech()
        c=http.client.HTTPConnection('127.0.0.1',server.server_port)
        c.request('POST','/api/morph/plan',json.dumps(dict(transcript='Open an app.')),{'Content-Type':'application/json'})
        r=c.getresponse();data=json.loads(r.read());assert r.status==200 and data['reply_id']
        c.request('POST','/api/voice/reply',json.dumps(dict(reply_id=data['reply_id'])),{'Content-Type':'application/json'})
        r=c.getresponse();assert r.status==200 and r.read().startswith(b'RIFF')
        assert spoken==['Which app should the button open?']
        c.request('POST','/api/voice/reply',json.dumps(dict(text='Unregistered text')),{'Content-Type':'application/json'})
        r=c.getresponse();r.read();assert r.status==400
        assert len(spoken)==1
        c.close()
