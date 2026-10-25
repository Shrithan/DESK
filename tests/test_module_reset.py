import http.client
import json
from test_live import running_server, jpeg
from vision.demo import fixture


def test_module_reset_clears_observations_and_invalidates_pending_detection():
    with running_server() as server:
        top=server.sessions['top']
        top.receive(jpeg(fixture()[0]))
        top.select(top.frame_id,[80,70,160,150])
        assert top.objects
        oid=next(iter(top.objects))
        from vision.keyboard import KeyboardOutput
        events=[]
        class Backend:
            def event(self,*args):events.append(args)
        server.keyboard.close()
        server.keyboard=KeyboardOutput(backend_factory=Backend,trusted=lambda:True,visible=lambda oid:True,start_watchdog=False)
        token=server.keyboard.arm(oid,allowed_keys=['w'])['token']
        server.keyboard.update(token,['w'],0)
        assert events==[('w',True)]
        server.dj.bind(oid,'mixxx.deck1.volume','y')
        top.pending_objects=[{'old':'candidate'}]
        generation=top.generation
        server.agent_replies['old']='Old setup reply'
        connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
        connection.request('POST','/api/module/reset','{}',{'Content-Type':'application/json'})
        response=connection.getresponse()
        assert response.status==200
        assert json.loads(response.read())=={'status':'reset'}
        for role,session in server.sessions.items():
            assert session.objects=={} and session.frame is None and session.pending_objects==[]
            assert session.workspace_multi and session.overhead==(role=='top')
        assert top.generation>generation
        assert not server.keyboard.status()['armed']
        assert events==[('w',True),('w',False)]
        assert server.dj.status()['mappings']=={} and not server.dj.status()['armed']
        assert not server.object_buttons.assigned_ids() and not server.agent_replies
