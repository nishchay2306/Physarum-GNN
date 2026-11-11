"""Offline dynamic Guwahati routing lab: python app.py."""
import json
import threading
import time
import webbrowser
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from physrum.dynamic import GRAPH, DEFAULT_START, DEFAULT_END, DISPLAY_BOUNDS
from physrum.fleet import Fleet, DEPOTS, ZONES
from physrum.graph import RoadGraph

ROOT=Path(__file__).resolve().parent
HTML=(ROOT/'fleet.html').read_bytes()
SESSIONS={}
BACKGROUND=RoadGraph(bounds=DISPLAY_BOUNDS)

class Handler(BaseHTTPRequestHandler):
    def respond(self,value,status=200):
        data=json.dumps(value).encode('utf8')
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store')
        self.end_headers();self.wfile.write(data)
    def do_GET(self):
        if self.path=='/':
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length',str(len(HTML)));self.end_headers();self.wfile.write(HTML)
        elif self.path=='/api/map':
            self.respond({'nodes':GRAPH.nodes,'edges':BACKGROUND.edges,
                'background_nodes':BACKGROUND.nodes,
                'default_start':DEFAULT_START,'default_end':DEFAULT_END,
                'depots':DEPOTS,'zones':ZONES,
                'title':'Maligaon-Kamakhya · OSM-derived road close-up'})
        elif self.path.startswith('/api/state/'):
            session=SESSIONS.get(self.path.split('/')[-1])
            if session:self.respond(session.get())
            else:self.respond({'error':'Simulation not found'},404)
        else:self.respond({'error':'Not found'},404)
    def do_POST(self):
        if self.path!='/api/start':return self.respond({'error':'Not found'},404)
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<10000:raise ValueError('Invalid request size.')
            body=json.loads(self.rfile.read(size))
            session=Fleet(count=int(body.get('count',50)),
                          start=body.get('start',DEFAULT_START),
                          target=body.get('target',DEFAULT_END),
                          seed=int(body.get('seed',2306)))
            key=uuid.uuid4().hex
            SESSIONS[key]=session
            threading.Thread(target=session.run,daemon=True).start()
            self.respond({'session':key,'initial':session.initial,
                          'depots':session.depots,'zones':session.zones})
        except (ValueError,TypeError,KeyError,json.JSONDecodeError) as exc:
            self.respond({'error':str(exc)},400)

def main():
    # Pick an unused port so an old demo on 8765 cannot silently serve stale UI.
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    url=f'http://127.0.0.1:{server.server_port}'
    print(f'Guwahati dynamic routing lab: {url}',flush=True)
    print('Keep this window open; Ctrl+C to stop.',flush=True)
    threading.Timer(.8,lambda:webbrowser.open(url)).start()
    try:server.serve_forever()
    except KeyboardInterrupt:server.server_close()

if __name__=='__main__':main()
