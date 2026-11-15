import math
import random
import statistics
from bisect import bisect_left

EXACT_MAX_BLOCKS=32


def quantile(values, p):
    if not values:
        raise ValueError('Cannot estimate a quantile from zero observations')
    ordered=sorted(values)
    position=(len(ordered)-1)*p
    left=math.floor(position);right=math.ceil(position)
    return ordered[left]+(ordered[right]-ordered[left])*(position-left)


def describe(values):
    return {'count':len(values),'mean_ms':statistics.fmean(values),
            'p50_ms':quantile(values,.5),'p95_ms':quantile(values,.95),'max_ms':max(values)}


def paired_effect(control, treatment, seed=73, resamples=2000):
    if len(control)!=len(treatment) or len(control)<2:
        raise ValueError('Paired inference needs at least two complete blocks')
    pairs=list(zip(control,treatment))
    delta=statistics.fmean(t-c for c,t in pairs)
    rng=random.Random(seed)
    bootstrap=[]
    for _ in range(resamples):
        sample=rng.choices(pairs,k=len(pairs))
        bootstrap.append(statistics.fmean(t-c for c,t in sample))
    return {'mean_delta_ms':delta,'ci95_delta_ms':[quantile(bootstrap,.025),quantile(bootstrap,.975)],
            'mean_change_pct':100*(statistics.fmean(treatment)/statistics.fmean(control)-1),
            'independent_units':'randomized paired workload blocks', 'blocks':len(pairs),
            'bootstrap':{'resamples':resamples,'seed':seed,'confidence':.95,'interval':'percentile'}}


def paired_randomization(control,treatment,seed=73,draws=20000):
    """Two-sided absolute mean statistic, swapping labels within paired blocks.

    Requires the random-order/sharp-null exchangeability assumptions stated in
    the method notes. Not a bootstrap p-value or a test of the practical margin.
    """
    if len(control)!=len(treatment) or len(control)<2:
        raise ValueError('Randomization test requires >=2 paired blocks')
    differences=[t-c for c,t in zip(control,treatment)]
    tolerance=max(max(map(abs,differences),default=0)*1e-12,1e-15)
    weights,cutoff=_integer_problem(differences,tolerance)
    exact=len(differences)<=EXACT_MAX_BLOCKS
    if exact:
        total=2**len(differences)
        extreme=_count_integer_tail(weights,cutoff)
    else:
        rng=random.Random(seed)
        signs=([rng.choice((-1,1)) for _ in differences] for _ in range(draws));total=draws
        extreme=sum(abs(sum(s*w for s,w in zip(sample,weights)))>=cutoff for sample in signs)
    p=extreme/total if exact else (extreme+1)/(total+1)
    return {'pvalue':p,'exact':exact,'assignments':total,'extreme_assignments':extreme,
            'seed':None if exact else seed,'tie_tolerance':tolerance,
            'statistic':'two-sided absolute sum of paired treatment-control differences',
            'sum_arithmetic':'exact integer-scaled input differences; tolerance applied before division',
            'algorithm':'meet_in_middle_integer' if exact else 'monte_carlo_integer',
            'null':'no arm effect, within-block labels exchangeable under the randomized order design'}


def _integer_problem(differences,tolerance):
    ratios=[value.as_integer_ratio() for value in differences]
    scale=math.lcm(*(denominator for _,denominator in ratios))
    weights=[numerator*(scale//denominator) for numerator,denominator in ratios]
    numerator,denominator=tolerance.as_integer_ratio()
    # |integer sum| >= |observed integer sum| - tolerance*scale.
    # Taking the ceiling of the right side is equivalent to this floor.
    cutoff=abs(sum(weights))-numerator*scale//denominator
    return weights,cutoff


def _signed_sums(weights):
    sums=[0]
    for weight in weights:
        sums=[value-weight for value in sums]+[value+weight for value in sums]
    return sums


def _count_integer_tail(weights,cutoff):
    if cutoff<=0:return 2**len(weights)
    middle=len(weights)//2
    left=_signed_sums(weights[:middle]);right=sorted(_signed_sums(weights[middle:]))
    # Global sign reversal bijects the positive and negative tails. For a
    # positive cutoff they are disjoint, so count only one and double it.
    return 2*sum(len(right)-bisect_left(right,cutoff-value) for value in left)


def holm_adjust(pvalues):
    """Holm step-down adjusted p-values for the declared comparison family."""
    result={};running=0.0;count=len(pvalues)
    for index,(name,p) in enumerate(sorted(pvalues.items(),key=lambda x:(x[1],x[0]))):
        if not 0<=p<=1:raise ValueError('Invalid p-value')
        running=max(running,(count-index)*p)
        result[name]=min(1.0,running)
    return result


def inference_design(blocks,family_size,alpha):
    """Best-case discrete resolution, not power or a sample-size guarantee.

    A two-sided sign-flip test includes the observed assignment and its global
    reversal. Holm cannot reject its first hypothesis below family_size times
    this p floor. Ties and zero differences can only increase that floor.
    """
    exact=blocks<=EXACT_MAX_BLOCKS
    raw_floor=2.0**(1-blocks) if exact and family_size else None
    holm_floor=min(1.0,family_size*raw_floor) if raw_floor is not None else None
    minimum=next((n for n in range(2,EXACT_MAX_BLOCKS+1)
        if min(1.0,family_size*2.0**(1-n))<alpha),None) if family_size else None
    status=('not_applicable' if not family_size else 'approximate_only' if not exact else
        'feasible' if holm_floor<alpha else 'resolution_limited')
    return {'status':status,'blocks':blocks,'replacement_family_size':family_size,'alpha':alpha,
        'exact_max_blocks':EXACT_MAX_BLOCKS,'raw_p_floor':raw_floor,'holm_p_floor':holm_floor,
        'minimum_exact_blocks':minimum,'support_possible':status=='feasible',
        'rule':'adjusted_p < alpha; exact test required; output and point-gain gates still apply',
        'scope':'best-case resolution only, not statistical power or a promise of support'}


def evidence_level(output_equal,change_pct,adjusted_p,exact,alpha,min_gain_pct):
    if not output_equal:return 'invalid_output'
    if change_pct>=0:return 'no_observed_gain'
    if -change_pct<min_gain_pct:return 'below_practical_threshold'
    if adjusted_p>=alpha or not exact:return 'inconclusive'
    return 'supported_in_this_experiment'
