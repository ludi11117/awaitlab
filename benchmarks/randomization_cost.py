"""Frozen/current randomized timing; memory is measured separately."""
import hashlib
import json
from pathlib import Path
import random
import statistics
import sys
import time
import tracemalloc

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import baseline_v064_statistics as before
from awaitlab import statistics as after,__version__


def inputs(n):
    return [100.0]*n,[100.0+(i%5-2)*.2-.15 for i in range(n)]


def sample(module,n,repeats):
    c,t=inputs(n);start=time.perf_counter_ns()
    for _ in range(repeats):result=module.paired_randomization(c,t)
    elapsed=(time.perf_counter_ns()-start)/1e6/repeats
    assert 0<result['pvalue']<=1
    return elapsed,result


def main():
    manifest=json.loads((ROOT/'benchmarks/baseline-v064-statistics.json').read_text())
    assert hashlib.sha256(Path(before.__file__).read_bytes()).hexdigest()==manifest['source_sha256']
    source_hash=hashlib.sha256(Path(after.__file__).read_bytes()).hexdigest()
    plan={'version':__version__,'baseline':manifest,'pairs':12,'seed':2409,
        'repeats':{8:20,12:5,16:1,24:1,32:1},'current_statistics_sha256':source_hash,
        'primary_family':['8','12','16'],'extended_scope':'24/32 compare old approximate vs new exact costs, descriptive only'}
    modules={'baseline':before,'current':after};samples={str(n):[] for n in plan['repeats']}
    results={};rng=random.Random(plan['seed'])
    for name,module in modules.items():
        for n in plan['repeats']:sample(module,n,1)
    for block in range(plan['pairs']):
        cases=list(plan['repeats']);rng.shuffle(cases)
        for n in cases:
            order=list(modules);rng.shuffle(order);row={'block':block,'order':order}
            for name in order:
                row[name],result=sample(modules[name],n,plan['repeats'][n])
                results.setdefault(str(n),{})[name]=result
            if n<=16:
                assert results[str(n)]['baseline']['extreme_assignments']==results[str(n)]['current']['extreme_assignments']
            samples[str(n)].append(row)
    measurements={}
    for n,rows in samples.items():
        c=[r['baseline'] for r in rows];t=[r['current'] for r in rows]
        item={'samples_ms':rows,'baseline_mean_ms':statistics.fmean(c),'current_mean_ms':statistics.fmean(t),
            'baseline_result':results[n]['baseline'],'current_result':results[n]['current']}
        if n in plan['primary_family']:
            item['effect']=after.paired_effect(c,t,plan['seed'])
            item['randomization']=after.paired_randomization(c,t,plan['seed'])
        measurements[n]=item
        print(n,item['baseline_mean_ms'],item['current_mean_ms'],flush=True)
    adjusted=after.holm_adjust({n:measurements[n]['randomization']['pvalue'] for n in plan['primary_family']})
    for n,value in adjusted.items():measurements[n]['holm_adjusted_p']=value
    memory={}
    for n in [16,32]:
        memory[str(n)]={}
        for name,module in modules.items():
            tracemalloc.start();sample(module,n,1);_,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
            memory[str(n)][name]={'traced_peak_kib':peak/1024}
    assert hashlib.sha256(Path(after.__file__).read_bytes()).hexdigest()==source_hash
    result={'plan':plan,'measurements':measurements,'memory':memory,
        'limits':['fixed input fixture, not a business speedup benchmark',
            'primary n<=16 fixture has equal tail counts; not universal old/new arithmetic equivalence',
            'extended cases change precision mode, not the same computation',
            'tracemalloc peaks exclude interpreter/runtime; separate from timing; not a universal memory bound']}
    target=ROOT/f'artifacts/randomization-cost-v{__version__}.json'
    target.write_text(json.dumps(result,indent=2),encoding='utf-8');print(target,flush=True)


if __name__=='__main__':main()
