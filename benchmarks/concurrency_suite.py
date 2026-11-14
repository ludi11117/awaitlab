"""Fixed exploratory protocol, sequential cases; never search for a passing seed."""
import argparse
import asyncio
from contextlib import suppress
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from awaitlab import Experiment,Settings,__version__
from awaitlab.experiment import fingerprint
from awaitlab.report import write_report
from awaitlab.scenarios import SCENARIOS


async def main(resume=False):
    folder=ROOT/f'artifacts/concurrency-v1-{__version__}';folder.mkdir(parents=True,exist_ok=True)
    plan={'protocol':'sqlite-concurrency-v1','scenario_order':['sqlite','sqlite-http'],
        'concurrency_order':[1,4,8],'blocks':10,'requests':32,'warmup':4,'seed':173,
        'library_version':__version__,'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'scope':'each case is exploratory; Holm covers replacement arms within a case, not the entire sweep'}
    plan_path=folder/'plan.json'
    if resume and (not plan_path.exists() or json.loads(plan_path.read_text(encoding='utf-8'))!=plan):
        raise ValueError('Sweep plan differs or is missing; do not combine runs from different protocols')
    plan_path.write_text(json.dumps(plan,indent=2),encoding='utf-8')
    summary={'plan':plan,'state':'running','environment':{'python':sys.version,'platform':platform.platform()},'cases':[]}
    summary_path=folder/'summary.json'
    for scenario_name in plan['scenario_order']:
        scenario=SCENARIOS[scenario_name]
        evidence=await scenario['prepare']()
        for concurrency in plan['concurrency_order']:
            settings=Settings(blocks=plan['blocks'],requests=plan['requests'],concurrency=concurrency,
                warmup=plan['warmup'],seed=plan['seed'])
            name=f'{scenario_name}-c{concurrency}';path=folder/(name+'.json')
            checkpoint=path.with_suffix('.checkpoint.json')
            print(f'Start {name}: {settings.blocks} paired blocks, {settings.requests} requests',flush=True)
            # psutil is an optional benchmark instrument, never a core dependency.
            peak=None;sampler=None
            try:
                import psutil
                process=psutil.Process();peak=process.memory_info().rss
                async def sample_memory():
                    nonlocal peak
                    while True:
                        peak=max(peak,process.memory_info().rss)
                        await asyncio.sleep(.05)
                sampler=asyncio.create_task(sample_memory())
            except ImportError:pass
            started=time.perf_counter()
            try:
                report=await Experiment(scenario['factory_for'](settings),scenario['arms'],settings).run(
                    checkpoint=checkpoint,resume=resume and checkpoint.exists(),
                    workload_version=fingerprint({'evidence':evidence,'plan':plan,'concurrency':concurrency}))
            finally:
                if sampler:
                    sampler.cancel()
                    with suppress(asyncio.CancelledError):await sampler
            report.update(scenario=scenario_name,title=f'{scenario["title"]} · 并发 {concurrency}',
                environment=summary['environment'],workload_evidence=evidence)
            if evidence.get('transport'):report['transport']=evidence['transport']
            path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            write_report(report,path.with_suffix('.html'))
            case={'name':name,'concurrency':concurrency,'scenario':scenario_name,'seconds':time.perf_counter()-started,
                'process_rss_peak_mib':peak/1024**2 if peak else None,
                'memory_scope':'50ms samples of the whole benchmark process; includes imports, driver and prior cases; not isolated service memory',
                'comparisons':[{k:c[k] for k in ['name','control_mean_ms','treatment_mean_ms','effect',
                    'holm_adjusted_p','evidence_level','output_equivalence']} for c in report['comparisons']]}
            summary['cases'].append(case)
            summary_path.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
            print(f'Done {name}: '+', '.join(f'{c["name"]} {c["effect"]["mean_change_pct"]:+.1f}%' for c in report['comparisons']),flush=True)
    summary['state']='complete'
    summary_path.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Summary: {summary_path}',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resume',action='store_true')
    args=parser.parse_args()
    asyncio.run(main(args.resume))
