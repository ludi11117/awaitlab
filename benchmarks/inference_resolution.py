"""Finite resolution oracle; also a real stdlib CLI workload for the warning."""
from contextlib import asynccontextmanager
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from awaitlab import Arm,Experiment,Settings,operation,__version__
from awaitlab.statistics import inference_design,paired_randomization,holm_adjust

@operation('sum')
async def total(i):return sum(range(5000+i))

async def formula(i):
    n=5000+i
    return n*(n-1)//2

@asynccontextmanager
async def workload():yield total

experiment=Experiment(workload,[
    Arm('formula','replacement','sum',replacements={'sum':formula}),
    Arm('unchanged','replacement','sum',replacements={'sum':total.__wrapped__})],
    Settings(blocks=6,requests=8,concurrency=1,warmup=1))
workload_version='integer-sum-resolution-v1'
title='6配对/2候选：真实整数求和替换与检验分辨率'
output_contract='核对每个已测整数上界的完整求和值；公式是已知算法，不是自动生成优化。'


def main():
    rows=[]
    for blocks in range(2,13):
        p=paired_randomization([100]*blocks,[100-i for i in range(1,blocks+1)])['pvalue']
        for family in [1,2,3,8]:
            for alpha in [.01,.05,.0625,.1]:
                design=inference_design(blocks,family,alpha)
                adjusted=holm_adjust({str(i):p for i in range(family)})
                assert design['raw_p_floor']==p
                assert design['holm_p_floor']==min(adjusted.values())
                assert design['support_possible']==any(v<alpha for v in adjusted.values())
                rows.append(design)
    result={'version':__version__,'cases':len(rows),'plans':rows,
        'scope':'exact sign-flip enumerated for all-negative nonzero differences; Holm all-best-case family',
        'limits':['not statistical power','ties and zero effects can increase p',
            'minimum exact blocks does not promise support','strict adjusted_p < alpha matches current evidence policy']}
    target=ROOT/f'artifacts/inference-resolution-v{__version__}.json'
    target.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(f'{len(rows)} design cases matched enumerated p and actual Holm rules')


if __name__=='__main__':main()
