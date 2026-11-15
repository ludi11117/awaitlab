from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from awaitlab import Experiment,Settings
from awaitlab.sqlite_workload import prepare_fixture
from examples import order_query_case as case


class OrderQueryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temp=Path('D:/CodexWork/temp/awaitlab');temp.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=temp);self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.path=prepare_fixture(self.root,rows=1000)['paths']['indexed']

    def compare(self,orders,expected_counts):
        results=[case.read_orders(self.path,orders,reader) for reader in (case.per_order,case.per_customer,case.batched)]
        self.assertEqual([result[1] for result in results],expected_counts)
        self.assertEqual(results[0][0],results[1][0]);self.assertEqual(results[0][0],results[2][0])
        return results[0][0]['orders']

    def test_repeated_and_missing_customers_preserve_every_order(self):
        output=self.compare(case.order_inputs(3,1000),[48,13,1])
        self.assertEqual(len(output),48)
        self.assertEqual([row['id'] for row in output],list(range(3000,3048)))
        self.assertEqual(output[0]['customers'],output[13]['customers'])
        self.assertEqual(output[12]['customers'],[])

    def test_empty_and_all_missing_inputs(self):
        self.assertEqual(self.compare([],[0,0,0]),[])
        orders=[{'id':i,'customer_email':"missing' OR 1=1 --"} for i in range(4)]
        self.assertTrue(all(not row['customers'] for row in self.compare(orders,[4,1,1])))

    def test_chunk_boundary_and_duplicates_across_chunks(self):
        orders=[{'id':i,'customer_email':f'user-{i+1}@example.test'} for i in range(257)]
        orders+=[{'id':300,'customer_email':'user-1@example.test'}]
        output=self.compare(orders,[258,257,2])
        self.assertEqual(output[0]['customers'],output[-1]['customers'])

    def test_no_cross_request_cache_and_nonunique_email_rows(self):
        orders=[{'id':1,'customer_email':'user-1@example.test'}]*2
        self.compare(orders,[2,1,1])
        with closing(sqlite3.connect(self.path)) as con:
            con.execute('UPDATE customers SET balance=12345 WHERE id=1')
            con.execute("INSERT INTO customers VALUES (1001,'user-1@example.test','Another customer',99)")
            con.commit()
        output=self.compare(orders,[2,1,1])
        self.assertEqual(output[0]['customers'],[[1,'Customer 1',12345],[1001,'Another customer',99]])

    async def test_experiment_counts_all_queries_and_preserves_outputs(self):
        audit=[]
        experiment=Experiment(case.make_workload(self.root,1000,workers=2,audit=audit),case.ARMS,
                              Settings(blocks=2,requests=3,concurrency=2,warmup=1))
        report=await experiment.run()
        self.assertTrue(all(c['output_equivalence'] for c in report['comparisons']))
        self.assertEqual(len(audit),12)
        self.assertTrue(all(len(counts)==4 for counts in audit))
        self.assertEqual(sorted(counts[0] for counts in audit),sorted([48]*8+[13]*2+[1]*2))
        self.assertFalse(report['comparisons'][-1]['candidate_improvement'])


if __name__=='__main__':unittest.main()
