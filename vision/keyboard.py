"""Local WASD output with explicit arming, ownership, stale-input release and cleanup."""
import ctypes
import secrets
import sys
import threading
import time

CODES=dict(zip('abcdefghijklmnopqrstuvwxyz',[0,11,8,2,14,3,5,4,34,38,40,37,46,45,31,35,12,15,1,17,32,9,13,7,16,6]))
CODES.update(dict(zip('0123456789',[29,18,19,20,21,23,22,26,28,25])))
CODES.update(up=126,down=125,left=123,right=124,space=49,enter=36,tab=48,escape=53)


def accessibility_trusted():
    if sys.platform!='darwin':return False
    try:
        lib=ctypes.CDLL('/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices')
        lib.AXIsProcessTrusted.restype=ctypes.c_bool
        return bool(lib.AXIsProcessTrusted())
    except (OSError,AttributeError):return False


def request_accessibility_permission():
    """Show the standard macOS prompt; only the user can grant access in Settings."""
    if sys.platform!='darwin':return False
    app=ctypes.CDLL('/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices')
    cf=ctypes.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
    cf.CFDictionaryCreateMutable.argtypes=[ctypes.c_void_p,ctypes.c_long,ctypes.c_void_p,ctypes.c_void_p]
    cf.CFDictionaryCreateMutable.restype=ctypes.c_void_p
    cf.CFDictionarySetValue.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p]
    cf.CFRelease.argtypes=[ctypes.c_void_p]
    app.AXIsProcessTrustedWithOptions.argtypes=[ctypes.c_void_p]
    app.AXIsProcessTrustedWithOptions.restype=ctypes.c_bool
    options=cf.CFDictionaryCreateMutable(None,0,None,None)
    try:
        key=ctypes.c_void_p.in_dll(app,'kAXTrustedCheckOptionPrompt')
        yes=ctypes.c_void_p.in_dll(cf,'kCFBooleanTrue')
        cf.CFDictionarySetValue(options,key,yes)
        return bool(app.AXIsProcessTrustedWithOptions(options))
    finally:cf.CFRelease(options)


class MacWASD:
    def __init__(self):
        if sys.platform!='darwin':raise RuntimeError('Real WASD output currently supports macOS.')
        self.lib=ctypes.CDLL('/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices')
        self.lib.CGEventCreateKeyboardEvent.argtypes=[ctypes.c_void_p,ctypes.c_uint16,ctypes.c_bool]
        self.lib.CGEventCreateKeyboardEvent.restype=ctypes.c_void_p
        self.lib.CGEventPost.argtypes=[ctypes.c_uint32,ctypes.c_void_p]
        self.lib.CGEventSetIntegerValueField.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int64]
        self.lib.CFRelease.argtypes=[ctypes.c_void_p]

    def event(self,key,down,repeat=False):
        event=self.lib.CGEventCreateKeyboardEvent(None,CODES[key],down)
        if not event:raise RuntimeError('macOS could not create a key event.')
        try:
            if repeat:self.lib.CGEventSetIntegerValueField(event,8,1)
            self.lib.CGEventPost(0,event)
        finally:self.lib.CFRelease(event)


