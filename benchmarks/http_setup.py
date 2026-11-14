"""Paired setup costs, with explicit cold trust-store cost and fresh client pools."""
import argparse
import asyncio
from contextlib import asynccontextmanager
import hashlib
import importlib.util
from importlib.metadata import version
import json
from pathlib import Path
import platform
import random
import ssl
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import httpx
from fastapi import FastAPI,Request
from awaitlab import __version__,local_http as current
from awaitlab.statistics import paired_effect,paired_randomization,holm_adjust

path=ROOT/'benchmarks/baseline_v061_local_http.py'
spec=importlib.util.spec_from_file_location('awaitlab._baseline_v061_http',path)
before=importlib.util.module_from_spec(spec);sys.modules[spec.name]=before;spec.loader.exec_module(before)


async def client_sample(cached):
    kwargs={'verify':current._client_ssl_context()} if cached else {}
    started=time.perf_counter_ns()
    client=httpx.AsyncClient(base_url='http://127.0.0.1:1',trust_env=False,timeout=10,**kwargs)
    built=time.perf_counter_ns();await client.aclose()
    return {'construct_ms':(built-started)/1e6,'close_ms':(time.perf_counter_ns()-built)/1e6}


async def helper_sample(helper):
    state={'startup':0,'shutdown':0};ports=set()
    @asynccontextmanager
    async def lifecycle(app):
        state['startup']+=1
        try:yield
        finally:state['shutdown']+=1
    app=FastAPI(lifespan=lifecycle)
    @app.get('/')
    async def ping(request:Request):
        ports.add(request.client.port)
        return {'ok':True}
    started=time.perf_counter_ns()
    async with helper(app) as (client,bridge):
        ready=time.perf_counter_ns()
        for _ in range(3):assert (await client.get('/')).json()=={'ok':True}
        closing=time.perf_counter_ns()
    finished=time.perf_counter_ns()
    assert state=={'startup':1,'shutdown':1} and len(ports)==1
    assert client.is_closed and bridge.pending_tickets==0
    return {'setup_ms':(ready-started)/1e6,'three_requests_ms':(closing-ready)/1e6,
            'shutdown_ms':(finished-closing)/1e6,'total_ms':(finished-started)/1e6}


async def worker(mode):
    rows=[]
    helper=before.serve_local if mode=='baseline' else current.serve_local
    for _ in range(12):rows.append(await helper_sample(helper))
    result={'mode':mode,'lifetimes':12,'phases':rows,
        'scope':'one fresh whole driver process, 12 app/client lifetimes, includes imports; descriptive memory only'}
    try:
        import psutil
        memory=psutil.Process().memory_info()
        result['memory']={'rss_end_mib':memory.rss/1024**2,'peak_working_set_mib':getattr(memory,'peak_wset',memory.rss)/1024**2}
    except ImportError:result['memory']=None
    print(json.dumps(result))


def memory_workers():
    order=['baseline','cached'];random.Random(91).shuffle(order)
    results=[]
    for mode in order:
        child=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker',mode],
            capture_output=True,encoding='utf-8',check=True)
        results.append(json.loads(child.stdout))
    report={'version':__version__,'order':order,'workers':results,
        'limits':['one separate process per configuration, no memory inference','first cold context cost included in each worker',
            'all 12 lifetimes close app/client/pool; no service output speedup claim']}
    target=ROOT/f'artifacts/http-setup-memory-v{__version__}.json'
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(target,flush=True)


async def main():
    manifest=json.loads((ROOT/'benchmarks/baseline-v061-http.json').read_text())
    assert hashlib.sha256(path.read_bytes()).hexdigest()==manifest['local_http_sha256']
    source_hash=hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest()
    current._client_ssl_context.cache_clear()
    start=time.perf_counter_ns();context=current._client_ssl_context();cold_ms=(time.perf_counter_ns()-start)/1e6
    assert context.verify_mode==ssl.CERT_REQUIRED and context.check_hostname
    plan={'version':__version__,'baseline':manifest,'pairs':12,'seed':409,'source_sha256':source_hash,
        'dependencies':{m:version(m) for m in ['httpx','uvicorn','fastapi','certifi']},
        'environment':{'python':sys.version,'platform':platform.platform()},
        'protocol':'warm each helper once, then random paired order; fresh app/client/pool each lifetime; same three local requests',
        'cold_context_ms':cold_ms,'trust_store_stats':context.cert_store_stats(),
        'verify_mode':int(context.verify_mode),'check_hostname':context.check_hostname}
    for helper in [before.serve_local,current.serve_local]:await helper_sample(helper)
    rng=random.Random(plan['seed']);clients=[];helpers=[]
    for block in range(plan['pairs']):
        for kind,rows in [('client',clients),('helper',helpers)]:
            order=['baseline','cached'];rng.shuffle(order);row={'block':block,'order':order}
            for mode in order:
                row[mode]=await client_sample(mode=='cached') if kind=='client' else await helper_sample(before.serve_local if mode=='baseline' else current.serve_local)
            rows.append(row)
    assert hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest()==source_hash
    results={}
    for name,rows,field in [('client_construct',clients,'construct_ms'),('helper_setup',helpers,'setup_ms')]:
        c=[p['baseline'][field] for p in rows];t=[p['cached'][field] for p in rows]
        results[name]={'effect':paired_effect(c,t,plan['seed']),'randomization':paired_randomization(c,t,plan['seed'])}
    adjusted=holm_adjust({k:r['randomization']['pvalue'] for k,r in results.items()})
    for name,r in results.items():
        r['holm_adjusted_p']=adjusted[name]
        print(name,r['effect']['mean_change_pct'],flush=True)
    report={'plan':plan,'clients':clients,'helpers':helpers,'results':results,
        'limits':['steady setup after first trust-store creation; cold cost reported separately',
            'no business-request acceleration inference','context is reused, apps/clients/pools are fresh',
            'single machine/process, exploratory paired evidence']}
    target=ROOT/f'artifacts/http-setup-v{__version__}.json'
    target.write_text(json.dumps(report,indent=2),encoding='utf-8');print(target,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group()
    group.add_argument('--worker',choices=['baseline','cached'],help=argparse.SUPPRESS)
    group.add_argument('--memory',action='store_true',help='Run baseline/cached in separate fresh processes')
    args=parser.parse_args()
    if args.memory:memory_workers()
    else:asyncio.run(worker(args.worker) if args.worker else main())
