from contextlib import asynccontextmanager
import unittest
from awaitlab import Arm,Experiment,Settings,operation,stage


class ReplacementReachTests(unittest.IsolatedAsyncioTestCase):
    async def check_unreached(self,mode):
        @operation('primary')
        async def primary(i):return i
        @operation('active')
        async def active(i):return i
        async def candidate(i):return i
        @asynccontextmanager
        async def workload():
            async def handler(i):
                if mode=='warmup' and i<0:await primary(i)
                if mode=='span':
                    async with stage('primary',kind='operation'):pass
                return await active(i)
            yield handler
        arm=Arm('bundle','replacement','primary',replacements={'primary':candidate,'active':candidate})
        exp=Experiment(workload,[arm],Settings(blocks=2,requests=3,concurrency=1,warmup=1))
        with self.assertRaisesRegex(ValueError,"did not reach instrumented site 'primary'"):
            await exp.run()

    async def test_other_replacement_does_not_prove_primary_was_called(self):
        await self.check_unreached('none')

    async def test_warmup_primary_does_not_prove_measured_primary_was_called(self):
        await self.check_unreached('warmup')

    async def test_observation_span_is_not_an_actual_replacement(self):
        await self.check_unreached('span')

    async def test_valid_bundle_counts_each_site_and_keeps_total(self):
        @operation('primary')
        async def primary(i):return i
        @operation('secondary')
        async def secondary(i):return i*2
        async def first(i):return i
        async def second(i):return i*2
        @asynccontextmanager
        async def workload():
            async def handler(i):return [await primary(i),await secondary(i),await secondary(i)]
            yield handler
        arm=Arm('bundle','replacement','primary',replacements={'primary':first,'secondary':second,'unused':first})
        report=await Experiment(workload,[arm],Settings(blocks=2,requests=3,warmup=2)).run()
        c=report['comparisons'][0]
        self.assertTrue(c['output_equivalence'])
        self.assertEqual(c['replacement_sites'],['primary','secondary','unused'])
        for b in c['blocks']:
            self.assertEqual(b['control']['replacement_calls_by_site'],{})
            self.assertEqual(b['treatment']['replacement_calls_by_site'],{'primary':3,'secondary':6})
            self.assertEqual(b['treatment']['replacement_calls'],9)

    async def test_secondary_self_wrapper_is_rejected_before_running(self):
        @operation('primary')
        async def primary(i):return i
        @operation('secondary')
        async def secondary(i):return i
        async def candidate(i):return i
        @asynccontextmanager
        async def workload():yield primary
        with self.assertRaisesRegex(ValueError,'own wrapper'):
            Experiment(workload,[Arm('bundle','replacement','primary',replacements={'primary':candidate,'secondary':secondary})])


if __name__=='__main__':unittest.main()
