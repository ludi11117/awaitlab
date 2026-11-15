"""Standalone SQLite HTTP example. Keep this terminal open; Enter stops it."""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import socket
import sys
import threading
from urllib.parse import parse_qs,urlsplit

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from awaitlab.experiment import fingerprint
from awaitlab import sqlite_workload as database


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args();fixture=database.prepare_fixture();counts={'before':0,'after':0};lock=threading.Lock()
    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def log_message(self,*args):pass
        def setup(self):
            super().setup();self.request.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
        def do_GET(self):
            parsed=urlsplit(self.path);name=parsed.path.strip('/')
            if name not in counts:self.send_error(404);return
            try:i=int(parse_qs(parsed.query).get('id',['0'])[0])
            except ValueError:self.send_error(400);return
            with lock:counts[name]+=1
            path=fixture['paths']['unindexed' if name=='before' else 'indexed']
            body=json.dumps(database.read_customer(path,database.request_key(i,database.DEFAULT_ROWS)),separators=(',',':')).encode()
            try:
                self.send_response(200);self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    identity=fingerprint({'fixture':fixture['manifest'],'server_source':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'database_source':hashlib.sha256(Path(database.__file__).read_bytes()).hexdigest(),
        'python':sys.version,'sqlite':fixture['sqlite_version']})
    print(json.dumps({'origin':f'http://127.0.0.1:{server.server_port}','workload_version':identity}),flush=True)
    print('Press Enter in this terminal to stop the example service.',file=sys.stderr,flush=True)
    try:sys.stdin.readline()
    except KeyboardInterrupt:pass
    finally:
        server.shutdown();server.server_close();thread.join()
        print(json.dumps({'requests':counts}),flush=True)


if __name__=='__main__':main()
