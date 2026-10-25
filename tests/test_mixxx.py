import json
import pytest
from vision.mixxx import MixxxBridge,DJRuntime,encode,PREFIX,TARGETS

class Output:
 def __init__(self):self.sent=[]
 def send_message(self,data):self.sent.append(data)

def test_midi_feedback_is_validated_and_values_are_real_feedback():
 clock=[100.];b=MixxxBridge(lambda:clock[0]);b.output=Output()
 assert not b.status()['online']
 packet=dict(type='state',protocol=1,session=b.session,ack=0,values={'mixxx.crossfader':.5},native_values={'mixxx.crossfader':0})
 b._receive((encode(packet),0),None)
 assert b.status()['online'] and b.get_value('mixxx.crossfader')==.5
 b.set_value('mixxx.crossfader',.6)
 assert b.get_value('mixxx.crossfader')==.5,'sending must not pretend Mixxx acknowledged the value'
 command=json.loads(bytes(b.output.sent[-1][len(PREFIX):-1]))
 assert command['value']==.6 and command['seq']==1
 bad=dict(packet,session='unrelated',values={'mixxx.crossfader':.8});b._receive((encode(bad),0),None)
 assert b.get_value('mixxx.crossfader')==.5
 clock[0]+=1
 assert not b.status()['online']
 with pytest.raises(RuntimeError):b.set_value('mixxx.crossfader',.7)

class Bridge:
 def __init__(self):self.values={k:.5 for k in TARGETS};self.sent=[];self.ack=0;self.online=True
 def close(self):pass
 def status(self):return dict(online=self.online,values=dict(self.values),ack=self.ack,connected=True)
 def set_value(self,target,value):self.sent.append((target,value));self.values[target]=value;self.ack+=1;return self.ack

def setup():
 now=[100.];b=Bridge();samples={i:dict(tracked=True,stamp=now[0],frame_id=1,position=[.5,.5]) for i in ['a','b','c']}
 r=DJRuntime(lambda oid:samples.get(oid),b,lambda:now[0])
 def tick(dt=.1):
  now[0]+=dt
  for s in samples.values():s['stamp']=now[0];s['frame_id']+=1
  return r.update()
 return r,b,samples,now,tick

def test_multiple_physical_sliders_can_control_different_decks():
 r,b,s,n,tick=setup();r.bind('a','mixxx.deck1.volume');r.bind('b','mixxx.deck2.volume');r.arm(True);tick()
 s['a']['position'][1]=.4;s['b']['position'][1]=.6
 for _ in range(6):tick()
 assert b.values['mixxx.deck1.volume']>.6 and b.values['mixxx.deck2.volume']<.4
 assert r.status()['armed']

def test_pickup_prevents_initial_jump_and_loss_holds_mixxx_value():
 r,b,s,n,tick=setup();b.values['mixxx.deck1.volume']=.9;r.bind('a','mixxx.deck1.volume');r.arm(True)
 for _ in range(5):tick()
 assert b.sent==[]
 s['a']['position'][1]=.3
 for _ in range(8):tick()
 assert r.mappings['mixxx.deck1.volume']['picked_up']
 s['a']['position'][1]=.25
 for _ in range(5):tick()
 held=b.values['mixxx.deck1.volume'];count=len(b.sent);s['a']['tracked']=False
 for _ in range(8):tick()
 assert b.values['mixxx.deck1.volume']==held and len(b.sent)==count
 s['a']['tracked']=True;s['a']['position'][1]=.6
 for _ in range(5):tick()
 assert b.values['mixxx.deck1.volume']==held,'recovery requires pickup again'

def test_camera_lease_disconnect_and_calibration_guards():
 r,b,s,n,tick=setup();r.bind('a','mixxx.crossfader');r.arm(True);n[0]+=1
 assert not r.status()['armed']
 tick()
 r.calibrate('mixxx.crossfader','low');r.calibrate('mixxx.crossfader','high');r.arm(True);tick()
 assert 'too close' in r.mappings['mixxx.crossfader']['state']
 b.online=False;assert not r.status()['armed']
 with pytest.raises(RuntimeError):r.arm(True)

def test_reversed_travel_manual_override_and_duplicate_frames():
 r,b,s,n,tick=setup();r.bind('a','mixxx.crossfader','x')
 s['a']['position'][0]=.8;r.calibrate('mixxx.crossfader','low')
 s['a']['position'][0]=.2;r.calibrate('mixxx.crossfader','high')
 s['a']['position'][0]=.5;r.arm(True);tick()
 s['a']['position'][0]=.4
 for _ in range(8):tick()
 assert b.values['mixxx.crossfader']>.6
 before=len(b.sent)
 for _ in range(10):r.update()
 assert len(b.sent)==before,'repeated browser polls must not invent camera samples'
 b.values['mixxx.crossfader']=.1;tick()
 assert not r.mappings['mixxx.crossfader']['picked_up']
 assert b.values['mixxx.crossfader']==.1,'manual mixer adjustment wins until pickup'

def test_new_mapping_status_is_strict_json_before_any_output():
 r,b,s,n,tick=setup()
 state=r.bind('a','mixxx.deck1.volume')
 assert json.loads(json.dumps(state,allow_nan=False))['mappings']['mixxx.deck1.volume']['last_write'] is None

def test_http_binding_and_status_are_serializable_without_midi_hardware():
 import http.client
 from test_live import running_server
 with running_server() as server:
  bridge=Bridge();server.dj=DJRuntime(lambda oid:dict(tracked=True,stamp=server.dj.clock(),frame_id=1,position=[.5,.5]),bridge)
  client=http.client.HTTPConnection(*server.server_address)
  client.request('POST','/api/dj/bind',json.dumps(dict(object_id='fixture',target='mixxx.deck1.volume')),{'Content-Type':'application/json'})
  response=client.getresponse();assert response.status==200
  assert json.loads(response.read())['mappings']['mixxx.deck1.volume']['last_write'] is None
  client.request('GET','/api/dj/status');response=client.getresponse();assert response.status==200
  assert 'mixxx.deck1.volume' in json.loads(response.read())['mappings']
  client.close()