class KeyboardOutput:
    def __init__(self,backend_factory=MacWASD,trusted=accessibility_trusted,clock=time.monotonic,visible=lambda oid:True,start_watchdog=True):
        self.factory,self.trusted,self.clock,self.visible=backend_factory,trusted,clock,visible
        self.backend=None;self.lock=threading.RLock();self.held=set();self.token=None;self.object_id=None
        self.last=0.;self.repeat_at=0.;self.sequence=-1;self.mode='game';self.reason='Disarmed'
        self.stopping=threading.Event();self.thread=None
        if start_watchdog:
            self.thread=threading.Thread(target=self._watch,name='wasd-release-watchdog',daemon=True);self.thread.start()

    def status(self):
        with self.lock:return dict(armed=bool(self.token),held=sorted(self.held),object_id=self.object_id,mode=self.mode,
                                  accessibility=self.trusted(),reason=self.reason,stale_timeout_ms=350)

    def arm(self,oid,mode='game',allowed_keys=None,retain_mapping=False):
        if type(retain_mapping) is not bool:raise ValueError('Invalid keyboard retention setting.')
        allowed_keys=['w','a','s','d'] if allowed_keys is None else allowed_keys
        if not isinstance(allowed_keys,list) or not 1<=len(allowed_keys)<=4 or any(k not in CODES for k in allowed_keys):raise ValueError('Choose supported keyboard bindings.')
        if not isinstance(oid,str) or not oid or len(oid)>200:raise ValueError('Select a tracked joystick first.')
        if mode not in ('game','typing'):raise ValueError('Choose game or typing mode.')
        with self.lock:
            self._disarm('Remapping')
            if not self.trusted():raise PermissionError('Enable macOS Accessibility for the app running this server, then retry Arm real WASD.')
            if not self.visible(oid):raise ValueError('The selected object is not currently tracked.')
            self.backend=self.backend or self.factory();self.object_id=oid;self.mode=mode
            self.retain_mapping=retain_mapping;self.allowed_keys=set(allowed_keys);self.token=secrets.token_urlsafe(24);self.last=self.clock();self.sequence=-1;self.reason='Armed · sends to focused app'
            return dict(token=self.token,**self.status())

    def update(self,token,keys,sequence):
        if not isinstance(keys,list) or len(keys)>2 or any(k not in getattr(self,'allowed_keys',set('wasd')) for k in keys) or len(set(keys))!=len(keys):raise ValueError('Only this controller’s configured keys are accepted.')
        if {'w','s'}<=set(keys) or {'a','d'}<=set(keys):raise ValueError('Opposing directions cannot be held together.')
        if type(sequence) is not int or sequence<0:raise ValueError('Invalid key sequence')
        with self.lock:
            if not self.token or not isinstance(token,str) or not secrets.compare_digest(token,self.token):raise PermissionError('Keyboard output is disarmed or owned by another session.')
            if sequence<=self.sequence:return self.status()
            self.sequence=sequence;self.last=self.clock()
            if not self.visible(self.object_id):self._set(set());self.reason='Waiting for tracked object';return self.status()
            self._set(set(keys));self.reason='Armed · sends to focused app';return self.status()

    def test_taps(self):
        with self.lock:
            self._disarm('Local keyboard test')
            if not self.trusted():raise PermissionError('Enable macOS Accessibility before testing real WASD.')
            self.backend=self.backend or self.factory()
            try:
                for key in 'wasd':
                    self.held.add(key)
                    self.backend.event(key,True)
                    self.backend.event(key,False)
                    self.held.discard(key)
                    time.sleep(.05)
            finally:self._disarm('Local keyboard test finished')
            return self.status()

    def _set(self,keys):
        try:
            for key in sorted(self.held-keys):self.backend.event(key,False);self.held.remove(key)
            for key in sorted(keys-self.held):self.backend.event(key,True);self.held.add(key);self.repeat_at=self.clock()+.4
        except Exception:
            self._disarm('Key output failed');raise

    def _disarm(self,reason):
        self.token=None
        for key in list(self.held):
            try:self.backend.event(key,False)
            except Exception:pass
        self.held.clear();self.object_id=None;self.reason=reason

    def disarm(self,reason='Disarmed'):
        with self.lock:self._disarm(reason);return self.status()

    def tick(self):
        with self.lock:
            if not self.token:return
            if self.clock()-self.last>.35:
                if getattr(self,'retain_mapping',False):
                    self._set(set());self.reason='Input stalled · keys released; mapping retained'
                else:self._disarm('Input stalled · re-arm to resume')
                return
            if not self.visible(self.object_id):self._set(set());self.reason='Tracking lost · keys released';return
            if self.mode=='typing' and self.held and self.clock()>=self.repeat_at:
                for key in sorted(self.held):self.backend.event(key,True,True)
                self.repeat_at=self.clock()+.1

    def _watch(self):
        while not self.stopping.wait(.04):
            try:self.tick()
            except Exception:self.disarm('Keyboard output error')

    def close(self):
        self.stopping.set();self.disarm('Server stopped')
        if self.thread and self.thread is not threading.current_thread():self.thread.join(timeout=1)
