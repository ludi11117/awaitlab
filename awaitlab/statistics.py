import math
import random
import statistics


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
            'independent_units':'randomized paired workload blocks', 'blocks':len(pairs)}
