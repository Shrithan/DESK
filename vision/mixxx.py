"""Local, bidirectional Mixxx MIDI bridge and simultaneous camera faders."""
import importlib.util
import json
import math
import secrets
import threading
import time

PREFIX=[0xF0,0x7D,0x44,0x53,0x4B,1]
TARGETS={
 'mixxx.deck1.volume':dict(label='Deck A volume',group='[Channel1]',key='volume',axis='y'),
 'mixxx.deck2.volume':dict(label='Deck B volume',group='[Channel2]',key='volume',axis='y'),
 'mixxx.crossfader':dict(label='Crossfader · A ↔ B',group='[Master]',key='crossfader',axis='x'),
}
for deck in (1,2):
 for band,param in [('low',1),('mid',2),('high',3)]:
  TARGETS[f'mixxx.deck{deck}.eq.{band}']=dict(label=f'Deck {"A" if deck==1 else "B"} {band} EQ',group=f'[EqualizerRack1_[Channel{deck}]_Effect1]',key=f'parameter{param}',axis='y')


def encode(packet):
 raw=json.dumps(packet,separators=(',',':'),ensure_ascii=True).encode('ascii')
 return PREFIX+list(raw)+[0xF7]


class MixxxBridge:
 def __init__(self,clock=time.monotonic):
  self.clock=clock;self.lock=threading.RLock();self.output=self.input=None
  self.session=secrets.token_hex(8);self.sequence=0;self.ack=0;self.values={};self.native={}
  self.received=-float('inf');self.last_hello=-float('inf');self.error=None

 def connect(self):
  with self.lock:
   if self.output:return self.status()
   import rtmidi
   output=rtmidi.MidiOut(name='DESK Spatial DJ');input_=rtmidi.MidiIn(name='DESK Spatial DJ')
   try:
    output.open_virtual_port('DESK Spatial DJ');input_.open_virtual_port('DESK Spatial DJ')
    input_.ignore_types(sysex=False,timing=True,active_sense=True);input_.set_callback(self._receive)
   except Exception:
    output.close_port();input_.close_port();raise
   self.output,self.input=output,input_;self._hello()
   return self.status()

 def _hello(self):
  if self.output and self.clock()-self.last_hello>=.5:
   self.last_hello=self.clock();self.output.send_message(encode(dict(type='hello',session=self.session)))

 def _receive(self,event,_):
  data=event[0]
  if list(data[:len(PREFIX)])!=PREFIX or len(data)>12000 or data[-1]!=0xF7:return
  try:
   p=json.loads(bytes(data[len(PREFIX):-1]).decode('ascii'))
   if p.get('type')!='state' or p.get('protocol')!=1 or p.get('session')!=self.session:return
   values=p['values']
   if not isinstance(values,dict) or any(k not in TARGETS or type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for k,v in values.items()):return
   if type(p.get('ack')) is not int or not 0<=p['ack']<=self.sequence:return
   with self.lock:
    self.values=values;self.native={k:v for k,v in p.get('native_values',{}).items() if k in TARGETS and type(v) in (int,float) and math.isfinite(v)}
    self.ack=p['ack'];self.error=str(p.get('error') or '')[:250] or None;self.received=self.clock()
  except (ValueError,KeyError,TypeError,UnicodeError):return

 def status(self):
  with self.lock:
   online=bool(self.output) and self.clock()-self.received<.8
   if self.output and not online:self._hello()
   return dict(connected=self.output is not None,online=online,port='DESK Spatial DJ',
    reason=self.error or ('Mixxx feedback connected' if online else 'Enable DESK Spatial DJ in Mixxx Preferences → Controllers' if self.output else 'Connect MIDI first'),
    values=dict(self.values),native_values=dict(self.native),ack=self.ack,sent_sequence=self.sequence,
    feedback_age_ms=round((self.clock()-self.received)*1000) if self.received>-float('inf') else None)

 def get_value(self,target):
  state=self.status()
  if not state['online'] or target not in state['values']:raise RuntimeError('Waiting for actual Mixxx fader feedback.')
  return state['values'][target]

 def set_value(self,target,value):
  if target not in TARGETS or type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=1:raise ValueError('Invalid Mixxx fader value.')
  with self.lock:
   if not self.status()['online']:raise RuntimeError('Mixxx feedback disconnected; no control was sent.')
   self.sequence+=1
   self.output.send_message(encode(dict(type='set',session=self.session,seq=self.sequence,target=target,value=round(value,6))))
   return self.sequence

 def close(self):
  with self.lock:
   if self.input:self.input.cancel_callback();self.input.close_port()
   if self.output:self.output.close_port()
   self.input=self.output=None;self.received=-float('inf')


_SHARED=None

def shared_bridge():
 global _SHARED
 if _SHARED is None:_SHARED=MixxxBridge()
 return _SHARED


class MixxxParameter:
 minimum=0.
 def __init__(self,target,bridge=None):self.target,self.bridge=target,bridge or shared_bridge()
 def get_value(self):return self.bridge.get_value(self.target)
 def set_value(self,value):self.bridge.set_value(self.target,value)
 def availability(self):
  s=self.bridge.status();return s['online'],None if s['online'] else s['reason']


