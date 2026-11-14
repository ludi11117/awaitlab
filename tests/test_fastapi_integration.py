import importlib.util
import unittest
from awaitlab import Arm,Experiment,Settings
from awaitlab.scenarios import fast_pricing


@unittest.skipUnless(importlib.util.find_spec('fastapi') and importlib.util.find_spec('httpx'),
                     'Optional FastAPI/HTTPX integration dependencies not installed')
class FastAPITests(unittest.IsolatedAsyncioTestCase):
    async def test_context_and_output_checks_survive_real_routing(self):
        from examples.fastapi_lab import application
        arm=Arm('fast','replacement','pricing.quote',replacements={'pricing.quote':fast_pricing})
        report=await Experiment(application,[arm],Settings(blocks=2,requests=4,warmup=0)).run()
        c=report['comparisons'][0]
        self.assertTrue(c['output_equivalence'])
        for pair in c['blocks']:
            self.assertEqual(pair['treatment']['replacement_calls'],4)
            names={row['name'] for row in pair['control']['operations']}
            self.assertIn('inventory.lookup',names)
            self.assertIn('pricing.quote',names)


if __name__=='__main__':unittest.main()
