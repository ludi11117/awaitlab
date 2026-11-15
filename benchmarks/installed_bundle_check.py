"""Run with the wheel on PYTHONPATH and python -S, outside the repository."""
import asyncio
import json
from pathlib import Path
import subprocess
import sys
import awaitlab

ROOT=Path(__file__).resolve().parents[1]
version=awaitlab.__version__
assert f'installed-{version}' in awaitlab.__file__,awaitlab.__file__
assert not any('site-packages' in p for p in sys.path)
folder=Path(f'D:/CodexWork/temp/awaitlab/bundle-user-case-{version}')
folder.mkdir(parents=True,exist_ok=True)
source=(ROOT/'examples/events_bundle_case.py').read_text(encoding='utf-8').replace(
    'Settings(blocks=10,requests=8,concurrency=1,warmup=1)',
    'Settings(blocks=2,requests=3,concurrency=1,warmup=0)')
entry=folder/'bundle_case.py';entry.write_text(source,encoding='utf-8')
target=folder/'measured.json'
command=[sys.executable,'-S','-m','awaitlab','run','bundle_case','--output',str(target)]
subprocess.run(command,cwd=folder,capture_output=True,encoding='utf-8',check=True)
before=json.loads(target.read_text(encoding='utf-8'))
subprocess.run(command+['--resume'],cwd=folder,capture_output=True,encoding='utf-8',check=True)
after=json.loads(target.read_text(encoding='utf-8'))
assert after['run']['resumed_pairs']==6 and before['comparisons']==after['comparisons']
assert all(c['output_equivalence'] for c in after['comparisons'])
bundle=next(c for c in after['comparisons'] if c['name']=='unique_and_count')
assert bundle['replacement_sites']==['events.unique','events.count']
for b in bundle['blocks']:
    assert b['treatment']['replacement_calls']==6
    assert b['treatment']['replacement_calls_by_site']=={'events.unique':3,'events.count':3}

# The benchmark path is already on sys.path. Loading these probes must not
# replace the SDK that was imported from the installed wheel above.
from replacement_reach import probe,scope_probe
from awaitlab import Experiment
from awaitlab import trace
async def check():
    observed={mode:await probe(Experiment,mode) for mode in
        ['unreached','warmup_only','observational_span','cleanup_only']}
    assert all(v['outcome']=='rejected' for v in observed.values())
    expired=await scope_probe(trace)
    assert expired['calls']==['original'] and not expired['recapture_after_exit']
    return observed,expired
observed,expired=asyncio.run(check())
assert f'installed-{version}' in trace.__file__
result={'version':version,'installed_path':awaitlab.__file__,'site_packages_disabled':True,
    'resumed_pairs':6,'comparisons_unchanged':True,'all_outputs_equal':True,
    'bundle_sites':bundle['replacement_sites'],'counts_per_treatment_block':{'events.unique':3,'events.count':3},
    'negative_reach_probes':observed,'expired_capture':expired}
(ROOT/f'artifacts/install-bundle-check-v{version}.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print('Installed bundle: 6 pairs resumed; per-site counts retained; 4 negative reach probes rejected')
