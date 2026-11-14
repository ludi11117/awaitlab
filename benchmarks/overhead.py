"""Measurement of this instrumenter, not of causal inference accuracy."""
import asyncio
import json
from pathlib import Path
import random
import statistics
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from awaitlab import Session,operation


async def plain(i):return i+1
instrumented=operation('noop')(plain)


async def one(mode,count):
    session=None
    start=time.perf_counter_ns()
    if mode=='plain':
        for i in range(count):await plain(i)
    elif mode=='disabled':
        for i in range(count):await instrumented(i)
    else:
        with Session(trace_requests=1 if mode=='bounded_trace' else 0,max_records=4096) as session:
            async with session.request(0):
                for i in range(count):await instrumented(i)
    elapsed=(time.perf_counter_ns()-start)/1000/count
    return {'us_per_call':elapsed,'trace_records':len(session.records) if session else 0,
            'trace_dropped':session.dropped_records if session else 0}


async def main():
    rng=random.Random(41);samples={m:[] for m in ['plain','disabled','aggregate','bounded_trace']}
    for _ in range(7):
        modes=list(samples);rng.shuffle(modes)
        for mode in modes:samples[mode].append(await one(mode,30000))
    result={'calls_per_sample':30000,'blocks':7,'workload':'async function returning immediately, no I/O',
            'results':{m:{'median_us_per_call':statistics.median(s['us_per_call'] for s in rows),
                          'max_trace_records':max(s['trace_records'] for s in rows),
                          'max_trace_dropped':max(s['trace_dropped'] for s in rows),
                          'samples':rows} for m,rows in samples.items()},
            'note':'No-op operations exaggerate relative overhead compared with I/O services. Process memory includes this driver.'}
    try:
        import psutil
        info=psutil.Process().memory_info()
        result['process_memory_mib']={'rss':info.rss/1024**2,'peak_working_set':getattr(info,'peak_wset',info.rss)/1024**2}
    except ImportError:
        result['process_memory_mib']=None
    (ROOT/'artifacts/overhead.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='results'},indent=2))
    for m,row in result['results'].items():print(m,round(row['median_us_per_call'],3),'us/call')


if __name__=='__main__':asyncio.run(main())
