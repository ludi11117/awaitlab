import asyncio
from contextlib import closing
import json
from pathlib import Path
import tempfile
import unittest
import importlib.util
from awaitlab import Experiment,Settings
from awaitlab.sqlite_workload import prepare_fixture,readonly,read_customer,make_workload,ARMS,table_digest


class SQLiteTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        root=Path('D:/CodexWork/temp/awaitlab');root.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=root);self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    async def test_only_schema_index_differs_and_all_rows_match(self):
        fixture=await asyncio.to_thread(prepare_fixture,self.root,2000)
        self.assertEqual(table_digest(fixture['paths']['unindexed']),table_digest(fixture['paths']['indexed']))
        for name,path in fixture['paths'].items():
            with closing(readonly(path)) as con:
                self.assertEqual(con.execute('SELECT COUNT(*) FROM customers').fetchone()[0],2000)
                indexes=con.execute('PRAGMA index_list(customers)').fetchall()
                self.assertEqual(len(indexes),int(name=='indexed'))
        for email in ['user-17@example.test','missing@example.test','user-2000@example.test']:
            self.assertEqual(read_customer(fixture['paths']['unindexed'],email),read_customer(fixture['paths']['indexed'],email))
        self.assertEqual(prepare_fixture(self.root,2000)['manifest'],fixture['manifest'])

    async def test_changed_fixture_is_not_silently_reused(self):
        fixture=prepare_fixture(self.root,100)
        with fixture['paths']['indexed'].open('ab') as f:f.write(b'changed')
        with self.assertRaisesRegex(ValueError,'fixture changed'):prepare_fixture(self.root,100)

    async def test_actual_executor_queries_remain_equivalent(self):
        factory=make_workload(self.root,rows=2000,workers=2)
        report=await Experiment(factory,ARMS,Settings(blocks=2,requests=8,concurrency=2,warmup=1)).run()
        self.assertEqual(report['schema_version'],3)
        self.assertEqual(report['evidence_policy']['family'],['indexed_lookup','unchanged_lookup'])
        for c in report['comparisons']:
            self.assertTrue(c['output_equivalence'])
            self.assertIn('holm_adjusted_p',c)
            self.assertFalse(c['candidate_improvement']) # two blocks cannot support a claim
            self.assertNotIn('verified_improvement',c)
            for p in c['blocks']:self.assertEqual(p['treatment']['replacement_calls'],8)

    @unittest.skipUnless(all(importlib.util.find_spec(m) for m in ['fastapi','httpx','uvicorn']),
                         'Optional HTTP dependencies not installed')
    async def test_real_database_queries_over_tcp_keep_request_context(self):
        from awaitlab.sqlite_http_workload import make_workload as make_http
        factory=make_http(self.root,rows=2000,workers=2)
        report=await Experiment(factory,[ARMS[0]],Settings(blocks=2,requests=4,concurrency=2,warmup=0)).run()
        c=report['comparisons'][0]
        self.assertTrue(c['output_equivalence'])
        for pair in c['blocks']:
            names={s['name'] for s in pair['control']['operations']}
            self.assertIn('customer.lookup',names);self.assertIn('http.server',names)
            self.assertEqual(pair['treatment']['replacement_calls'],4)


if __name__=='__main__':unittest.main()
