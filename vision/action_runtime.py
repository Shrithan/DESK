"""Execute validated mappings through registered adapters with a short input lease."""
import math
import secrets
import threading
import time
from vision.cover import CoverButton, HandDetector
from vision.desktop_actions import ActionRegistry, DesktopEvents
from vision.keyboard import accessibility_trusted

SLIDER_GAIN = 3.0  # 10% of camera travel changes the parameter by 30 percentage points
PARAMETER_SLEW_PER_S = 1.3

class ActionRuntime:
    def __init__(self,snapshot,registry=None,events_factory=DesktopEvents,hand_factory=HandDetector,trusted=accessibility_trusted,clock=time.monotonic,start_watchdog=True):
        self.snapshot=snapshot;self.registry=registry or ActionRegistry();self.events_factory=events_factory;self.hand_factory=hand_factory
        self.trusted=trusted;self.clock=clock;self.lock=threading.RLock();self.token=None;self.mapping=None;self.events=None;self.hand=None
        self.reason='Disarmed';self.details={};self.last=0.;self.sequence=-1;self.last_frame=None;self.enabled=False
        self.stopping=threading.Event();self.thread=None
        if start_watchdog:
            self.thread=threading.Thread(target=self._watch,daemon=True,name='desktop-action-watchdog');self.thread.start()

    def status(self):
        with self.lock:return dict(armed=bool(self.token),mapping=self.mapping,reason=self.reason,details=self.details,region=list(self.cover.bbox) if self.mapping and self.mapping['controller']=='cover_button' else None,stale_timeout_ms=350)

    def arm(self,mapping):
        # The HTTP handler validates the full plan against a fresh server snapshot first.
        with self.lock:
            self.stop('Remapping')
            target=self.registry.target(mapping.get('output','keyboard'))
            if mapping['controller'] not in target['controllers']:raise ValueError('This controller cannot drive that target.')
            snapshot=self.snapshot(mapping['object_id'],mapping['controller']=='cover_button')
            if not snapshot or not snapshot['tracked'] or self.clock()-snapshot['stamp']>.35:raise ValueError('Show the target clearly before arming.')
            kind=target['kind']
            if kind=='keys' and mapping['controller']!='cover_button':raise ValueError('Use the keyboard controller for held keys.')
            if kind in ('keys','relative'):
                if not self.trusted():raise PermissionError('Enable macOS Accessibility for desktop keyboard/scroll controls.')
                self.events=self.events or self.events_factory()
            self.mapping=dict(mapping);self.target=target;self.last=self.clock();self.last_good_input=self.last;self.sequence=-1;self.last_frame=None
            self.origin=self._position(snapshot);self.filtered=self.origin;self.scroll_anchor=self.origin;self.updated=self.clock();self.last_write=-float('inf')
            if kind=='continuous':self.start_value=self.value=float(target['adapter'].get_value())
            if mapping['controller']=='cover_button':
                try:self.hand=self.hand_factory();self.cover=CoverButton(snapshot['frame'],snapshot['bbox'],self.clock(),immediate=True)
                except Exception:
                    self.stop('Cover detector could not start');raise
            self.token=secrets.token_urlsafe(24);self.reason='Armed · waiting for measured input';self.enabled=False
            return dict(token=self.token,**self.status())

    def _position(self,snapshot):
        axis=1 if self.mapping['controller']=='slider_y' else 0
        return snapshot['position'][axis]

    def update(self,token,sequence,enabled):
        if type(sequence) is not int or sequence<0 or type(enabled) is not bool:raise ValueError('Invalid action update.')
        with self.lock:
            if not self.token or not isinstance(token,str) or not secrets.compare_digest(self.token,token):raise PermissionError('Desktop control is disarmed or belongs to another session.')
            if sequence<=self.sequence:return self.status()
            self.sequence=sequence;now=self.clock();self.last=now
            cover=self.mapping['controller']=='cover_button'
            sample=self.snapshot(self.mapping['object_id'],cover)
            if not sample or now-sample['stamp']>.35:
                self.enabled=False
                self.reason='Camera briefly unavailable · output paused'
                if cover:self.cover.phase='missing';self.cover.since=None
                # Keep the mapping lease while dashboard heartbeats continue.
                # Missing measurements pause execution; only the watchdog/Stop disarms.
                return self.status()
            self.last_good_input=now
            if not enabled:
                self.enabled=False;self.last_frame=None;self.reason='Paused while dashboard controls have focus'
                if cover:self.cover.phase='missing';self.cover.since=None
                else:self.scroll_anchor=self.filtered=self._position(sample)
                return self.status()
            if sample['frame_id']==self.last_frame:return self.status()
            self.last_frame=sample['frame_id']
            if not cover and not sample['tracked']:
                self.enabled=False;self.reason='Tracking lost · output paused';return self.status()
            dt=min(.15,max(.001,now-self.updated));self.updated=now
            try:
                if cover:
                    hand_coverage=self.hand.coverage(sample['frame'],self.cover.bbox,now)
                    x,y,x2,y2=self.cover.bbox
                    object_coverage=max([max(0,min(x2,b[2])-max(x,b[0]))*max(0,min(y2,b[3])-max(y,b[1]))/max(1,(x2-x)*(y2-y)) for b in sample.get('occluders',[])]+[0.])
                    coverage=max(hand_coverage,object_coverage)
                    self.details=self.cover.step(sample['frame'],coverage,now)
                    self.details['evidence']='covered' if coverage>.55 and self.details['appearance_change']>.12 else 'tracking_lost' if not sample['tracked'] else 'clear'
                    self.details['value']=int(self.details['phase']=='pressed' and coverage>.3 and self.details['appearance_change']>.06)
                    if self.details['fire']:
                        if self.target['kind']=='trigger':self.target['adapter'].trigger()
                        else:self.events.press(self.mapping['bindings']['press'])
                    self.reason=self.target['label']+' · '+self.details['phase']
                else:
                    position=self._position(sample)
                    if not math.isfinite(position) or not 0<=position<=1:raise ValueError('Invalid measured slider position.')
                    if not self.enabled:
                        self.filtered=position  # reacquisition starts at the actual new anchor
                    self.filtered+= (1-math.exp(-dt/0.055))*(position-self.filtered)
                    if not self.enabled:
                        self.scroll_anchor=self.filtered
                        if self.target['kind']=='continuous':
                            self.origin=self.filtered
                            self.start_value=self.value=float(self.target['adapter'].get_value())
                    kind=self.target['kind']
                    if kind=='relative':
                        delta=self.filtered-self.scroll_anchor
                        if abs(delta)>max(.002,self.mapping['deadzone']*.025):
                            direction=self.mapping['bindings']['positive' if delta>0 else 'negative']
                            pixels=max(1,min(90,round(abs(delta)*2000)))
                            self.events.scroll(pixels if direction=='up' else -pixels);self.scroll_anchor=self.filtered
                        self.details=dict(position=round(position,3),mode='move to scroll; stationary means no scroll')
                    elif kind=='continuous':
                        sign=1 if self.mapping['bindings']['positive']=='increase' else -1
                        adapter=self.target['adapter'];minimum=getattr(adapter,'minimum',0.)
                        desired=max(minimum,min(1.,self.start_value+sign*(self.filtered-self.origin)*SLIDER_GAIN))
                        # Bound write frequency, change speed and jitter across all parameter adapters.
                        proposed=self.value+max(-dt*PARAMETER_SLEW_PER_S,min(dt*PARAMETER_SLEW_PER_S,desired-self.value))
                        if now-self.last_write>=.09 and abs(proposed-self.value)>=.004:
                            adapter.set_value(proposed);self.value=float(adapter.get_value());self.last_write=now
                        self.details=dict(position=round(position,3),value=round(self.value,3),target=self.mapping['output'],axis='Y (up/down)' if self.mapping['controller']=='slider_y' else 'X (left/right)')
                    self.reason='Active · '+self.target['label']
                self.enabled=True
            except Exception:
                self.stop('Action failed · stopped');raise
            return self.status()

    def stop(self,reason='Stopped'):
        with self.lock:
            self.token=None;self.mapping=None;self.reason=reason;self.details={};self.enabled=False
            if self.hand:
                self.hand.close();self.hand=None
            return self.status()

    def tick(self):
        with self.lock:
            if self.token and self.clock()-self.last>.35:
                if self.mapping['controller']=='cover_button' and self.target['kind']=='trigger':
                    # Opening an app can throttle the dashboard's timers. Retain the
                    # explicit assignment, but never carry a pending cover across a gap.
                    self.enabled=False;self.last_frame=None
                    self.cover.phase='missing';self.cover.since=None
                    self.details=dict(self.details,phase='missing',fire=False,value=0)
                    self.reason='Input stalled · button paused; uncover to resume'
                else:self.stop('Input stalled · output disarmed')

    def _watch(self):
        while not self.stopping.wait(.04):self.tick()

    def close(self):
        self.stopping.set();self.stop('Server stopped')
        if self.thread:self.thread.join(timeout=1)

