"""Fixed follow-up protocol, executed against the installed 0.7.0 wheel.

Run from D: temp with PYTHONPATH pointing at installed-0.7.0 and python -S.
All configurations, repeats and the diagnostic p-value family are fixed below
before any measurements. This is not an adaptive search for a passing control.
"""
import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
from pathlib import Path
import platform
import random
import sys
import zipfile

import awaitlab
from awaitlab import Arm,Experiment,Settings,operation
from awaitlab.statistics import holm_adjust

ROOT=Path(__file__).resolve().parents[1]
TARGET=ROOT/'artifacts/negative-control-diagnosis-v0.7.0'
CONFIGS={'short':{'size':5000,'warmup':1,'trace_requests':2},
    'long':{'size':500000,'warmup':1,'trace_requests':2},
    'warmup50':{'size':5000,'warmup':50,'trace_requests':2},
    'unsampled':{'size':5000,'warmup':1,'trace_requests':0}}


def case(config):
    size=config['size']
    @operation('sum')
    async def total(i):return sum(range(size+i))
    async def formula(i):
        n=size+i
        return n*(n-1)//2
    @asynccontextmanager
    async def workload():yield total
    return Experiment(workload,[Arm('formula','replacement','sum',replacements={'sum':formula}),
        Arm('unchanged','replacement','sum',replacements={'sum':total.__wrapped__})],
        Settings(blocks=24,requests=8,concurrency=1,warmup=config['warmup'],
            trace_requests=config['trace_requests'],seed=173))


async def main():
    assert 'installed-0.7.0' in awaitlab.__file__,awaitlab.__file__
    assert awaitlab.__version__=='0.7.0'
    wheel=ROOT/'artifacts/wheels/awaitlab_local-0.7.0-py3-none-any.whl'
    installed=Path(awaitlab.__file__).parent.parent
    with zipfile.ZipFile(wheel) as archive:
        files=[name for name in archive.namelist() if name.startswith('awaitlab/')]
        assert all(archive.read(name)==(installed/name).read_bytes() for name in files)
    rng=random.Random(9137);schedule=[]
    for repeat in range(8):
        names=list(CONFIGS);rng.shuffle(names)
        schedule.extend({'repeat':repeat,'config':name} for name in names)
    plan={'sdk_version':'0.7.0','sdk_path':awaitlab.__file__,'packaged_files':len(files),
        'wheel_sha256':hashlib.sha256(wheel.read_bytes()).hexdigest(),
        'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'python':sys.version,'platform':platform.platform(),'configs':CONFIGS,'repeats_per_config':8,
        'experiment_settings':{'blocks':24,'requests':8,'concurrency':1,'seed':173},
        'schedule_seed':9137,'schedule':schedule,'diagnostic_family_size':32,
        'diagnostic_rule':'Holm over all 32 unchanged-arm raw p-values; alarm if p < .05 and abs(point change) >= 5%',
        'limits':['follow-up exploratory diagnosis, not replication of the old machine state',
            'all results retained; no seed search or extension until significance',
            'interventions change one setting relative to short, not all order/environment effects',
            'diagnostic family is separate from each run replacement family',
            'global Python/OS caches and background load are not reset']}
    TARGET.mkdir(parents=True,exist_ok=True);plan_path=TARGET/'plan.json'
    if plan_path.exists():assert json.loads(plan_path.read_text())==plan
    else:plan_path.write_text(json.dumps(plan,indent=2),encoding='utf-8')
    rows=[]
    for step in schedule:
        tag=step['config'];repeat=step['repeat'];config=CONFIGS[tag]
        experiment=case(config);target=TARGET/f'{tag}-{repeat+1:02d}.json'
        checkpoint=target.with_suffix('.checkpoint.json')
        report=await experiment.run(checkpoint=checkpoint,resume=checkpoint.exists(),
            workload_version=f'negative-control-diagnosis-v1-{tag}-{config["size"]}',source_files=[__file__])
        report['diagnosis']={'config':tag,'repeat':repeat,'protocol':str(plan_path)}
        target.write_text(json.dumps(report,indent=2),encoding='utf-8')
        c=next(c for c in report['comparisons'] if c['name']=='unchanged')
        row={'config':tag,'repeat':repeat,'report':target.name,'control_mean_ms':c['control_mean_ms'],
            'treatment_mean_ms':c['treatment_mean_ms'],'change_pct':c['effect']['mean_change_pct'],
            'raw_p':c['randomization']['pvalue'],'within_run_holm_p':c['holm_adjusted_p'],
            'within_run_supported':c['candidate_improvement'],'outputs_equal':c['output_equivalence']}
        rows.append(row)
        print(f'{tag} #{repeat+1}: {row["change_pct"]:+.2f}%, within-run supported={row["within_run_supported"]}',flush=True)
    adjusted=holm_adjust({f'{r["config"]}-{r["repeat"]}':r['raw_p'] for r in rows})
    for row in rows:
        row['diagnostic_global_holm_p']=adjusted[f'{row["config"]}-{row["repeat"]}']
        row['diagnostic_alarm']=row['diagnostic_global_holm_p']<.05 and abs(row['change_pct'])>=5
    summary={'plan':plan,'rows':rows,'all_outputs_equal':all(r['outputs_equal'] for r in rows),
        'counts':{tag:{'within_run_supported':sum(r['within_run_supported'] for r in rows if r['config']==tag),
            'diagnostic_alarms':sum(r['diagnostic_alarm'] for r in rows if r['config']==tag)} for tag in CONFIGS}}
    (TARGET/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary['counts'],indent=2),flush=True)


if __name__=='__main__':asyncio.run(main())
