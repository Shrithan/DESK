"""Discoverable desktop action adapters. Controllers never contain target-specific code."""
import ctypes as C
import math
import sys
from vision.keyboard import MacWASD, CODES


def fourcc(text):return int.from_bytes(text.encode('ascii'),'big')


class Property(C.Structure):
    _fields_=[('selector',C.c_uint32),('scope',C.c_uint32),('element',C.c_uint32)]


class DisplayBrightness:
    minimum=.08
    def __init__(self):
        self.cg=C.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
        self.ds=C.CDLL('/System/Library/PrivateFrameworks/DisplayServices.framework/DisplayServices')
        self.cg.CGGetActiveDisplayList.argtypes=[C.c_uint32,C.POINTER(C.c_uint32),C.POINTER(C.c_uint32)]
        self.cg.CGDisplayIsBuiltin.argtypes=[C.c_uint32];self.cg.CGDisplayIsBuiltin.restype=C.c_uint32
        ids=(C.c_uint32*16)();count=C.c_uint32()
        if self.cg.CGGetActiveDisplayList(16,ids,C.byref(count)):raise RuntimeError('Cannot enumerate displays.')
        self.display=next((int(i) for i in ids[:count.value] if self.cg.CGDisplayIsBuiltin(i)),None)
        if self.display is None:raise RuntimeError('No supported built-in display. External displays need a compatible adapter.')
        self.ds.DisplayServicesGetBrightness.argtypes=[C.c_uint32,C.POINTER(C.c_float)]
        self.ds.DisplayServicesGetBrightness.restype=C.c_int
        self.ds.DisplayServicesSetBrightness.argtypes=[C.c_uint32,C.c_float];self.ds.DisplayServicesSetBrightness.restype=C.c_int
        self.get_value()

    def get_value(self):
        value=C.c_float()
        if self.ds.DisplayServicesGetBrightness(self.display,C.byref(value)) or not math.isfinite(value.value):raise RuntimeError('Display brightness is unavailable.')
        return max(0.,min(1.,float(value.value)))

    def set_value(self,value):
        value=max(self.minimum,min(1.,value))
        if self.ds.DisplayServicesSetBrightness(self.display,value):raise RuntimeError('macOS could not set display brightness.')


class OutputVolume:
    minimum=0.
    def __init__(self):
        self.lib=C.CDLL('/System/Library/Frameworks/CoreAudio.framework/CoreAudio')
        self.lib.AudioObjectHasProperty.argtypes=[C.c_uint32,C.POINTER(Property)];self.lib.AudioObjectHasProperty.restype=C.c_bool
        self.lib.AudioObjectGetPropertyData.argtypes=[C.c_uint32,C.POINTER(Property),C.c_uint32,C.c_void_p,C.POINTER(C.c_uint32),C.c_void_p]
        self.lib.AudioObjectSetPropertyData.argtypes=[C.c_uint32,C.POINTER(Property),C.c_uint32,C.c_void_p,C.c_uint32,C.c_void_p]
        self.lib.AudioObjectIsPropertySettable.argtypes=[C.c_uint32,C.POINTER(Property),C.POINTER(C.c_bool)]
        self.device=self._read(1,Property(fourcc('dOut'),fourcc('glob'),0),C.c_uint32)
        self.channels=[]
        for channel in (0,1,2):
            prop=Property(fourcc('volm'),fourcc('outp'),channel);writable=C.c_bool()
            if self.lib.AudioObjectHasProperty(self.device,C.byref(prop)) and not self.lib.AudioObjectIsPropertySettable(self.device,C.byref(prop),C.byref(writable)) and writable.value:
                self.channels.append(channel)
                if channel==0:break
        if not self.channels:raise RuntimeError('The current audio output has no writable system volume control.')
        self.get_value()

    def _read(self,device,prop,kind):
        value=kind();size=C.c_uint32(C.sizeof(value))
        if self.lib.AudioObjectGetPropertyData(device,C.byref(prop),0,None,C.byref(size),C.byref(value)):raise RuntimeError('Cannot read the audio output setting.')
        return value.value

    def _check_device(self):
        if self._read(1,Property(fourcc('dOut'),fourcc('glob'),0),C.c_uint32)!=self.device:raise RuntimeError('Audio output changed. Remap to use the new device.')

    def get_value(self):
        self._check_device()
        values=[self._read(self.device,Property(fourcc('volm'),fourcc('outp'),ch),C.c_float) for ch in self.channels]
        if any(not math.isfinite(v) for v in values):raise RuntimeError('Invalid system volume.')
        return max(0.,min(1.,sum(values)/len(values)))

    def set_value(self,value):
        self._check_device()
        for ch in self.channels:
            prop=Property(fourcc('volm'),fourcc('outp'),ch);number=C.c_float(max(0.,min(1.,value)))
            if self.lib.AudioObjectSetPropertyData(self.device,C.byref(prop),0,None,C.sizeof(number),C.byref(number)):raise RuntimeError('macOS could not set output volume.')


