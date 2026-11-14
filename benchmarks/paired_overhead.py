"""Compare frozen v0.1.0 and current tracing in randomized paired blocks."""
import asyncio
import hashlib
import json
from pathlib import Path
import random
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import baseline_v010_trace as before
from awaitlab import trace as after
from awaitlab.statistics import paired_effect


async def value(i):return i+1


async def sample(module,wrapped,count):
    start=time.perf_counter_ns()
    with module.Session(trace_requests=0) as session:
        async with session.request(0):
            for i in range(count):await wrapped(i)
    elapsed=(time.perf_counter_ns()-start)/1_000_000/count
    assert session.stats[('noop','operation')]['count']==count
    return elapsed


async def main():
    manifest=json.loads((ROOT/'benchmarks/baseline-manifest.json').read_text(encoding='utf-8'))
    source=Path(before.__file__).read_bytes()
    assert hashlib.sha256(source).hexdigest()==manifest['source_sha256'],'Frozen baseline changed'
    modules={'baseline':before,'current':after}
    wrapped={name:module.operation('noop')(value) for name,module in modules.items()}
    for name in modules:await sample(modules[name],wrapped[name],3000)
    rng=random.Random(73);pairs=[]
    for block in range(11):
        order=list(modules);rng.shuffle(order)
        row={'block':block,'order':order}
        for name in order:row[name]=await sample(modules[name],wrapped[name],30000)
        pairs.append(row)
    effect=paired_effect([p['baseline'] for p in pairs],[p['current'] for p in pairs],resamples=4000)
    report={'baseline':manifest,'current_source_sha256':hashlib.sha256(Path(after.__file__).read_bytes()).hexdigest(),
            'calls_per_sample':30000,'blocks':len(pairs),'mode':'aggregate, no sampled spans, no I/O',
            'mean_change_pct':effect['mean_change_pct'],'mean_delta_us_per_call':effect['mean_delta_ms']*1000,
            'ci95_delta_us_per_call':[v*1000 for v in effect['ci95_delta_ms']],
            'samples_ms_per_call':pairs,
            'limits':['one machine and process','empty async function exaggerates relative overhead',
                      'does not measure application speedup or inference/causal accuracy']}
    (ROOT/'artifacts/paired-overhead.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='samples_ms_per_call'},indent=2))


if __name__=='__main__':asyncio.run(main())
