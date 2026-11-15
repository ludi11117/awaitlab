"""Reproduce primary-site masking by another replacement in the same arm."""
import asyncio
from contextlib import asynccontextmanager
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from awaitlab import Arm,Experiment,Settings,operation,stage,__version__
from awaitlab import trace as current_trace
import baseline_v062_trace as frozen_trace

path=ROOT/'benchmarks/baseline_v062_experiment.py'
spec=importlib.util.spec_from_file_location('awaitlab._baseline_v062_experiment',path)
before=importlib.util.module_from_spec(spec);sys.modules[spec.name]=before;spec.loader.exec_module(before)


@operation('primary')
async def primary(i):return i*2


@operation('active')
async def active(i):return i*2


async def replacement(i):return i*2


def workload_for(mode):
    @asynccontextmanager
    async def workload():
        closing=asyncio.Event();late=None
        async def handler(i):
            nonlocal late
            if mode=='cleanup_only' and i==0:
                async def cleanup():
                    await closing.wait();await primary(0)
                late=asyncio.create_task(cleanup())
            if mode=='warmup_only' and i<0:await primary(i)
            if mode=='observational_span':
                async with stage('primary',kind='operation'):pass
            return await active(i)
        try:yield handler
        finally:
            if late is not None:closing.set();await late
    return workload


async def probe(engine,mode):
    arm=Arm('masked','replacement','primary',replacements={'primary':replacement,'active':replacement})
    try:
        report=await engine(workload_for(mode),[arm],Settings(blocks=2,requests=3,concurrency=1,warmup=1)).run()
        c=report['comparisons'][0]
        return {'outcome':'accepted','total_replacement_calls':sum(b['treatment']['replacement_calls'] for b in c['blocks']),
            'observed_operation_names':sorted({o['name'] for b in c['blocks'] for o in b['treatment']['operations'] if o['kind']=='operation'}),
            'output_equivalence':c['output_equivalence']}
    except ValueError as error:return {'outcome':'rejected','reason':str(error)}


async def scope_probe(module):
    calls=[]
    @module.operation('late')
    async def original():calls.append('original');return 1
    async def candidate():calls.append('replacement');return 1
    with module.Session(replacements={'late':candidate}) as session:
        captured=module.capture_context()
    with captured.attach():
        result=await original()
        recaptured=module.capture_context() is not None
    return {'calls':calls,'output':result,'replacement_calls':session.replacement_calls,
        'recapture_after_exit':recaptured,'recorded_operations':[s['name'] for s in session.summaries()]}


async def main():
    manifest=json.loads((ROOT/'benchmarks/baseline-v062-reach.json').read_text())
    assert hashlib.sha256(path.read_bytes()).hexdigest()==manifest['source_sha256']['experiment.py']
    assert hashlib.sha256(Path(frozen_trace.__file__).read_bytes()).hexdigest()==manifest['source_sha256']['trace.py']
    cases={}
    for mode in ['unreached','warmup_only','observational_span','cleanup_only']:
        cases[mode]={'frozen_gate':await probe(before.Experiment,mode),'current_gate':await probe(Experiment,mode)}
    scope={'frozen_trace':await scope_probe(frozen_trace),'current_trace':await scope_probe(current_trace)}
    assert scope['frozen_trace']['calls']==['replacement'] and scope['current_trace']['calls']==['original']
    assert all(c['current_gate']['outcome']=='rejected' for c in cases.values())
    result={'version':__version__,'baseline':manifest,'cases':cases,'expired_capture':scope,
        'scope':'gate cases share current trace and workload; expired_capture compares frozen/current trace independently; correctness only, no speedup inference'}
    target=ROOT/f'artifacts/replacement-reach-v{__version__}.json'
    target.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(cases,indent=2))


if __name__=='__main__':asyncio.run(main())
