"""Exercise the URL command against a separate real SQLite HTTP process."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from awaitlab import __version__
from awaitlab.sqlite_workload import prepare_fixture


def main():
    temp=Path('D:/CodexWork/temp/awaitlab');temp.mkdir(parents=True,exist_ok=True)
    env={**os.environ,'PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1','TEMP':str(temp),'TMP':str(temp)}
    target=ROOT/f'artifacts/external-http-v{__version__}.json'
    with (temp/f'http-service-v{__version__}.log').open('w',encoding='utf-8') as log:
        server=subprocess.Popen([sys.executable,str(ROOT/'examples/http_service.py'),'--port','0'],cwd=ROOT,env=env,
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,encoding='utf-8',bufsize=1)
        try:
            ready=json.loads(server.stdout.readline());origin=ready['origin']
            command=[sys.executable,'-m','awaitlab','http','--before',origin+'/before?id={id}',
                '--after',origin+'/after?id={id}','--workload-version',ready['workload_version'],
                '--blocks','10','--requests','12','--concurrency','4','--output',str(target)]
            plan=subprocess.run(command+['--plan'],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',check=True)
            preview=json.loads(plan.stdout);assert preview['workload_executed'] is False
            first=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',check=True)
            before=json.loads(target.read_text(encoding='utf-8'))
            resumed=subprocess.run(command+['--resume'],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',check=True)
            after=json.loads(target.read_text(encoding='utf-8'))
            assert before['comparisons']==after['comparisons'] and after['run']['resumed_pairs']==20
            assert all(c['output_equivalence'] for c in after['comparisons'])
            assert after['http_request']==preview['http_request']
            assert not after['comparisons'][1]['candidate_improvement']
            (temp/f'http-command-v{__version__}.log').write_text(first.stdout+first.stderr+resumed.stdout+resumed.stderr,encoding='utf-8')
        finally:
            if server.poll() is None:server.stdin.write('\n');server.stdin.flush()
            summary=server.stdout.readline();server.wait(timeout=15)
            server.stdin.close();server.stdout.close()
    counts=json.loads(summary)['requests']
    assert counts=={'before':480,'after':160},counts
    fixture=prepare_fixture()
    record={'version':__version__,'report':str(target),'independent_server_process':True,
        'requests':counts,'expected_measurement_and_warmup_requests':640,'plan_and_resume_added_no_requests':True,
        'resumed_pairs':20,'comparisons_unchanged':True,'all_outputs_equal':True,
        'request_spec':after['http_request'],'quality':after['quality'],'fixture':fixture['manifest'],
        'limits':['server stays alive across blocks; its caches are not reset',
            'SQLite uses short read-only connections; persistent service threads differ from managed per-block executors',
            'no server-internal trace or general internet latency claim']}
    (ROOT/f'artifacts/http-command-check-v{__version__}.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    print('External HTTP command: 640 real SQLite requests; plan/resume sent no extra requests; 20 pairs restored')


if __name__=='__main__':main()
