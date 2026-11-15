"""Compare audit-source validation cost against unchanged 0.13 source."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import statistics
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from awaitlab import __version__
from awaitlab.code_audit import audit_source

BASELINE_SHA='3d1e5028ba8fda9e14718a355e4dc9259c13062cb71e751c312819d079182918'


def fixture(count):
    return ''.join(f'def f{i}(value):\n    if value is None:\n        return None\n    if value is not None:\n        return value\n\n' for i in range(count))


def measured(function,source):
    start=time.perf_counter();result=function(source,'cost-fixture.py')
    return (time.perf_counter()-start)*1000,result


def load_baseline():
    path=ROOT/'benchmarks/baseline_v013_code_audit.py'
    assert hashlib.sha256(path.read_bytes()).hexdigest()==BASELINE_SHA
    spec=importlib.util.spec_from_file_location('awaitlab._frozen_audit_v013',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.audit_source


def main():
    parser=argparse.ArgumentParser();mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--gate-ms',type=float);mode.add_argument('--corpus',action='store_true');args=parser.parse_args()
    if args.gate_ms is not None:
        elapsed,(findings,_)=measured(audit_source,fixture(200))
        assert len(findings)==200 and all(item['patch_available'] for item in findings)
        print(json.dumps({'version':__version__,'guards':200,'elapsed_ms':elapsed,'local_gate_ms':args.gate_ms}))
        raise SystemExit(int(elapsed>=args.gate_ms))
    baseline=load_baseline();rng=random.Random(173);records=[]
    if args.corpus:
        paths=subprocess.run(['git','ls-files','--cached','--others','--exclude-standard','-z','--','*.py'],
            cwd=ROOT,capture_output=True,check=True).stdout.decode('utf-8').split('\0')
        names=sorted(set(name for name in paths if name));count=0
        for name in names:
            source=(ROOT/name).read_text(encoding='utf-8')
            old=baseline(source,name);new=audit_source(source,name)
            assert old==new,name
            count+=len(new[0])
        record={'version':__version__,'baseline_source_sha256':BASELINE_SHA,'files':names,
            'files_compared':len(names),'diagnostics_compared':count,'diagnostics_and_patched_sources_identical':True,
            'scope':'Current Git-listed Python corpus, including intentional diagnostic examples; no targets executed.'}
        (ROOT/f'artifacts/audit-validation-equivalence-v{__version__}.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8',newline='\n')
        print('Frozen baseline equivalence:',len(names),'files,',count,'diagnostics, exact proposed sources equal')
        return
    for count in (20,100,200):
        source=fixture(count);runs=[]
        for pair in range(3):
            order=['baseline','current'];rng.shuffle(order);values={};results={}
            for name in order:values[name],results[name]=measured(baseline if name=='baseline' else audit_source,source)
            assert results['baseline']==results['current']
            runs.append({'order':order,'ms':values})
        before=statistics.median(row['ms']['baseline'] for row in runs)
        after=statistics.median(row['ms']['current'] for row in runs)
        records.append({'guards':count,'runs':runs,'median_ms':{'baseline':before,'current':after},
            'change_pct':100*(after/before-1),'diagnostics_and_patched_source_identical':True})
    fallback=fixture(3)+'def blocked(value):\n    if value is not None:\n        if value is None:\n            return 1\n'
    old_ms,old_result=measured(baseline,fallback);new_ms,new_result=measured(audit_source,fallback)
    assert old_result==new_result
    record={'version':__version__,'baseline_source_sha256':BASELINE_SHA,'baseline_commit':'2cd76b224030bad0b31d9328b5d3984067e50e0c',
        'records':records,'fallback':{'baseline_ms':old_ms,'current_ms':new_ms,'results_identical':True},
        'limits':['Constructed scan workload, not application response latency.',
            'Three descriptive timing pairs per size; no inferential performance guarantee.',
            'Mixed rejected edits may still require sequential validation.']}
    (ROOT/f'artifacts/audit-validation-cost-v{__version__}.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8',newline='\n')
    for row in records:print(row['guards'],row['median_ms'],'change_pct',round(row['change_pct'],2))


if __name__=='__main__':main()
