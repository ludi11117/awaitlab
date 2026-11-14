import asyncio
from contextlib import asynccontextmanager
import unittest
from awaitlab import Arm,Experiment,Session,Settings,operation,stage
from awaitlab.statistics import quantile,paired_effect


class TraceTests(unittest.IsolatedAsyncioTestCase):
    async def test_spawned_tasks_keep_correct_request_parents(self):
        @operation('child')
        async def child():
            await asyncio.sleep(0)
            return 3
        async def request(session,i):
            async with session.request(i):
                return await asyncio.gather(child(),child())
        with Session(trace_requests=2) as session:
            result=await asyncio.gather(request(session,0),request(session,1))
        self.assertEqual(result,[[3,3],[3,3]])
        records={r.id:r for r in session.records}
        children=[r for r in records.values() if r.name=='child']
        self.assertEqual(len(children),4)
        for child in children:
            parent=records[child.parent]
            self.assertEqual(parent.name,'request')
            self.assertEqual(parent.request,child.request)
            self.assertNotEqual(parent.task,child.task)

    async def test_delay_is_cooperative_and_keeps_resource_held(self):
        semaphore=asyncio.Semaphore(1)
        operation_returned=asyncio.Event()
        observed=[]
        @operation('query')
        async def query():
            operation_returned.set()
            return 'value'
        async def worker():
            async with semaphore:
                return await query()
        async def observer():
            await operation_returned.wait()
            observed.append(semaphore.locked())
        with Session(delay_site='query',delay_ms=15) as session:
            result=await asyncio.gather(worker(),observer())
        self.assertEqual(result[0],'value')
        self.assertEqual(observed,[True])
        self.assertEqual(session.interventions,1)

    async def test_context_restored_after_exception(self):
        @operation('fail')
        async def fail():raise LookupError('expected')
        with Session() as session:
            with self.assertRaises(LookupError):await fail()
            async with stage('after'):
                pass
        self.assertEqual(session.stats[('fail','operation')]['failed'],1)
        self.assertTrue(all(r.parent is None for r in session.records))
        before=len(session.stats)
        with self.assertRaises(LookupError):await fail()
        self.assertEqual(len(session.stats),before)

    async def test_cancellation_recorded_and_propagated(self):
        entered=asyncio.Event()
        @operation('cancel')
        async def wait():
            entered.set();await asyncio.Event().wait()
        with Session() as session:
            task=asyncio.create_task(wait());await entered.wait();task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
        self.assertEqual(session.stats[('cancel','operation')]['failed'],1)

    async def test_bounded_trace_retains_aggregate_counts(self):
        @operation('many')
        async def many():return 1
        with Session(max_records=3) as session:
            async with session.request(0):
                for _ in range(30):await many()
        self.assertEqual(len(session.records),3)
        self.assertEqual(session.dropped_records,28)
        self.assertEqual(session.stats[('many','operation')]['count'],30)


