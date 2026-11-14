"""Controlled lost-reference task; inspect both frozen and current ownership."""
import asyncio
from contextlib import asynccontextmanager
import gc
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch
import weakref

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import baseline_v060_ownership as before
from awaitlab import Arm,Experiment,Settings,operation,__version__
from awaitlab import ownership as after


async def probe(owner):
    loop=asyncio.get_running_loop();previous_handler=loop.get_exception_handler()
    previous_factory=loop.get_task_factory()
    logs=[];finalized=[];alive=[];refs=[]
    def log(loop,context):logs.append(str(context.get('message')))
    loop.set_exception_handler(log)
    async def orphan():
        try:await asyncio.Event().wait()
        finally:finalized.append(type(sys.exc_info()[1]).__name__)
    @operation('value')
    async def value(i):
        gc.collect();alive.append(refs[0]() is not None)
        return i
    @asynccontextmanager
    async def workload():
        task=asyncio.create_task(orphan());refs.append(weakref.ref(task));del task
        await asyncio.sleep(0)
        yield value
    unrelated=asyncio.create_task(asyncio.Event().wait())
    try:
        experiment=Experiment(workload,[Arm('unused','delay','value',1)],
            Settings(blocks=2,requests=2,concurrency=1,warmup=0))
        with patch('awaitlab.experiment.owned_tasks',owner):
            try:
                await experiment._block(None)
                outcome='accepted'
            except RuntimeError as error:
                outcome=str(error)
        return {'outcome':outcome,'task_survived_gc_during_requests':alive,
                'orphan_finalization':finalized,'loop_messages':logs,
                'unrelated_task_untouched':not unrelated.done(),
                'task_factory_restored':loop.get_task_factory() is previous_factory}
    finally:
        unrelated.cancel();await asyncio.gather(unrelated,return_exceptions=True)
        loop.set_exception_handler(previous_handler)


async def main():
    manifest=json.loads((ROOT/'benchmarks/baseline-v060-ownership.json').read_text())
    assert hashlib.sha256(Path(before.__file__).read_bytes()).hexdigest()==manifest['ownership_sha256']
    baseline=await probe(before.owned_tasks);current=await probe(after.owned_tasks)
    result={'version':__version__,'baseline':manifest,'baseline_result':baseline,'current_result':current,
        'current_source_sha256':hashlib.sha256(Path(after.__file__).read_bytes()).hexdigest(),
        'scope':'deliberately orphaned task awaiting a private Event, forced GC, single controlled block; no application performance claim'}
    path=ROOT/f'artifacts/ownership-gc-v{__version__}.json'
    path.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':asyncio.run(main())
