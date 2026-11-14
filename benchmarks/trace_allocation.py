"""Fixed paired check: reduced aggregate allocations, including cold-name cost."""
import asyncio
import hashlib
import json
from pathlib import Path
import platform
import random
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import baseline_v040_trace as before
from awaitlab import trace as after,__version__
from awaitlab.statistics import paired_effect,paired_randomization,holm_adjust


async def value(i):return i+1


async def sample(module,wrappers,mode,count):
    checksum=0
    start=time.perf_counter_ns()
    with module.Session(trace_requests=1 if mode=='bounded_trace' else 0,max_records=4096) as session:
        async with session.request(0):
            if mode=='cold_names':
                for i,func in enumerate(wrappers):checksum+=await func(i)
            else:
                func=wrappers[0]
                for i in range(count):checksum+=await func(i)
    elapsed=(time.perf_counter_ns()-start)/1_000_000/count
    assert checksum==count*(count+1)//2
    assert sum(s['count'] for (name,kind),s in session.stats.items() if kind=='operation')==count
    assert len(session.records)==(4096 if mode=='bounded_trace' else 0)
    return elapsed


async def main():
    manifest=json.loads((ROOT/'benchmarks/baseline-v040-manifest.json').read_text(encoding='utf-8'))
    assert hashlib.sha256(Path(before.__file__).read_bytes()).hexdigest()==manifest['frozen_trace_sha256']
    current_hash=hashlib.sha256(Path(after.__file__).read_bytes()).hexdigest()
    counts={'aggregate':100000,'bounded_trace':30000,'cold_names':4000}
    plan={'baseline':manifest,'current_version':__version__,'current_trace_sha256':current_hash,
        'pairs':12,'seed':991,'counts':counts,'bootstrap_resamples':4000,
        'environment':{'python':sys.version,'platform':platform.platform()},
        'scope':'empty async calls; cold_names includes many distinct aggregates; no I/O or application speedup inference'}
    modules={'baseline':before,'candidate':after}
    wrappers={name:{mode:[module.operation(f'noop.{i}' if mode=='cold_names' else 'noop')(value)
        for i in range(count if mode=='cold_names' else 1)] for mode,count in counts.items()}
        for name,module in modules.items()}
    for name,module in modules.items():
        await sample(module,wrappers[name]['aggregate'],'aggregate',3000)
    samples={mode:[] for mode in counts};rng=random.Random(plan['seed'])
    for block in range(plan['pairs']):
        modes=list(counts);rng.shuffle(modes)
        for mode in modes:
            names=list(modules);rng.shuffle(names);row={'block':block,'order':names}
            for name in names:row[name]=await sample(modules[name],wrappers[name][mode],mode,counts[mode])
            samples[mode].append(row)
    assert hashlib.sha256(Path(after.__file__).read_bytes()).hexdigest()==current_hash
    results={}
    for mode,rows in samples.items():
        controls=[p['baseline'] for p in rows];treatments=[p['candidate'] for p in rows]
        effect=paired_effect(controls,treatments,plan['seed'],plan['bootstrap_resamples'])
        results[mode]={'effect':effect,'randomization':paired_randomization(controls,treatments,plan['seed']),
            'samples_ms_per_call':rows}
    adjusted=holm_adjust({k:v['randomization']['pvalue'] for k,v in results.items()})
    for mode,row in results.items():
        row['holm_adjusted_p']=adjusted[mode]
        print(f'{mode}: {row["effect"]["mean_change_pct"]:+.2f}% time/call, adjusted p={adjusted[mode]:.6f}',flush=True)
    report={'plan':plan,'results':results,'limits':['one process/machine and one fixed protocol','all inference exploratory',
        'no-op calls amplify instrumenter cost','cold-name setup/wrapper creation excluded; new aggregate creation included']}
    target=ROOT/f'artifacts/trace-allocation-v{__version__}.json'
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(target,flush=True)


if __name__=='__main__':asyncio.run(main())
