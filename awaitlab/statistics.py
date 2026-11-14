import math
import random
import statistics
import itertools


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
    observed=abs(math.fsum(differences))
    tolerance=max(max(map(abs,differences),default=0)*1e-12,1e-15)
    exact=len(differences)<=16
    if exact:
        signs=itertools.product((-1,1),repeat=len(differences));total=2**len(differences)
    else:
        rng=random.Random(seed)
        signs=([rng.choice((-1,1)) for _ in differences] for _ in range(draws));total=draws
    extreme=sum(abs(math.fsum(s*d for s,d in zip(sample,differences)))>=observed-tolerance for sample in signs)
    p=extreme/total if exact else (extreme+1)/(total+1)
    return {'pvalue':p,'exact':exact,'assignments':total,'extreme_assignments':extreme,
            'seed':None if exact else seed,'tie_tolerance':tolerance,
            'statistic':'two-sided absolute sum of paired treatment-control differences',
            'null':'no arm effect, within-block labels exchangeable under the randomized order design'}


def holm_adjust(pvalues):
    """Holm step-down adjusted p-values for the declared comparison family."""
    result={};running=0.0;count=len(pvalues)
    for index,(name,p) in enumerate(sorted(pvalues.items(),key=lambda x:(x[1],x[0]))):
        if not 0<=p<=1:raise ValueError('Invalid p-value')
        running=max(running,(count-index)*p)
        result[name]=min(1.0,running)
    return result


def evidence_level(output_equal,change_pct,adjusted_p,exact,alpha,min_gain_pct):
    if not output_equal:return 'invalid_output'
    if change_pct>=0:return 'no_observed_gain'
    if -change_pct<min_gain_pct:return 'below_practical_threshold'
    if adjusted_p>=alpha or not exact:return 'inconclusive'
    return 'supported_in_this_experiment'
