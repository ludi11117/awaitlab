import argparse
import asyncio
import importlib
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
    commands=parser.add_subparsers(dest='command',required=True)
    demo=commands.add_parser('demo',help='Run a bundled workload')
    demo.add_argument('--scenario',choices=SCENARIOS,default='parallel')
    demo.add_argument('--blocks',type=int,default=None)
    demo.add_argument('--requests',type=int,default=40)
    demo.add_argument('--concurrency',type=int,default=8)
    custom=commands.add_parser('run',help='Run a local Python module exporting experiment and workload_version')
    custom.add_argument('module',help='Importable dotted Python module, e.g. examples.unique_case')
    for command in [demo,custom]:
        command.add_argument('--output',default=None,help='JSON path ending in .json; a sibling standalone HTML is also written')
        command.add_argument('--resume',action='store_true',help='Resume completed pairs only if code/settings/workload identity match')
    args=parser.parse_args()
    if args.command=='demo':
        scenario=SCENARIOS[args.scenario]
        settings=Settings(blocks=args.blocks if args.blocks is not None else scenario.get('default_blocks',6),requests=args.requests,concurrency=args.concurrency)
        try:settings.validate()
        except ValueError as exc:parser.error(str(exc))
        label=args.scenario
    else:
        if not all(part.isidentifier() for part in args.module.split('.')):parser.error('Use an importable dotted Python module name')
        label=args.module
    target=Path(args.output or f'D:/CodexWork/projects/awaitlab/artifacts/{label}-latest.json').resolve()
    if target.suffix.lower()!='.json':parser.error('--output must end in .json; the HTML report is generated alongside it')
    async def execute():
        evidence=None;source_files=()
        if args.command=='demo':
            evidence=await scenario['prepare']() if 'prepare' in scenario else None
            factory=scenario['factory_for'](settings) if 'factory_for' in scenario else scenario['factory']
            experiment=Experiment(factory,scenario['arms'],settings)
            workload_version='bundled-scenarios-v1' if evidence is None else fingerprint(evidence)
            metadata={'scenario':args.scenario,'title':scenario['title']}
        else:
            sys.path.insert(0,str(Path.cwd()))
            module=importlib.import_module(args.module)
            experiment=getattr(module,'experiment',None)
            workload_version=getattr(module,'workload_version',None)
            if not isinstance(experiment,Experiment):raise ValueError('The module must export experiment = Experiment(...)')
            if not isinstance(workload_version,str) or not workload_version.strip():
                raise ValueError('The module must export a nonempty workload_version for external data/config')
            source_files=(module.__file__,) if getattr(module,'__file__',None) else ()
            metadata={'scenario':'custom','title':str(getattr(module,'title',args.module)),'workload_module':args.module}
            for field in ('transport','output_contract'):
                if hasattr(module,field):metadata[field]=str(getattr(module,field))
        calibration=await calibrate() if any(arm.kind=='delay' for arm in experiment.arms) else None
        report=await experiment.run(
            lambda done,total,name:print(f'[{done}/{total}] {name}',flush=True),
            checkpoint=target.with_suffix('.checkpoint.json'),resume=args.resume,workload_version=workload_version,source_files=source_files)
        if calibration is not None:report['timer_calibration']=calibration
        if evidence is not None:report['workload_evidence']=evidence
        if evidence and evidence.get('transport'):report['transport']=evidence['transport']
        report.update(**metadata,environment={'python':sys.version,'platform':platform.platform()})
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
        if isinstance(exc,ImportError) and getattr(args,'scenario',None)=='sqlite-http':
            print('HTTP 场景需要 fastapi、httpx、uvicorn；标准库场景可使用 --scenario sqlite。',file=sys.stderr)
        if target.exists():print(f'上一次完整数据未替换：{target}',file=sys.stderr)
        print(f'断点路径：{target.with_suffix(".checkpoint.json")}',file=sys.stderr)
        raise SystemExit(1)
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
