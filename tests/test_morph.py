import io
import json
import pytest
from vision.morph import MorphPlanner, validate_plan, catalog
from vision.voice import VoiceError
from vision.keyboard import KeyboardOutput

OBJECTS=[dict(object_id='can-1',label='cup',number=1,controllers=['joystick','slider_x','slider_y'])]
def plan():return dict(status='ready',message='Can mapped to arrows.',mapping=dict(object_id='can-1',controller='joystick',bindings=dict(up='up',down='down',left='left',right='right'),mode='game',deadzone=.18))

def test_actual_catalog_and_validated_provider_request():
    requests=[]
    def transport(request,timeout):
        requests.append(json.loads(request.data))
        return io.BytesIO(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(plan())}}]}).encode())
    result=MorphPlanner(config=lambda:{'ASI1_API_KEY':'local-test'},transport=transport).plan('Use the can as arrow keys',OBJECTS)
    assert result['plan']==plan()
    context=json.loads(requests[0]['messages'][1]['content'])
    assert context['objects']==OBJECTS and context['catalog']==catalog()
    assert 'local-test' not in json.dumps(requests)

@pytest.mark.parametrize('change',[
    {'object_id':'invented'}, {'controller':'dial'}, {'controller':'shell'},
    {'bindings':dict(up='cmd',down='down',left='left',right='right')},
    {'deadzone':float('nan')}, {'mode':'execute'}, {'extra':'code'},
])
def test_rejects_unavailable_or_invented_plan(change):
    value=plan();value['mapping'].update(change)
    with pytest.raises(ValueError):validate_plan(value,OBJECTS)


def test_missing_key_and_malformed_provider_response_never_map():
    with pytest.raises(VoiceError):MorphPlanner(config=lambda:{}).plan('map',OBJECTS)
    planner=MorphPlanner(config=lambda:{'ASI1_API_KEY':'fake'},transport=lambda *a,**k:io.BytesIO(b'{}'))
    with pytest.raises(VoiceError):planner.plan('map',OBJECTS)
    assert validate_plan(dict(status='clarify',message='Which can?',mapping=None),OBJECTS)['mapping'] is None


def test_custom_keys_still_release_on_tracking_loss():
    events=[]
    class Backend:
        def event(self,*args):events.append(args)
    visible=[True]
    output=KeyboardOutput(backend_factory=Backend,trusted=lambda:True,visible=lambda oid:visible[0],start_watchdog=False)
    token=output.arm('can-1',allowed_keys=['up','down','left','right'])['token']
    output.update(token,['up'],0)
    with pytest.raises(ValueError):output.update(token,['w'],1)
    visible[0]=False;output.tick()
    assert events==[('up',True),('up',False)]
    output.close()


def test_module_catalog_and_exact_existing_game_profiles():
    from vision.morph import MODULES, plan_format
    assert {'general','flight-stick','subway-slide','dj'} <= set(catalog()['modules'])
    for module in ('flight-stick','subway-slide','subway-tilt','can-slide-wasd'):
        value=plan()
        value['mapping'].update(module=module,setup_action='map',output='keyboard',bindings=MODULES[module]['bindings'])
        assert validate_plan(value,OBJECTS)==value
        value['mapping']['bindings']=dict(up='w',down='s',left='a',right='d')
        with pytest.raises(ValueError,match='existing module profile'):validate_plan(value,OBJECTS)
    schema=plan_format(OBJECTS,catalog())['json_schema']['schema']
    for variant in schema['properties']['mapping']['anyOf'][1:]:
        assert 'module' in variant['required'] and 'setup_action' in variant['required']


def test_setup_conversation_reaches_planner_and_is_bounded():
    requests=[]
    def transport(request,timeout):
        requests.append(json.loads(request.data))
        return io.BytesIO(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(plan())}}]}).encode())
    planner=MorphPlanner(config=lambda:{'ASI1_API_KEY':'fake'},transport=transport)
    history=[dict(transcript='I want to fly',message='Which object should be the flight joystick?')]
    planner.plan('the cup',OBJECTS,conversation=history)
    assert json.loads(requests[0]['messages'][1]['content'])['conversation']==history
    for invalid in (history*9,[{'message':'missing transcript'}],[dict(transcript='a'*1001,message='x')]):
        with pytest.raises(ValueError,match='conversation'):planner.plan('cup',OBJECTS,conversation=invalid)


def test_rejects_calibration_outside_dj_and_unknown_modules():
    for change in ({'module':'invented'},{'setup_action':'execute'},{'setup_action':'enable'},{'module':'dj'}):
        value=plan();value['mapping'].update(change)
        with pytest.raises(ValueError):validate_plan(value,OBJECTS)
