"""Frozen/current trace timing with and without active replacements."""
import asyncio
import hashlib
import json
from pathlib import Path
import random
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import baseline_v062_trace as before
from awaitlab import trace as after,__version__
from awaitlab.statistics import paired_effect,paired_randomization,holm_adjust


async def value(i):return i+1


async def sample(module,wrapped,mode,count):
    total=0
    start=time.perf_counter_ns()
    with module.Session(trace_requests=0,replacements={'noop':value} if mode=='replacement' else {}) as session:
        async with session.request(0):
            for i in range(count):total+=await wrapped(i)
    elapsed=(time.perf_counter_ns()-start)/1e6/count
    assert total==count*(count+1)//2
    assert session.stats[('noop','operation')]['count']==count
    assert session.replacement_calls==(count if mode=='replacement' else 0)
    if hasattr(session,'replacement_calls_by_site'):
        assert session.replacement_calls_by_site==({'noop':count} if mode=='replacement' else {})
    return elapsed


async def main():
    manifest=json.loads((ROOT/'benchmarks/baseline-v062-reach.json').read_text())
    assert hashlib.sha256(Path(before.__file__).read_bytes()).hexdigest()==manifest['source_sha256']['trace.py']
    source_hash=hashlib.sha256(Path(after.__file__).read_bytes()).hexdigest()
    plan={'version':__version__,'baseline':manifest,'pairs':12,'calls_per_sample':100000,'seed':2121,
        'modes':['aggregate','replacement'],'current_trace_sha256':source_hash}
    modules={'baseline':before,'current':after}
    wrappers={name:module.operation('noop')(value) for name,module in modules.items()}
    for name,module in modules.items():
        for mode in plan['modes']:await sample(module,wrappers[name],mode,3000)
    rng=random.Random(plan['seed']);samples={m:[] for m in plan['modes']}
    for block in range(plan['pairs']):
        modes=plan['modes'][:];rng.shuffle(modes)
        for mode in modes:
            names=list(modules);rng.shuffle(names);row={'block':block,'order':names}
            for name in names:row[name]=await sample(modules[name],wrappers[name],mode,plan['calls_per_sample'])
            samples[mode].append(row)
    assert hashlib.sha256(Path(after.__file__).read_bytes()).hexdigest()==source_hash
    results={}
    for mode,rows in samples.items():
        c=[p['baseline'] for p in rows];t=[p['current'] for p in rows]
        results[mode]={'samples_ms_per_call':rows,'effect':paired_effect(c,t,plan['seed']),
            'randomization':paired_randomization(c,t,plan['seed'])}
    adjusted=holm_adjust({m:r['randomization']['pvalue'] for m,r in results.items()})
    for mode,r in results.items():
        r['holm_adjusted_p']=adjusted[mode]
        print(mode,r['effect']['mean_change_pct'],r['effect']['mean_delta_ms']*1000,'us delta',flush=True)
    result={'plan':plan,'results':results,'limits':['empty async calls and checksum loop, no I/O',
        'exploratory paired evidence in one process; not business speedup','replacement mode uses same underlying function on both sides']}
    target=ROOT/f'artifacts/replacement-counter-cost-v{__version__}.json'
    target.write_text(json.dumps(result,indent=2),encoding='utf-8');print(target,flush=True)


if __name__=='__main__':asyncio.run(main())
