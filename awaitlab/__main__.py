import argparse
import asyncio
import importlib
import json
from pathlib import Path
import platform
import sys
from dataclasses import asdict
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
    http=commands.add_parser('http',help='Compare two existing GET endpoints with complete JSON output checks')
    http.add_argument('--before',required=True,help='Original URL; optional {id} expands to a stable request ID')
    http.add_argument('--after',required=True,help='Candidate URL; optional {id} uses the same request IDs')
    http.add_argument('--workload-version',required=True,help='Label both service builds and fixture; change when external code/data changes')
    http.add_argument('--blocks',type=int,default=10)
    http.add_argument('--requests',type=int,default=40)
    http.add_argument('--concurrency',type=int,default=8)
    http.add_argument('--timeout',type=float,default=10,help='Deadline in seconds to receive each complete response; synchronous JSON decoding is not preempted')
    http.add_argument('--max-response-bytes',type=int,default=1048576,help='Decoded body limit per response (default 1 MiB), not a process-memory bound')
    http.add_argument('--first-id',type=int,default=0)
    for command in [demo,custom,http]:
        command.add_argument('--plan',action='store_true',help='Inspect settings and inference resolution without executing the workload; custom modules are still imported')
        command.add_argument('--output',default=None,help='JSON path ending in .json; a sibling standalone HTML is also written')
        command.add_argument('--resume',action='store_true',help='Resume completed pairs only if code/settings/workload identity match')
    args=parser.parse_args()
    if args.command=='demo':
        scenario=SCENARIOS[args.scenario]
        blocks=args.blocks if args.blocks is not None else scenario.get('default_blocks',6)
        label=args.scenario
    elif args.command=='http':
        if not args.workload_version.strip():parser.error('HTTP comparison requires a nonempty workload version for external service code/data')
        blocks=args.blocks;label='http'
    else:
        if not all(part.isidentifier() for part in args.module.split('.')):parser.error('Use an importable dotted Python module name')
        label=args.module
    if args.command in ('demo','http'):
        settings=Settings(blocks=blocks,requests=args.requests,concurrency=args.concurrency)
        try:settings.validate()
        except ValueError as exc:parser.error(str(exc))
    target=Path(args.output or f'D:/CodexWork/projects/awaitlab/artifacts/{label}-latest.json').resolve()
    if target.suffix.lower()!='.json':parser.error('--output must end in .json; the HTML report is generated alongside it')
    async def execute():
        evidence=None;source_files=()
        if args.command=='http':
            from .http_workload import make_experiment
            experiment,spec=make_experiment(args.before,args.after,settings,timeout=args.timeout,first_id=args.first_id,
                max_response_bytes=args.max_response_bytes)
            workload_version=fingerprint({'external_version':args.workload_version,'request':spec})
            metadata={'scenario':'http','title':'现有HTTP接口：原实现与候选实现的实际对比',
                'http_request':spec,'external_workload_version':args.workload_version,
                'transport':'HTTPX GET / 已运行的外部服务；每块新客户端，不重启服务或清除服务缓存',
                'output_contract':'核对HTTP状态码与完整JSON；不自动忽略时间戳、随机ID或任何字段。仅接受2xx JSON响应。'}
        elif args.command=='demo':
            factory=scenario['factory_for'](settings) if 'factory_for' in scenario else scenario['factory']
            experiment=Experiment(factory,scenario['arms'],settings)
            metadata={'scenario':args.scenario,'title':scenario['title']}
        else:
            sys.path.insert(0,str(Path.cwd()))
            module=importlib.import_module(args.module)
            config=vars(module)
            experiment=config.get('experiment')
            workload_version=config.get('workload_version')
            if not isinstance(experiment,Experiment):raise ValueError('The module must export experiment = Experiment(...)')
            if not isinstance(workload_version,str) or not workload_version.strip():
                raise ValueError('The module must export a nonempty workload_version for external data/config')
            source_files=(module.__file__,)
            metadata={'scenario':'custom','title':args.module,'workload_module':args.module}
            for field in ('title','transport','output_contract'):
                if field in config:
                    if not isinstance(config[field],str):raise ValueError(f'Optional module field {field!r} must be a string; omit it to use the default')
                    metadata[field]=config[field]
        design=experiment.inference_design()
        if args.plan:
            plan={'settings':asdict(experiment.settings),'inference_design':design,
                'replacement_family':[arm.name for arm in experiment.arms if arm.kind=='replacement'],
                'replacement_roles':{arm.name:arm.role for arm in experiment.arms if arm.kind=='replacement'},
                'workload_executed':False,'scope':'imports custom module; does not call bundled prepare, workload, calibration, or checkpoint'}
            if args.command=='http':plan['http_request']=spec
            print(json.dumps(plan,ensure_ascii=False,indent=2))
            return None
        if design['status']=='resolution_limited':
            minimum=design['minimum_exact_blocks']
            extra=f'同一预定比较组至少需{minimum}批次才具备理论分辨率；' if minimum else '当前精确检验范围内没有可行批次数；'
            print(f'AwaitLab: 检验分辨率不足：{design["blocks"]}配对批次、{design["replacement_family_size"]}个替换比较的最佳Holm p={design["holm_p_floor"]:g}，规则要求p < {design["alpha"]:g}。{extra}增加每批请求数不能消除该限制。这不是功效保证，请在新实验前固定方案，勿补样直到显著。',file=sys.stderr,flush=True)
        elif design['status']=='approximate_only':
            print(f'AwaitLab: 当前{design["blocks"]}批次超过精确枚举上限{design["exact_max_blocks"]}；近似p仍报告，本版本不会自动标为支持。请在新实验前确定统计方案，勿从已测数据截取较少批次。',file=sys.stderr,flush=True)
        if args.command=='demo':
            evidence=await scenario['prepare']() if 'prepare' in scenario else None
            workload_version='bundled-scenarios-v1' if evidence is None else fingerprint(evidence)
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
        if not args.plan:target.parent.mkdir(parents=True,exist_ok=True)
        report=asyncio.run(execute())
    except KeyboardInterrupt:
        print('AwaitLab: 实验已中断，未生成本次完成报告。完整配对保存在断点中；代码与参数不变时可加 --resume。',file=sys.stderr)
        if target.exists():print(f'上一次完整数据未替换：{target}',file=sys.stderr)
        raise SystemExit(130)
    except (ValueError,RuntimeError,OSError,ImportError) as exc:
        print(f'AwaitLab: 实验未完成：{exc}',file=sys.stderr)
        if isinstance(exc,ImportError) and getattr(args,'scenario',None)=='sqlite-http':
            print('HTTP 场景需要 fastapi、httpx、uvicorn；标准库场景可使用 --scenario sqlite。',file=sys.stderr)
        if isinstance(exc,ImportError) and args.command=='http':
            print('此命令需要httpx；在项目目录可用 python -m pip install ".[http]" 安装可选依赖。',file=sys.stderr)
        if target.exists():print(f'上一次完整数据未替换：{target}',file=sys.stderr)
        print(f'断点路径：{target.with_suffix(".checkpoint.json")}',file=sys.stderr)
        raise SystemExit(1)
    if report is None:return
    try:
        temporary=target.with_name(target.name+'.tmp')
        temporary.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        temporary.replace(target)
        html_target=write_report(report,target.with_suffix('.html'))
    except OSError as exc:
        print(f'AwaitLab: 测量已完成，但保存报告失败：{exc}',file=sys.stderr)
        print(f'请检查输出路径与权限：{target}；完整配对仍在断点中。',file=sys.stderr)
        raise SystemExit(1)
    if report['quality']['status']=='warning':
        print('AwaitLab: 负面对照出现变化或输出不一致，本轮暂停推荐候选收益；请检查实验条件并独立复验。原始效应与p值保留。',file=sys.stderr)
    for c in report['comparisons']:
        control_note=f'; negative_control={c["control_status"]}' if c['role']=='negative_control' else ''
        print(f'{c["name"]}: {c["effect"]["mean_change_pct"]:+.1f}% mean latency; equal outputs={c["output_equivalence"]}{control_note}')
    print(f'Report: {target}')
    print(f'Interactive report: {html_target}')


if __name__=='__main__':main()
