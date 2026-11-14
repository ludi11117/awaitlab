import argparse
import asyncio
import json
from pathlib import Path
import platform
import sys
from .experiment import Experiment,Settings
from .scenarios import SCENARIOS
from .calibration import calibrate
from .report import write_report


def main():
    parser=argparse.ArgumentParser(description='AwaitLab — asynchronous latency experiments, no model/API required')
    parser.add_argument('command',choices=['demo'])
    parser.add_argument('--scenario',choices=SCENARIOS,default='parallel')
    parser.add_argument('--blocks',type=int,default=6)
    parser.add_argument('--requests',type=int,default=40)
    parser.add_argument('--concurrency',type=int,default=8)
    parser.add_argument('--output',default=None)
    parser.add_argument('--resume',action='store_true',help='Resume completed pairs only if code/settings/workload identity match')
    args=parser.parse_args()
    scenario=SCENARIOS[args.scenario]
    settings=Settings(blocks=args.blocks,requests=args.requests,concurrency=args.concurrency)
    target=Path(args.output or f'D:/CodexWork/projects/awaitlab/artifacts/{args.scenario}-latest.json').resolve()
    target.parent.mkdir(parents=True,exist_ok=True)
    async def execute():
        calibration=await calibrate()
        report=await Experiment(scenario['factory'],scenario['arms'],settings).run(
            lambda done,total,name:print(f'[{done}/{total}] {name}',flush=True),
            checkpoint=target.with_suffix('.checkpoint.json'),resume=args.resume,workload_version='bundled-scenarios-v1')
        report['timer_calibration']=calibration
        return report
    report=asyncio.run(execute())
    report.update(scenario=args.scenario,title=scenario['title'],environment={'python':sys.version,'platform':platform.platform()})
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    html_target=write_report(report,target.with_suffix('.html'))
    for c in report['comparisons']:
        print(f'{c["name"]}: {c["effect"]["mean_change_pct"]:+.1f}% mean latency; equal outputs={c["output_equivalence"]}')
    print(f'Report: {target}')
    print(f'Interactive report: {html_target}')


if __name__=='__main__':main()
