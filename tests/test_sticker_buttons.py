"""A registered cover target is a fixed input area, not a textured moving track."""
import cv2
import numpy as np
from vision.live import LiveSession,LiveServer
from vision.cover import CoverButton


def jpeg(frame):return cv2.imencode('.jpg',frame)[1].tobytes()


def test_textureless_sticker_keeps_fixed_id_and_box_when_covered(monkeypatch):
    clock=[100.];monkeypatch.setattr('vision.live.time.monotonic',lambda:clock[0])
    class NoObjects:
        def detect(self,frame):return []
    s=LiveSession('top',NoObjects());s.overhead=s.workspace_multi=True
    clear=np.full((240,320,3),150,np.uint8);s.receive(jpeg(clear))
    mask=np.zeros((240,320),np.uint8);mask[80:120,100:140]=1
    obs=s._add_object(mask,'sticker','cover_region');oid=obs['object_id']
    assert len(s.tracker.targets['top',oid].points)==0
    covered=clear.copy();covered[60:140,80:160]=30
    for frame in [clear]*5+[covered]*15+[clear]*5:
        clock[0]+=.2;r=s.receive(jpeg(frame))
        o=next(item for item in r['objects'] if item['observation']['object_id']==oid)
        assert o['observation']['tracking_state']=='tracked'
        assert o['observation']['bbox_xyxy']==[100,80,140,120]
        assert o['observation']['tracking_basis']=='fixed_registered_region'
    assert list(s.objects)==[oid]


def test_sticker_region_does_not_fire_without_hand_or_repeat_when_held():
    clear=np.full((240,320,3),150,np.uint8);covered=clear.copy();covered[80:120,100:140]=30
    b=CoverButton(clear,[100,80,140,120],0.)
    now=0.;fires=0
    for frame,hand,count in [(clear,0.,6),(covered,0.,8),(clear,0.,6),(covered,.9,15),(clear,0.,6),(covered,.9,5)]:
        for _ in range(count):now+=.1;fires+=b.step(frame,hand,now)['fire']
    assert fires==2


def test_fixed_buttons_only_advertise_cover_input(monkeypatch):
    from vision.cover import HandDetector
    monkeypatch.setattr(HandDetector,'available',staticmethod(lambda:True))
    s=LiveSession('top');s.overhead=True;s.receive(jpeg(np.full((240,320,3),100,np.uint8)))
    mask=np.zeros((240,320),np.uint8);mask[80:120,100:140]=1
    s._add_object(mask,'sticker','cover_region')
    server=object.__new__(LiveServer);server.sessions={'top':s}
    items=server.mapping_objects()
    assert items[0]['controllers']==['cover_button']


def test_http_registration_reports_id_and_rejects_bad_button_edges():
    import http.client,json,threading
    server=LiveServer(('127.0.0.1',0));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    connection=http.client.HTTPConnection('127.0.0.1',server.server_port)
    def post(path,data,mime='application/json'):
        connection.request('POST',path,json.dumps(data) if mime=='application/json' else data,{'Content-Type':mime,'X-Camera-Id':'top'})
        r=connection.getresponse();return r.status,json.loads(r.read())
    try:
        frame=np.full((240,320,3),150,np.uint8)
        assert post('/api/workspace-multi',{})[0]==200
        assert post('/api/frame',jpeg(frame),'image/jpeg')[0]==200
        status,result=post('/api/register-region',dict(stationary=True,bbox=[.3,.3,.5,.5]))
        assert status==200
        oid=result['registered_object_id']
        assert server.sessions['top'].objects[oid]['source']=='cover_region'
        status,result=post('/api/register-region',dict(stationary=True,bbox=[0.,0.,.2,.2]))
        assert status==400
        assert list(server.sessions['top'].objects)==[oid]
        frame[72:120,96:160]=30
        _,result=post('/api/frame',jpeg(frame),'image/jpeg')
        assert result['objects'][0]['observation']['object_id']==oid
        assert result['objects'][0]['observation']['tracking_basis']=='fixed_registered_region'
    finally:
        connection.close();server.shutdown();server.server_close();thread.join(2)
