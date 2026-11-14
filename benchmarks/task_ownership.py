"""Fixed task-heavy timing probe; compare lifecycle ownership implementations."""
import asyncio
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import platform
import random
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import baseline_v060_ownership as before
from awaitlab import ownership as after,__version__
from awaitlab.statistics import paired_effect,paired_randomization,holm_adjust


async def value(i,yield_once):
    if yield_once:await asyncio.sleep(0)
    return i


async def sample(owner,mode,count,wave):
    total=0
    start=time.perf_counter_ns()
    with owner():
        for offset in range(0,count,wave):
            batch=[asyncio.create_task(value(i,mode=='yield_once')) for i in range(offset,offset+wave)]
            total+=sum(await asyncio.gather(*batch))
    elapsed=(time.perf_counter_ns()-start)/1_000_000/count
    assert total==count*(count-1)//2
    return elapsed


async def main():
    manifest=json.loads((ROOT/'benchmarks/baseline-v060-ownership.json').read_text())
    assert hashlib.sha256(Path(before.__file__).read_bytes()).hexdigest()==manifest['ownership_sha256']
    source_hash=hashlib.sha256(Path(after.__file__).read_bytes()).hexdigest()
    plan={'version':__version__,'baseline':manifest,'pairs':12,'tasks_per_sample':4096,'wave':64,'seed':1807,
        'modes':['immediate','yield_once'],'current_source_sha256':source_hash,
        'environment':{'python':sys.version,'platform':platform.platform()}}
    owners={'untracked':nullcontext,'weak_baseline':before.owned_tasks,'strong_current':after.owned_tasks}
    for owner in owners.values():await sample(owner,'yield_once',256,64)
    rng=random.Random(plan['seed']);pairs={m:[] for m in plan['modes']}
    for block in range(plan['pairs']):
        modes=plan['modes'][:];rng.shuffle(modes)
        for mode in modes:
            order=list(owners);rng.shuffle(order);row={'block':block,'order':order}
            for name in order:row[name]=await sample(owners[name],mode,plan['tasks_per_sample'],plan['wave'])
            pairs[mode].append(row)
    assert hashlib.sha256(Path(after.__file__).read_bytes()).hexdigest()==source_hash
    results={}
    for mode,rows in pairs.items():
        c=[p['weak_baseline'] for p in rows];t=[p['strong_current'] for p in rows]
        results[mode]={'samples_ms_per_task':rows,'strong_minus_weak':paired_effect(c,t,plan['seed']),
            'randomization':paired_randomization(c,t,plan['seed'])}
    adjusted=holm_adjust({m:r['randomization']['pvalue'] for m,r in results.items()})
    for mode,row in results.items():
        row['holm_adjusted_p']=adjusted[mode]
        print(f'{mode}: strong vs weak {row["strong_minus_weak"]["mean_change_pct"]:+.2f}% task/wave time, adjusted p={adjusted[mode]:.6f}',flush=True)
    report={'plan':plan,'results':results,'limits':['one process/machine, exploratory timing','includes task/gather/scheduling and registry overhead',
        'untracked mode has no lifecycle cleanup guarantee','no I/O or application speedup inference']}
    path=ROOT/f'artifacts/task-ownership-v{__version__}.json'
    path.write_text(json.dumps(report,indent=2),encoding='utf-8');print(path,flush=True)


if __name__=='__main__':asyncio.run(main())