class ExperimentTests(unittest.IsolatedAsyncioTestCase):
    def settings(self):return Settings(blocks=2,requests=5,concurrency=2,warmup=0)

    async def test_actual_replacement_must_preserve_tested_outputs(self):
        @operation('value')
        async def value(i):return {'value':i}
        async def changed(i):return {'value':i+1}
        @asynccontextmanager
        async def factory():yield value
        report=await Experiment(factory,[Arm('bad','replacement','value',replacements={'value':changed})],self.settings()).run()
        comparison=report['comparisons'][0]
        self.assertFalse(comparison['output_equivalence'])
        self.assertFalse(comparison['candidate_improvement'])

    async def test_typo_in_site_cannot_be_reported_as_zero_sensitivity(self):
        @operation('real')
        async def value(i):return i
        @asynccontextmanager
        async def factory():yield value
        with self.assertRaisesRegex(ValueError,'did not reach'):
            await Experiment(factory,[Arm('typo','delay','missing',1)],self.settings()).run()

    async def test_failed_worker_cancels_siblings_and_closes_resources(self):
        exited=[];pending=[]
        @operation('work')
        async def work(i):
            if i==0:
                await asyncio.sleep(0)
                raise RuntimeError('injected')
            try:await asyncio.Event().wait()
            finally:pending.append('cancelled')
        @asynccontextmanager
        async def factory():
            try:yield work
            finally:exited.append('closed')
        with self.assertRaisesRegex(RuntimeError,'injected'):
            await Experiment(factory,[Arm('delay','delay','work',1)],self.settings()).run()
        self.assertTrue(exited)
        self.assertTrue(pending)

    async def test_each_arm_uses_fresh_resources_and_warms_replacement(self):
        seen=[]
        @operation('f')
        async def value(i):seen.append(('original',i));return i
        async def replacement(i):seen.append(('replacement',i));return i
        @asynccontextmanager
        async def factory():yield value
        experiment=Experiment(factory,[Arm('replacement','replacement','f',replacements={'f':replacement})],Settings(blocks=2,requests=2,warmup=1))
        result=await experiment._block(experiment.arms[0])
        self.assertIn(('replacement',-1),seen)
        self.assertNotIn(('original',-1),seen)
        self.assertEqual(result['replacement_calls'],2)

    async def test_leaked_background_task_rejects_measurement(self):
        background=[]
        @operation('work')
        async def work(i):
            background.append(asyncio.create_task(asyncio.Event().wait()))
            await asyncio.sleep(0)
            return i
        @asynccontextmanager
        async def factory():yield work
        experiment=Experiment(factory,[Arm('delay','delay','work',1)],self.settings())
        with self.assertRaisesRegex(RuntimeError,'leaked background tasks'):
            await experiment._block(None)
        self.assertTrue(all(t.cancelled() for t in background))

    async def test_report_compacts_hashes_without_losing_mismatch_ids(self):
        @operation('f')
        async def f(i):return i
        async def other(i):return 99 if i==2 else i
        @asynccontextmanager
        async def factory():yield f
        result=await Experiment(factory,[Arm('other','replacement','f',replacements={'f':other})],self.settings()).run()
        for block in result['comparisons'][0]['blocks']:
            self.assertEqual(block['output_mismatch_ids'],[2])
            self.assertNotIn('output_hashes',block['control'])
            self.assertEqual(len(block['control']['batch_output_hash']),64)

    async def test_unrelated_tasks_created_during_block_are_not_cancelled(self):
        trigger=asyncio.Event();created=asyncio.Event();foreign=[]
        async def unrelated_producer():
            await trigger.wait()
            foreign.append(asyncio.create_task(asyncio.Event().wait()))
            created.set()
        producer=asyncio.create_task(unrelated_producer())
        @operation('f')
        async def f(i):
            trigger.set();await created.wait();return i
        @asynccontextmanager
        async def factory():yield f
        previous=asyncio.get_running_loop().get_task_factory()
        try:
            experiment=Experiment(factory,[Arm('d','delay','f',1)],self.settings())
            await experiment._block(None)
            self.assertFalse(foreign[0].done())
            self.assertIs(asyncio.get_running_loop().get_task_factory(),previous)
        finally:
            await producer
            for task in foreign:task.cancel()
            await asyncio.gather(*foreign,return_exceptions=True)


class StatisticsTests(unittest.TestCase):
    def test_quantile_interpolates_small_samples(self):
        self.assertEqual(quantile([10,20],.5),15)
        self.assertAlmostEqual(quantile([10,20],.95),19.5)

    def test_paired_interval_preserves_pairing(self):
        result=paired_effect([10,100,1000],[8,98,998],resamples=100)
        self.assertEqual(result['mean_delta_ms'],-2)
        self.assertEqual(result['ci95_delta_ms'],[-2,-2])


if __name__=='__main__':unittest.main()
