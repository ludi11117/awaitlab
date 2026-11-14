import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from awaitlab import Arm,Experiment,Settings,operation


class CheckpointTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        root=Path('D:/CodexWork/temp/awaitlab');root.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=root)
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'run.checkpoint.json'

    async def fixture(self,blocks=3,requests=2):
        calls=[]
        @operation('query')
        async def query(i):calls.append(i);return i
        @asynccontextmanager
        async def workload():yield query
        arm=Arm('delay','delay','query',.1)
        return Experiment(workload,[arm],Settings(blocks=blocks,requests=requests,warmup=0)),calls

    async def test_failure_then_resume_reuses_only_complete_pairs(self):
        experiment,calls=await self.fixture()
        def interrupt(done,total,name):
            if done==1:raise RuntimeError('stop after first pair')
        with self.assertRaises(RuntimeError):
            await experiment.run(interrupt,checkpoint=self.path,workload_version='fixture-v1')
        state=json.loads(self.path.read_text(encoding='utf-8'))
        self.assertEqual(state['status'],'failed')
        self.assertEqual(len(state['pairs']['delay']),1)
        self.assertEqual(len(calls),4)
        report=await experiment.run(checkpoint=self.path,resume=True,workload_version='fixture-v1')
        self.assertEqual(len(calls),12)
        self.assertEqual(report['run']['resumed_pairs'],1)
        self.assertEqual([p['block'] for p in report['comparisons'][0]['blocks']],[0,1,2])
        self.assertEqual(json.loads(self.path.read_text(encoding='utf-8'))['status'],'complete')
        await experiment.run(checkpoint=self.path,resume=True,workload_version='fixture-v1')
        self.assertEqual(len(calls),12)

    async def test_changed_workload_or_settings_cannot_mix_results(self):
        experiment,calls=await self.fixture(blocks=2)
        await experiment.run(checkpoint=self.path,workload_version='v1')
        original=self.path.read_bytes()
        with self.assertRaisesRegex(ValueError,'identity differs'):
            await experiment.run(checkpoint=self.path,resume=True,workload_version='v2')
        self.assertEqual(self.path.read_bytes(),original)
        changed=Experiment(experiment.workload,experiment.arms,Settings(blocks=2,requests=3,warmup=0))
        with self.assertRaisesRegex(ValueError,'identity differs'):
            await changed.run(checkpoint=self.path,resume=True,workload_version='v1')
        self.assertEqual(len(calls),8)

    async def test_cancelled_half_pair_not_recorded_as_complete(self):
        started=asyncio.Event()
        @operation('work')
        async def work(i):started.set();await asyncio.Event().wait()
        @asynccontextmanager
        async def workload():yield work
        experiment=Experiment(workload,[Arm('delay','delay','work',1)],Settings(blocks=2,requests=2,warmup=0))
        task=asyncio.create_task(experiment.run(checkpoint=self.path,workload_version='v1'))
        await started.wait();task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        state=json.loads(self.path.read_text(encoding='utf-8'))
        self.assertEqual(state['status'],'interrupted')
        self.assertEqual(state['pairs']['delay'],[])

    async def test_modified_measurement_checksum_is_rejected(self):
        experiment,_=await self.fixture(blocks=2)
        await experiment.run(checkpoint=self.path,workload_version='v1')
        state=json.loads(self.path.read_text(encoding='utf-8'))
        state['pairs']['delay'][0]['outputs_equal']=False
        self.path.write_text(json.dumps(state),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'checksum'):
            await experiment.run(checkpoint=self.path,resume=True,workload_version='v1')

    async def test_checkpoint_requires_explicit_data_version(self):
        experiment,_=await self.fixture()
        with self.assertRaisesRegex(ValueError,'workload_version'):
            await experiment.run(checkpoint=self.path)

    async def test_source_change_during_run_prevents_verified_completion(self):
        from awaitlab import checkpoint as checkpoints
        experiment,_=await self.fixture(blocks=2)
        real_identity=checkpoints.identity
        invocations=0
        def changing_identity(*args,**kwargs):
            nonlocal invocations
            invocations+=1
            result=real_identity(*args,**kwargs)
            if invocations>1:result['digest']='changed-during-run'
            return result
        with patch('awaitlab.experiment.checkpoints.identity',side_effect=changing_identity):
            with self.assertRaisesRegex(RuntimeError,'Source code changed'):
                await experiment.run(checkpoint=self.path,workload_version='v1')
        state=json.loads(self.path.read_text(encoding='utf-8'))
        self.assertEqual(state['status'],'failed')
        self.assertEqual(len(state['pairs']['delay']),2)

    async def test_explicit_entry_source_changed_during_run_is_rejected(self):
        experiment,_=await self.fixture(blocks=2)
        entry=self.path.with_name('entry.py');entry.write_text('# configuration v1',encoding='utf-8')
        def edit(done,total,name):
            if done==1:entry.write_text('# configuration v2',encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError,'Source code changed'):
            await experiment.run(edit,checkpoint=self.path,workload_version='v1',source_files=(p for p in [entry]))
        state=json.loads(self.path.read_text(encoding='utf-8'))
        self.assertEqual(state['status'],'failed')
        self.assertEqual(len(state['pairs']['delay']),2)


if __name__=='__main__':unittest.main()
