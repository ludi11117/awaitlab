"""Quantify inline output-check interference; oracle mode is NOT a product feature."""
import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
from pathlib import Path
import random
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from awaitlab import Arm,Experiment,Settings,operation,__version__
from awaitlab.experiment import fingerprint
from awaitlab.statistics import paired_effect


async def main():
    plan={'version':__version__,'payload_sizes':[32,65536,1048576],'pairs':7,'requests':40,
        'concurrency':4,'sleep_seconds':.008,'seed':617,
        'scope':'controlled immutable-output fixture; precomputed oracle removes fingerprint CPU only; not usable for unknown business outputs',
        'sources':{name:hashlib.sha256((ROOT/'awaitlab'/name).read_bytes()).hexdigest() for name in ['experiment.py','trace.py']}}
    result={'plan':plan,'cases':[]}
    rng=random.Random(plan['seed'])
    for size in plan['payload_sizes']:
        payload='x'*size
        def value(i):return {'id':i,'payload':payload}
        expected={i:fingerprint(value(i)) for i in range(plan['requests'])}
        @operation('probe.echo')
        async def echo(i):
            await asyncio.sleep(plan['sleep_seconds'])
            return value(i)
        @asynccontextmanager
        async def factory():yield echo
        experiment=Experiment(factory,[Arm('unused','delay','probe.echo',1)],
            Settings(blocks=2,requests=plan['requests'],concurrency=plan['concurrency'],warmup=4,trace_requests=0))
        pairs=[]
        for block in range(plan['pairs']):
            order=['inline','precomputed_oracle'];rng.shuffle(order)
            row={'block':block,'order':order}
            for mode in order:
                checker=fingerprint if mode=='inline' else lambda output:expected[output['id']]
                with patch('awaitlab.experiment.fingerprint',checker):measurement=await experiment._block(None)
                assert measurement.pop('output_hashes')==list(expected.values())
                row[mode]={'mean_ms':measurement['latency']['mean_ms'],'wall_ms':measurement['wall_ms']}
            pairs.append(row)
        effect=paired_effect([p['inline']['mean_ms'] for p in pairs],[p['precomputed_oracle']['mean_ms'] for p in pairs],seed=plan['seed'])
        result['cases'].append({'payload_bytes':size,'pairs':pairs,'oracle_minus_inline_effect':effect,'all_expected_outputs_equal':True})
        print(f'{size} bytes: no-hash oracle changes measured mean by {effect["mean_change_pct"]:+.1f}%',flush=True)
    target=ROOT/f'artifacts/output-probe-v{__version__}.json'
    target.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(target,flush=True)


if __name__=='__main__':asyncio.run(main())
