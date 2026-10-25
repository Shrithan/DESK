"""USB presence guard. This cannot inspect or force Continuity's video transport."""
import platform
import plistlib
import subprocess
import threading
import time


def count_usb_iphones(tree):
    ids=set()
    def walk(nodes):
        if isinstance(nodes,list):
            for node in nodes:walk(node)
        elif isinstance(nodes,dict):
            name=str(nodes.get('USB Product Name') or nodes.get('kUSBProductString') or nodes.get('IORegistryEntryName',''))
            if 'iphone' in name.lower() and nodes.get('idVendor',1452)==1452:
                # Registry entry IDs are used only for deduplication; never returned.
                ids.add(nodes.get('IORegistryEntryID',id(nodes)))
            walk(nodes.get('IORegistryEntryChildren',[]))
    walk(tree)
    return len(ids)


class USBPhoneGuard:
    def __init__(self, runner=subprocess.run, system=platform.system, clock=time.monotonic):
        self.runner,self.system,self.clock=runner,system,clock
        self.lock=threading.Lock();self.cached=None;self.checked=-float('inf')

    def status(self):
        with self.lock:
            if self.cached is not None and self.clock()-self.checked<1:
                return self.cached
            result=dict(required=True,verified=False,connected=False,phone_count=0,
                        video_transport='unverified',method='macOS USB device inventory')
            if self.system()!='Darwin':
                result['message']='USB iPhone verification is supported on this Mac only.'
            else:
                try:
                    response=self.runner(['/usr/sbin/ioreg','-p','IOUSB','-a','-l'],capture_output=True,timeout=2,check=True)
                    count=count_usb_iphones(plistlib.loads(response.stdout))
                    result.update(verified=True,connected=count==1,phone_count=count)
                    result['message']='USB iPhone detected; Continuity transport is controlled by macOS.' if count==1 else ('Connect exactly one iPhone by USB to avoid selecting a different wireless phone.' if count>1 else 'No USB iPhone detected. Plug in a data cable, unlock the phone and tap Trust.')
                except (OSError,subprocess.SubprocessError,ValueError,plistlib.InvalidFileException):
                    result['message']='Cannot verify the USB connection. iPhone camera is blocked until verification works.'
            self.checked=self.clock();self.cached=result
            return result
