"""Independent Fraction enumeration and analytic large-n distributions."""
from fractions import Fraction
from collections import Counter
import hashlib
import itertools
import json
import math
from pathlib import Path
import random
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import baseline_v064_statistics as before
from awaitlab import statistics as current,__version__


def reference(values,tolerance):
    values=list(map(Fraction,values));cutoff=abs(sum(values))-Fraction(tolerance)
    return sum(abs(sum(sign*v for sign,v in zip(signs,values)))>=cutoff
        for signs in itertools.product((-1,1),repeat=len(values)))


def main():
    rng=random.Random(519);cases=[]
    for _ in range(96):
        n=rng.randrange(2,11)
        cases.append([rng.choice([0.,.1,-.3,.5,1e-8,-1e-8]) for _ in range(n)])
    for small in [math.nextafter(5e-13,-math.inf),5e-13,math.nextafter(5e-13,math.inf)]:
        cases.append([1.0,small])
    rows=[]
    for values in cases:
        result=current.paired_randomization([0.]*len(values),values)
        expected=reference(values,result['tie_tolerance'])
        assert result['extreme_assignments']==expected
        old=before.paired_randomization([0.]*len(values),values)
        rows.append({'differences':values,'fraction_oracle_extreme':expected,
            'current':result,'frozen_rounded_p':old['pvalue']})
    analytic=[]
    for n,negative,zeros in [(32,5,0),(31,3,1),(20,4,12),(32,0,0)]:
        values=[1]*negative+[-1]*(n-negative)+[0]*zeros
        result=current.paired_randomization([0.]*(n+zeros),values)
        expected=2*sum(math.comb(n,k) for k in range(negative+1))*2**zeros
        assert result['extreme_assignments']==expected
        analytic.append({'n_nonzero':n,'negative_or_positive_minority':negative,'zeros':zeros,
            'binomial_extreme':expected,'current':result})
    boundary=[r for r in rows if r['current']['pvalue']!=r['frozen_rounded_p']]
    fixture=[100.+(i%5-2)*.2-.15-100. for i in range(32)]
    distribution=Counter({Fraction(0):1})
    for value in map(Fraction,fixture):
        next_distribution=Counter()
        for partial,multiplicity in distribution.items():
            next_distribution[partial-value]+=multiplicity
            next_distribution[partial+value]+=multiplicity
        distribution=next_distribution
    result=current.paired_randomization([0.]*32,fixture)
    cutoff=abs(sum(map(Fraction,fixture)))-Fraction(result['tie_tolerance'])
    extreme=sum(m for value,m in distribution.items() if abs(value)>=cutoff)
    assert sum(distribution.values())==2**32 and extreme==result['extreme_assignments']
    dp={'blocks':32,'fraction_states':len(distribution),'assignments':2**32,'fraction_extreme':extreme,'current':result}
    record={'version':__version__,'source_sha256':hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest(),
        'fraction_cases':len(rows),'fraction_results':rows,'analytic_large_n':analytic,'fraction_distribution_dp':dp,
        'rounded_boundary_differences':boundary,
        'limits':['input differences are already-rounded treatment-control values',
            'integer accumulation intentionally replaces rounded-fsum tail boundaries',
            'tolerance unchanged in magnitude, applied to exact sum before division',
            'finite checks and analytic cases do not prove business causal assumptions']}
    target=ROOT/f'artifacts/integer-tail-validation-v{__version__}.json'
    target.write_text(json.dumps(record,indent=2),encoding='utf-8')
    print(f'{len(rows)} Fraction cases and {len(analytic)} large-n binomial oracles passed; {len(boundary)} rounded boundary differences recorded')


if __name__=='__main__':main()