class DesktopEvents(MacWASD):
    def __init__(self):
        super().__init__()
        # Variadic CoreGraphics function: explicitly type its three fixed arguments.
        self.lib.CGEventCreateScrollWheelEvent.argtypes=[C.c_void_p,C.c_uint32,C.c_uint32]
        self.lib.CGEventCreateScrollWheelEvent.restype=C.c_void_p

    def scroll(self,pixels):
        event=self.lib.CGEventCreateScrollWheelEvent(None,0,1,C.c_int32(int(pixels)))
        if not event:raise RuntimeError('macOS could not create a scroll event.')
        try:self.lib.CGEventPost(0,event)
        finally:self.lib.CFRelease(event)

    def press(self,key):
        try:self.event(key,True)
        finally:self.event(key,False)


class ActionRegistry:
    """Register an adapter once; all normalized sliders can drive its parameter."""
    def __init__(self):
        self.targets={}
        self.register('keyboard',dict(label='Keyboard keys',kind='keys',controllers=['joystick','slider_x','slider_y','cover_button'],keys=sorted(CODES)),None)
        self.register('desktop.scroll',dict(label='Scroll the application under the pointer',kind='relative',controllers=['slider_x','slider_y'],bindings=dict(negative='up',positive='down')),None)
        self._discover('display.brightness','Built-in display brightness',DisplayBrightness)
        self._discover('audio.volume','Current audio output volume',OutputVolume)
        from vision.mixxx import TARGETS, MixxxParameter
        for target,spec in TARGETS.items():
            self.register(target,dict(label='Mixxx · '+spec['label'],kind='continuous',controllers=['slider_x','slider_y'],bindings=dict(negative='decrease',positive='increase'),range=[0,1]),MixxxParameter(target))
        from vision.app_actions import installed_apps, OpenApplication
        for bundle,label,path in installed_apps():
            self.register('app.open.'+bundle,dict(label='Open '+label,kind='trigger',
                controllers=['cover_button'],bindings=dict(press='open'),app_name=label),OpenApplication(bundle,path))

    def register(self,identifier,spec,adapter,error=None):
        self.targets[identifier]=dict(spec,available=error is None,reason=error,adapter=adapter)

    def _discover(self,identifier,label,factory):
        spec=dict(label=label,kind='continuous',controllers=['slider_x','slider_y'],bindings=dict(negative='decrease',positive='increase'),range=[0,1])
        try:
            if sys.platform!='darwin':raise RuntimeError('This adapter requires macOS.')
            adapter=factory();spec['range']=[getattr(adapter,'minimum',0.),1.];self.register(identifier,spec,adapter)
        except (OSError,AttributeError,RuntimeError) as exc:self.register(identifier,spec,None,str(exc))

    def catalog(self):
        result={}
        for key,value in self.targets.items():
            spec={k:v for k,v in value.items() if k!='adapter'}
            if hasattr(value['adapter'],'availability'):spec['available'],spec['reason']=value['adapter'].availability()
            result[key]=spec
        return result

    def target(self,identifier):
        target=self.targets.get(identifier)
        if not target or not target['available']:raise ValueError('That action is not available on this computer.')
        return target
