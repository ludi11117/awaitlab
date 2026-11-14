import importlib.util
from pathlib import Path
import tempfile
import unittest
from awaitlab import Arm,Experiment,Settings


@unittest.skipUnless(all(importlib.util.find_spec(m) for m in ['fastapi','httpx','uvicorn']),
                     'Optional HTTP dependencies not installed')
class CustomerAPITests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        root=Path('D:/CodexWork/temp/awaitlab');root.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=root);self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    async def run_case(self,project=True,replacement=None):
        from examples.customer_api_case import make_workload
        from awaitlab import sqlite_workload as database
        audit=[]
        arm=Arm('indexed','replacement','customer.lookup',replacements={'customer.lookup':replacement or database.indexed_lookup})
        experiment=Experiment(make_workload(self.root,rows=2000,workers=2,project=project,audit=audit),[arm],
            Settings(blocks=2,requests=4,concurrency=2,warmup=1))
        return await experiment.run(),audit

    async def test_explicit_business_scope_with_persistent_http_and_lifespan(self):
        report,audit=await self.run_case()
        self.assertTrue(report['comparisons'][0]['output_equivalence'])
        self.assertEqual(len(audit),4)
        for state in audit:
            self.assertEqual(state['startups'],1);self.assertEqual(state['shutdowns'],1)
            self.assertEqual(state['requests'],5)
            self.assertTrue(state['client_closed']);self.assertEqual(state['pending_tickets'],0)
            self.assertGreaterEqual(state['http_connections'],1);self.assertLessEqual(state['http_connections'],2)

    async def test_full_response_check_detects_dynamic_metadata(self):
        report,_=await self.run_case(project=False)
        c=report['comparisons'][0]
        self.assertFalse(c['output_equivalence']);self.assertEqual(c['evidence_level'],'invalid_output')
        self.assertTrue(all(b['output_mismatch_ids']==[0,1,2,3] for b in c['blocks']))

    async def test_business_exception_still_closes_client_and_resources(self):
        from examples.customer_api_case import make_workload
        audit=[]
        with self.assertRaisesRegex(LookupError,'business failed'):
            async with make_workload(self.root,rows=2000,workers=1,audit=audit)() as handler:
                await handler(1)
                raise LookupError('business failed')
        self.assertEqual(audit[0]['shutdowns'],1)
        self.assertTrue(audit[0]['client_closed']);self.assertEqual(audit[0]['pending_tickets'],0)

    async def test_business_change_still_fails_under_projection(self):
        from awaitlab import sqlite_workload as database
        async def changed_balance(store,email):
            result=await database.indexed_lookup(store,email)
            for customer in result['customers']:customer[2]+=1
            return result
        report,_=await self.run_case(replacement=changed_balance)
        c=report['comparisons'][0]
        self.assertEqual(c['evidence_level'],'invalid_output')
        self.assertTrue(all(b['output_mismatch_ids']==[1,2,3] for b in c['blocks']))


if __name__=='__main__':unittest.main()