class DJRuntime:
 """Independent faders, per-target pickup, bounded filtering and an input lease."""
 def __init__(self,snapshot,bridge=None,clock=time.monotonic):
  self.snapshot,self.bridge,self.clock=snapshot,bridge or shared_bridge(),clock
  self.lock=threading.RLock();self.mappings={};self.armed=False;self.last=0.;self.reason='DJ controls disarmed'

 def bind(self,oid,target,axis=None,reverse=False):
  if not isinstance(oid,str) or target not in TARGETS or axis not in (None,'x','y') or type(reverse) is not bool:raise ValueError('Choose an object, Mixxx target and axis.')
  sample=self.snapshot(oid)
  if not sample or not sample['tracked'] or self.clock()-sample['stamp']>.35:raise ValueError('Show the slider object clearly first.')
  with self.lock:
   self.mappings={t:m for t,m in self.mappings.items() if m['object_id']!=oid}
   self.mappings[target]=dict(object_id=oid,target=target,axis=axis or TARGETS[target]['axis'],reverse=reverse,
    low=.25,high=.75,picked_up=False,previous=None,filtered=None,frame=None,last_write=-float('inf'),state='Calibrate travel or move to pick up the actual Mixxx value')
   return self.status()

 @staticmethod
 def position(sample,m):return sample['position'][0] if m['axis']=='x' else 1-sample['position'][1]

 def calibrate(self,target,end):
  if end not in ('low','high'):raise ValueError('Choose a travel endpoint.')
  with self.lock:
   m=self.mappings.get(target)
   if not m:raise ValueError('Map an object first.')
   sample=self.snapshot(m['object_id'])
   if not sample or not sample['tracked'] or self.clock()-sample['stamp']>.35:raise ValueError('Show the object at the endpoint first.')
   m[end]=self.position(sample,m);m['picked_up']=False;m['previous']=m['filtered']=None
   return self.status()

 def arm(self,enabled):
  if type(enabled) is not bool:raise ValueError('Invalid DJ arm state.')
  with self.lock:
   if enabled and not self.bridge.status()['online']:raise RuntimeError('Connect MIDI and enable the DESK Spatial DJ mapping in Mixxx first.')
   self.armed=enabled;self.last=self.clock();self.reason='DJ controls armed · move each slider to pick up' if enabled else 'DJ controls stopped · Mixxx values held'
   for m in self.mappings.values():m['picked_up']=False;m['previous']=None
   return self.status()

 def update(self):
  with self.lock:
   now=self.clock();peer=self.bridge.status()
   if self.armed and (now-self.last>.7 or not peer['online']):self.armed=False;self.reason='Input or Mixxx connection interrupted · re-enable DJ controls'
   self.last=now
   for target,m in self.mappings.items():
    if not self.armed:continue
    sample=self.snapshot(m['object_id'])
    if not sample or not sample['tracked'] or now-sample['stamp']>.3:
     m['state']='Object hidden · Mixxx value held';m['picked_up']=False;m['previous']=m['filtered']=None;continue
    if sample['frame_id']==m['frame']:continue
    m['frame']=sample['frame_id'];span=m['high']-m['low']
    if abs(span)<.03:m['state']='Travel endpoints too close · recalibrate';continue
    raw=max(0.,min(1.,(self.position(sample,m)-m['low'])/span));raw=1-raw if m['reverse'] else raw
    dt=min(.15,max(.001,now-m.get('updated',now-.03)));m['updated']=now
    filtered=raw if m['filtered'] is None else m['filtered']+(1-math.exp(-dt/.045))*(raw-m['filtered']);m['filtered']=filtered
    actual=peer['values'].get(target)
    if actual is None:m['state']='Waiting for Mixxx feedback';continue
    previous=m['previous'];m['previous']=filtered;m['input']=round(filtered,4)
    # Other controllers/mouse changes also require pickup again.
    if m['picked_up'] and m.get('last_sent') is not None and self.bridge.ack>=m.get('sequence',0) and abs(actual-m['last_sent'])>.06:
     m['picked_up']=False
    if not m['picked_up']:
     crossed=previous is not None and (previous-actual)*(filtered-actual)<=0
     if abs(filtered-actual)<=.025 or crossed:m['picked_up']=True
     else:m['state']='Move slider to '+str(round(actual*100))+'% to pick up';continue
    if now-m['last_write']>=1/30 and abs(filtered-actual)>=.0015:
     proposed=actual+max(-dt*2.5,min(dt*2.5,filtered-actual))
     m['sequence']=self.bridge.set_value(target,proposed);m['last_sent']=proposed;m['last_write']=now
    m['state']='Controlling Mixxx'
   return self.status()

 def status(self):
  with self.lock:
   peer=self.bridge.status()
   if self.armed and (self.clock()-self.last>.7 or not peer['online']):
    self.armed=False;self.reason='Input or Mixxx connection interrupted · re-enable DJ controls'
    for m in self.mappings.values():m['picked_up']=False;m['previous']=None
   return dict(armed=self.armed,reason=self.reason,bridge=peer,targets=TARGETS,mappings={t:dict({k:(None if isinstance(v,float) and not math.isfinite(v) else v) for k,v in m.items()},label=TARGETS[t]['label'],actual=peer['values'].get(t)) for t,m in self.mappings.items()})

 def remove(self,target):
  with self.lock:self.mappings.pop(target,None)
  return self.status()
