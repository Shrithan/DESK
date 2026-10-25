import plistlib
import subprocess
from types import SimpleNamespace
from vision.usb_guard import USBPhoneGuard, count_usb_iphones


def test_usb_inventory_counts_only_iphones_without_returning_identifiers():
    tree=[{'IORegistryEntryChildren':[{'USB Product Name':'iPhone','idVendor':1452,'IORegistryEntryID':7,'USB Serial Number':'private'}, {'USB Product Name':'C270','idVendor':1133}]}]
    calls=[]
    def run(*args,**kwargs):calls.append(args);return SimpleNamespace(stdout=plistlib.dumps(tree))
    guard=USBPhoneGuard(runner=run,system=lambda:'Darwin',clock=lambda:0)
    state=guard.status()
    assert state['verified'] and state['connected'] and state['phone_count']==1
    assert state['video_transport']=='unverified' and 'private' not in str(state)
    assert guard.status()==state and len(calls)==1


def test_unplug_invalid_inventory_and_multiple_phones_fail_closed():
    clock=[0]
    tree=[{'USB Product Name':'iPhone','IORegistryEntryID':7}]
    def run(*args,**kwargs):return SimpleNamespace(stdout=plistlib.dumps(tree))
    guard=USBPhoneGuard(runner=run,system=lambda:'Darwin',clock=lambda:clock[0])
    assert guard.status()['connected']
    tree.clear();clock[0]=2
    assert not guard.status()['connected']
    tree.extend([{'USB Product Name':'iPhone','IORegistryEntryID':7},{'USB Product Name':'iPhone','IORegistryEntryID':8}]);clock[0]=4
    assert not guard.status()['connected']
    guard.runner=lambda *a,**k:SimpleNamespace(stdout=b'not a plist');clock[0]=6
    assert not guard.status()['verified']
    guard.system=lambda:'Linux';clock[0]=8
    assert not guard.status()['connected']


def test_inventory_failure_does_not_allow_phone():
    def run(*a,**k):raise subprocess.TimeoutExpired('ioreg',2)
    guard=USBPhoneGuard(runner=run,system=lambda:'Darwin')
    assert not guard.status()['connected']
