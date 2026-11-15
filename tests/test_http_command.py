"""Real TCP server in this process, AwaitLab CLI in a separate process."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from urllib.parse import parse_qs,urlsplit


@unittest.skipUnless(importlib.util.find_spec('httpx'),'optional httpx dependency')
class HTTPCommandTests(unittest.TestCase):
    def setUp(self):
        root=Path('D:/CodexWork/temp/awaitlab');root.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=root);self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name);self.calls=[];calls=self.calls
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                parsed=urlsplit(self.path);i=int(parse_qs(parsed.query).get('id',['0'])[0]);calls.append((parsed.path,i))
                if parsed.path=='/slow':time.sleep(.3)
                status=500 if parsed.path=='/error' else 201 if parsed.path=='/created' else 200
                body=b'private response text' if parsed.path=='/text' else json.dumps({'id':i+int(parsed.path=='/wrong'),'value':i*2}).encode()
                try:
                    self.send_response(status);self.send_header('Content-Length',str(len(body)));self.end_headers()
                    if parsed.path=='/trickle':
                        for value in body:
                            self.wfile.write(bytes([value]));self.wfile.flush();time.sleep(.025)
                    else:self.wfile.write(body)
                except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=lambda:self.server.serve_forever(poll_interval=.02),daemon=True);self.thread.start()
        self.addCleanup(self.close_server)
        self.origin=f'http://127.0.0.1:{self.server.server_port}'

    def close_server(self):
        self.server.shutdown();self.server.server_close();self.thread.join()

    def cli(self,after='/after',*extra,version='fixture-v1',before=None):
        env={**os.environ,'PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1',
            'PYTHONPATH':str(Path(__file__).resolve().parents[1]),'TEMP':str(self.folder),'TMP':str(self.folder)}
        return subprocess.run([sys.executable,'-m','awaitlab','http',
            '--before',before or self.origin+'/before?id={id}&token=private-query-marker',
            '--after',self.origin+after+'?id={id}','--workload-version',version,
            '--blocks','2','--requests','3','--concurrency','2','--first-id','10',
            '--output',str(self.folder/'result.json'),*extra],cwd=self.folder,env=env,
            capture_output=True,encoding='utf-8',timeout=20)

    def test_plan_performs_no_requests_or_output_writes(self):
        result=self.cli('/after','--plan');self.assertEqual(result.returncode,0,result.stderr)
        plan=json.loads(result.stdout)
        self.assertFalse(plan['workload_executed']);self.assertEqual(self.calls,[])
        self.assertEqual(plan['replacement_roles']['http_control'],'negative_control')
        self.assertEqual(plan['http_request']['first_id'],10)
        self.assertNotIn('private-query-marker',result.stdout)
        self.assertFalse((self.folder/'result.json').exists())

    def test_existing_services_compare_and_resume_without_new_requests(self):
        result=self.cli();self.assertEqual(result.returncode,0,result.stderr)
        target=self.folder/'result.json';report=json.loads(target.read_text(encoding='utf-8'))
        self.assertTrue(all(c['output_equivalence'] for c in report['comparisons']))
        self.assertEqual(len(self.calls),8*(3+4))
        self.assertEqual({i for _,i in self.calls},{10,11,12})
        self.assertEqual(sum(path=='/after' for path,_ in self.calls),2*(3+4))
        self.assertFalse(report['comparisons'][1]['candidate_improvement'])
        self.assertEqual(report['comparisons'][1]['role'],'negative_control')
        self.assertNotIn('timer_calibration',report)
        self.assertNotIn('private-query-marker',target.read_text(encoding='utf-8'))
        self.assertIn('完整JSON',target.with_suffix('.html').read_text(encoding='utf-8'))
        resume=self.cli('/after','--resume');self.assertEqual(resume.returncode,0,resume.stderr)
        restored=json.loads(target.read_text(encoding='utf-8'))
        self.assertEqual(restored['run']['resumed_pairs'],4);self.assertEqual(len(self.calls),56)
        self.assertEqual(restored['comparisons'],report['comparisons'])
        changed=self.cli('/after','--resume',version='fixture-v2')
        self.assertEqual(changed.returncode,1);self.assertIn('Checkpoint identity differs',changed.stderr)
        self.assertEqual(len(self.calls),56)

    def test_changed_json_is_not_treated_as_equivalent(self):
        result=self.cli('/wrong');self.assertEqual(result.returncode,0,result.stderr)
        c=json.loads((self.folder/'result.json').read_text(encoding='utf-8'))['comparisons'][0]
        self.assertFalse(c['output_equivalence']);self.assertEqual(c['evidence_level'],'invalid_output')
        self.assertTrue(all(b['output_mismatch_ids']==[0,1,2] for b in c['blocks']))

    def test_status_is_part_of_output_even_when_both_are_successful(self):
        result=self.cli('/created');self.assertEqual(result.returncode,0,result.stderr)
        c=json.loads((self.folder/'result.json').read_text(encoding='utf-8'))['comparisons'][0]
        self.assertFalse(c['output_equivalence'])

    def test_bad_status_and_non_json_reject_without_overwriting_old_report(self):
        target=self.folder/'result.json';target.write_text('old complete JSON',encoding='utf-8')
        target.with_suffix('.html').write_text('old complete HTML',encoding='utf-8')
        for route,message in [('/error','status 500'),('/text','not JSON')]:
            result=self.cli(route)
            self.assertEqual(result.returncode,1);self.assertIn(message,result.stderr)
            self.assertNotIn('Traceback',result.stderr);self.assertNotIn('private response text',result.stderr)
            self.assertNotIn('private-query-marker',result.stderr)
            self.assertEqual(target.read_text(),'old complete JSON')
            self.assertEqual(target.with_suffix('.html').read_text(),'old complete HTML')

    def test_invalid_url_and_timeout_fail_before_any_requests(self):
        for before,extra in [('file:///private',()),(self.origin+'/{unknown}',()),
                ('http://user:password@127.0.0.1/',()),(self.origin,('--timeout','nan'))]:
            result=self.cli('/after','--plan',*extra,before=before)
            self.assertNotEqual(result.returncode,0)
        empty_version=self.cli('/after','--plan',version=' ')
        self.assertNotEqual(empty_version.returncode,0);self.assertIn('nonempty workload version',empty_version.stderr)
        self.assertEqual(self.calls,[])

    def test_read_timeout_is_reported_without_traceback_or_url_secrets(self):
        result=self.cli('/slow','--timeout','.05')
        self.assertEqual(result.returncode,1);self.assertIn('Timeout',result.stderr)
        self.assertNotIn('Traceback',result.stderr);self.assertNotIn('private-query-marker',result.stderr)
        self.assertFalse((self.folder/'result.json').exists())

    def test_body_limit_rejects_oversized_responses(self):
        result=self.cli('/after','--max-response-bytes','8')
        self.assertEqual(result.returncode,1);self.assertIn('exceeds 8 bytes',result.stderr)
        self.assertFalse((self.folder/'result.json').exists())

    def test_total_receive_deadline_also_stops_a_trickling_response(self):
        result=self.cli('/trickle','--timeout','.3')
        self.assertEqual(result.returncode,1);self.assertIn('(TimeoutError)',result.stderr)
        self.assertFalse((self.folder/'result.json').exists())


if __name__=='__main__':unittest.main()
