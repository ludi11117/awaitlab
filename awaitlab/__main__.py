import argparse
import asyncio
import json
from pathlib import Path
import platform
import sys
from .experiment import Experiment,Settings,fingerprint
from .scenarios import SCENARIOS
from .calibration import calibrate
from .report import write_report


def main():
    parser=argparse.ArgumentParser(description='AwaitLab — asynchronous latency experiments, no model/API required')
    parser.add_argument('command',choices=['demo'])
    parser.add_argument('--scenario',choices=SCENARIOS,default='parallel')
    parser.add_argument('--blocks',type=int,default=None)
    parser.add_argument('--requests',type=int,default=40)
    parser.add_argument('--concurrency',type=int,default=8)
    parser.add_argument('--output',default=None,help='JSON path ending in .json; a sibling standalone HTML is also written')
    parser.add_argument('--resume',action='store_true',help='Resume completed pairs only if code/settings/workload identity match')
    args=parser.parse_args()
    scenario=SCENARIOS[args.scenario]
    settings=Settings(blocks=args.blocks if args.blocks is not None else scenario.get('default_blocks',6),requests=args.requests,concurrency=args.concurrency)
    try:settings.validate()
    except ValueError as exc:parser.error(str(exc))
    target=Path(args.output or f'D:/CodexWork/projects/awaitlab/artifacts/{args.scenario}-latest.json').resolve()
    if target.suffix.lower()!='.json':parser.error('--output must end in .json; the HTML report is generated alongside it')
    async def execute():
        evidence=await scenario['prepare']() if 'prepare' in scenario else None
        calibration=await calibrate()
        factory=scenario['factory_for'](settings) if 'factory_for' in scenario else scenario['factory']
        workload_version='bundled-scenarios-v1' if evidence is None else fingerprint(evidence)
        report=await Experiment(factory,scenario['arms'],settings).run(
            lambda done,total,name:print(f'[{done}/{total}] {name}',flush=True),
            checkpoint=target.with_suffix('.checkpoint.json'),resume=args.resume,workload_version=workload_version)
        report['timer_calibration']=calibration
        if evidence is not None:report['workload_evidence']=evidence
        if evidence and evidence.get('transport'):report['transport']=evidence['transport']
        return report
    try:
        target.parent.mkdir(parents=True,exist_ok=True)
        report=asyncio.run(execute())
    except KeyboardInterrupt:
        print('AwaitLab: 实验已中断，未生成本次完成报告。完整配对保存在断点中；代码与参数不变时可加 --resume。',file=sys.stderr)
        if target.exists():print(f'上一次完整数据未替换：{target}',file=sys.stderr)
        raise SystemExit(130)
    except (ValueError,RuntimeError,OSError,ImportError) as exc:
        print(f'AwaitLab: 实验未完成：{exc}',file=sys.stderr)
        if isinstance(exc,ImportError) and args.scenario=='sqlite-http':
            print('HTTP 场景需要 fastapi、httpx、uvicorn；标准库场景可使用 --scenario sqlite。',file=sys.stderr)
        if target.exists():print(f'上一次完整数据未替换：{target}',file=sys.stderr)
        print(f'断点路径：{target.with_suffix(".checkpoint.json")}',file=sys.stderr)
        raise SystemExit(1)
    report.update(scenario=args.scenario,title=scenario['title'],environment={'python':sys.version,'platform':platform.platform()})
    try:
        temporary=target.with_name(target.name+'.tmp')
        temporary.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        temporary.replace(target)
        html_target=write_report(report,target.with_suffix('.html'))
    except OSError as exc:
        print(f'AwaitLab: 测量已完成，但保存报告失败：{exc}',file=sys.stderr)
        print(f'请检查输出路径与权限：{target}；完整配对仍在断点中。',file=sys.stderr)
        raise SystemExit(1)
    for c in report['comparisons']:
        print(f'{c["name"]}: {c["effect"]["mean_change_pct"]:+.1f}% mean latency; equal outputs={c["output_equivalence"]}')
    print(f'Report: {target}')
    print(f'Interactive report: {html_target}')


if __name__=='__main__':main()