class ActionGroup:
    """Independent leases for simultaneous manually mapped controls."""
    def __init__(self,snapshot,registry):
        self.snapshot,self.registry=snapshot,registry
        self.runtimes={};self.lock=threading.RLock()

    def arm(self,mapping):
        with self.lock:
            # Reuse an identical activation; independent mappings retain their leases.
            for token,runtime in list(self.runtimes.items()):
                if not runtime.token:
                    runtime.close();self.runtimes.pop(token)
                elif runtime.mapping==mapping:
                    return dict(token=token,**runtime.status())
            runtime=ActionRuntime(self.snapshot,registry=self.registry,start_watchdog=True)
            try:result=runtime.arm(mapping)
            except Exception:runtime.close();raise
            self.runtimes[result['token']]=runtime
            return result

    def update(self,token,sequence,enabled):
        with self.lock:runtime=self.runtimes.get(token)
        if not runtime:raise PermissionError('Control is no longer active.')
        return runtime.update(token,sequence,enabled)

    def stop(self,token=None):
        with self.lock:
            tokens=[token] if token else list(self.runtimes)
            for key in tokens:
                runtime=self.runtimes.pop(key,None)
                if runtime:runtime.close()
        return dict(armed=False,reason='Controls stopped')

    def close(self):self.stop()
