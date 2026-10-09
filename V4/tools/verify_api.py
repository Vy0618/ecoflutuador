"""Local HTTP integration check with synthetic camera/serial; always shuts down."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'poc_raspberry'))
import json
import time
from urllib.request import urlopen
from main import Pipeline

p=Pipeline({'api':{'host':'127.0.0.1','port':0},'recognition':{'confirmation_s':0}},'mock')
try:
    assert p.setup()
    assert p._status_server is not None, "Local sockets unavailable"
    base='http://127.0.0.1:'+str(p._status_server._server.server_port)
    p._on_serial_response('EVENT:START:1')
    for _ in range(8):
        time.sleep(.11)
        frame=p._camera.get_frame()
        if frame is not None:
            state=p._process_frame(frame)
            p._status_server.update_state(state)
            p._status_server.update_runtime(p.runtime_status())
    for route in ('/','/health','/status','/telemetry','/history','/diagnostics'):
        with urlopen(base+route,timeout=2) as response:
            body=response.read()
            assert response.status==200
            if route!='/':json.loads(body)
            print(json.dumps({'route':route,'status':response.status,'bytes':len(body)}))
    assert any(c!='s' for c in p._serial.sent_commands)
finally:
    p.shutdown()
assert p._serial.get_last_sent()=='s'
print('HTTP integration and graceful STOP passed; no hardware')
