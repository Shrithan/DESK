import http.client
import json
from test_live import running_server
from vision.keyboard import KeyboardOutput


def test_flight_http_reaches_key_backend_and_retains_assignment_on_gap():
    now=[100.];events=[]
    class Backend:
        def event(self,key,down,repeat=False):events.append((key,down))
    with running_server() as server:
        server.keyboard.close()
        server.keyboard=KeyboardOutput(backend_factory=Backend,trusted=lambda:True,clock=lambda:now[0],visible=lambda oid:True,start_watchdog=False)
        connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
        def post(path,body):
            connection.request('POST',path,json.dumps(body),{'Content-Type':'application/json'})
            response=connection.getresponse();data=json.loads(response.read())
            assert response.status==200,data
            return data
        armed=post('/api/keys/arm',dict(object_id='flight-can',allowed_keys=['w','s','a','d'],retain_mapping=True))
        token=armed['token']
        assert armed['armed']
        state=post('/api/keys/update',dict(token=token,keys=['w','a'],sequence=0))
        assert set(state['held'])=={'w','a'} and events==[('a',True),('w',True)]
        now[0]+=1;server.keyboard.tick()
        assert server.keyboard.token==token and not server.keyboard.held
        state=post('/api/keys/update',dict(token=token,keys=['s'],sequence=1))
        assert state['held']==['s'] and events[-1]==('s',True)
        post('/api/keys/stop',{})
        assert events[-1]==('s',False) and not server.keyboard.token
