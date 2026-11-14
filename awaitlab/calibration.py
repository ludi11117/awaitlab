import asyncio
import time
from .statistics import describe


async def calibrate(repetitions=7):
    rows=[]
    for requested in [1,4,8,10,12,20,30,32]:
        samples=[]
        for _ in range(repetitions):
            start=time.perf_counter_ns()
            await asyncio.sleep(requested/1000)
            samples.append((time.perf_counter_ns()-start)/1_000_000)
        rows.append({'requested_ms':requested,**describe(samples)})
    return {'sleep_samples':rows,'clock':{name:vars(time.get_clock_info(name)) for name in ['perf_counter','monotonic']},
            'note':'measured in an idle calibration; per-arm observed injection includes actual scheduling under load; no timer resolution changes requested'}
