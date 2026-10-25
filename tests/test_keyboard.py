import pytest
from vision.keyboard import KeyboardOutput


class Backend:
    def __init__(self):self.events=[]
    def event(self,key,down,repeat=False):self.events.append((key,down,repeat))


def controller():
    clock=[100.];visible=[True];backend=Backend()
    output=KeyboardOutput(backend_factory=lambda:backend,trusted=lambda:True,clock=lambda:clock[0],visible=lambda oid:visible[0],start_watchdog=False)
    return output,backend,clock,visible


def test_held_keys_edges_release_first_and_stop():
    o,b,c,v=controller();token=o.arm('can')['token']
    o.update(token,['w'],0);o.update(token,['w'],1);assert len(b.events)==1
    o.update(token,['s','d'],2)
    assert b.events[1]==('w',False,False) and b.events[2:]==[('d',True,False),('s',True,False)]
    o.disarm();assert not o.held and not o.status()['armed']
    assert b.events[-1][1] is False


def test_watchdog_tracking_and_out_of_order_updates():
    o,b,c,v=controller();token=o.arm('can')['token'];o.update(token,['w'],2)
    o.update(token,['s'],1);assert o.held=={'w'}
    v[0]=False;o.tick();assert not o.held
    v[0]=True;o.update(token,['a'],3);c[0]+=.351;o.tick()
    assert not o.status()['armed'] and not o.held
    with pytest.raises(PermissionError):o.update(token,['d'],4)


def test_permission_validation_and_typing_repeat():
    o,b,c,v=controller();o.trusted=lambda:False
    with pytest.raises(PermissionError):o.arm('can')
    o.trusted=lambda:True;token=o.arm('can','typing')['token'];o.update(token,['w'],0)
    c[0]+=.3;o.update(token,['w'],1);c[0]+=.11;o.tick();assert b.events[-1]==('w',True,True)
    for keys in [['x'],['w','s'],['a','d'],['w','a','s'],['w','w']]:
        with pytest.raises(ValueError):o.update(token,keys,2)
    with pytest.raises(PermissionError):o.update('different-owner',['w'],3)
    o.close();assert not o.held


def test_local_taps_are_fixed_wasd_and_finish_disarmed():
    o,b,c,v=controller();o.test_taps()
    assert b.events==[(k,down,False) for k in 'wasd' for down in (True,False)]
    assert not o.status()['armed'] and not o.held


def test_flight_retains_explicit_mapping_but_releases_keys_across_focus_handoff():
    o,b,c,v=controller()
    token=o.arm('can',retain_mapping=True)['token']
    o.update(token,['w'],0)
    c[0]+=1;o.tick()
    assert o.token==token and not o.held and b.events[-1]==('w',False,False)
    assert 'mapping retained' in o.status()['reason']
    v[0]=False;o.update(token,['a'],1)
    assert not o.held
    v[0]=True;o.update(token,['a'],2)
    assert o.held=={'a'} and b.events[-1]==('a',True,False)
    o.disarm();assert o.token is None and not o.held
    o.close()
