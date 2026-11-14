import asyncio
from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
import random
import statistics
import time
from . import __version__
from .trace import Session
from .statistics import describe,paired_effect,paired_randomization,holm_adjust,evidence_level
from .ownership import owned_tasks
from . import checkpoint as checkpoints


@dataclass(frozen=True)
class Arm:
    name: str
    kind: str  # delay | replacement
    site: str
    delay_ms: float = 0
    replacements: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Settings:
    blocks: int = 6
    requests: int = 40
    concurrency: int = 8
    warmup: int = 4
    seed: int = 173
    trace_requests: int = 2
    max_records: int = 4096
    min_gain_pct: float = 5.0
    alpha: float = .05

    def validate(self):
        if self.blocks<2 or self.requests<2 or self.concurrency<1 or self.warmup<0:
            raise ValueError('Need >=2 blocks and requests, positive concurrency, nonnegative warmup')
        if not 0<self.alpha<1 or not 0<=self.min_gain_pct<100:
            raise ValueError('alpha must be in (0,1), min_gain_pct must be in [0,100)')


def fingerprint(value):
    raw=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


class Experiment:
    def __init__(self, workload, arms, settings=None):
        """workload() is a fresh async context manager yielding handler(request_id)."""
        self.workload,self.arms,self.settings=workload,list(arms),settings or Settings()
        self.settings.validate()
        if not self.arms:raise ValueError('Need at least one experiment arm')
        names=[a.name for a in self.arms]
        if len(set(names))!=len(names) or 'control' in names:
            raise ValueError('Arm names must be unique; control is reserved')
        for arm in self.arms:
            if arm.kind not in ('delay','replacement') or (arm.kind=='delay' and (not math.isfinite(arm.delay_ms) or arm.delay_ms<=0)):
                raise ValueError('Use positive cooperative delay or actual replacement arms')
            if arm.kind=='replacement' and arm.site not in arm.replacements:
                raise ValueError('Replacement arm must replace its named site')
            if arm.kind=='replacement' and getattr(arm.replacements[arm.site],'__awaitlab_name__',None)==arm.site:
                raise ValueError('Pass an undecorated replacement; replacing a site with its own wrapper would recurse')

    async def _block(self, arm, trace=False):
        with owned_tasks() as tasks:
            try:
                result=await self._execute_block(arm,trace)
            finally:
                leaked=[t for t in tasks if not t.done()]
                for task in leaked:task.cancel()
                if leaked:await asyncio.gather(*leaked,return_exceptions=True)
        if leaked:
            raise RuntimeError('Workload leaked background tasks after teardown; cancelled them and rejected this block')
        return result

    async def _execute_block(self, arm, trace=False):
        cfg=self.settings
        async with self.workload() as handler:
            # Warm the same implementation under test, not the other arm's cache.
            with Session(delay_site=arm.site if arm and arm.kind=='delay' else None,
                         delay_ms=arm.delay_ms if arm else 0,
                         replacements=arm.replacements if arm else {},trace_requests=0):
                for i in range(cfg.warmup):
                    await handler(-i-1)
            session=Session(delay_site=arm.site if arm and arm.kind=='delay' else None,
                delay_ms=arm.delay_ms if arm else 0,replacements=arm.replacements if arm else {},
                trace_requests=cfg.trace_requests if trace else 0,max_records=cfg.max_records)
            latencies=[None]*cfg.requests;cycles=[None]*cfg.requests
            check_times=[None]*cfg.requests;outputs=[None]*cfg.requests
            jobs=iter(range(cfg.requests))
            async def worker():
                for i in jobs:
                    start=time.perf_counter_ns()
                    async with session.request(i):
                        value=await handler(i)
                    returned=time.perf_counter_ns()
                    latencies[i]=(returned-start)/1_000_000
                    outputs[i]=fingerprint(value)
                    checked=time.perf_counter_ns()
                    cycles[i]=(checked-start)/1_000_000
                    check_times[i]=(checked-returned)/1_000_000
            start=time.perf_counter_ns()
            with session:
                workers=[asyncio.create_task(worker()) for _ in range(min(cfg.concurrency,cfg.requests))]
                try:
                    await asyncio.gather(*workers)
                finally:
                    # A failed request must not leave other requests running into
                    # another arm's resources or measurements.
                    for task in workers:
                        if not task.done():task.cancel()
                    await asyncio.gather(*workers,return_exceptions=True)
            elapsed=(time.perf_counter_ns()-start)/1_000_000
        return {'latency':describe(latencies),'worker_cycle':describe(cycles),
                'output_check':{**describe(check_times),'total_ms':sum(check_times),
                    'share_of_worker_cycle_pct':100*sum(check_times)/sum(cycles),
                    'basis':'synchronous elapsed after handler returns, includes timing bookkeeping, before worker begins its next request; not isolated CPU time'},
                'wall_ms':elapsed,
                'interventions':session.interventions,'replacement_calls':session.replacement_calls,
                'injection':{'requested_ms':arm.delay_ms if arm and arm.kind=='delay' else 0,
                    'mean_observed_ms':session.observed_injection_ms/session.interventions if session.interventions else 0,
                    'max_observed_ms':session.max_injection_ms},
                'throughput_rps':cfg.requests*1000/elapsed,'output_hashes':outputs,
                'operations':session.summaries(), 'trace':[asdict(r) for r in session.records],
                'trace_dropped':session.dropped_records}

    async def run(self, progress=None, *, checkpoint=None, resume=False, workload_version=None):
        rng=random.Random(self.settings.seed)
        pairs={arm.name:[] for arm in self.arms}
        total=len(self.arms)*self.settings.blocks
        schedule=[]
        for block in range(self.settings.blocks):
            order=list(self.arms);rng.shuffle(order)
            for arm in order:
                sequence=[None,arm];rng.shuffle(sequence)
                schedule.append({'block':block,'arm':arm.name,'order':['treatment' if x else 'control' for x in sequence]})
        run_identity=checkpoints.identity(self.workload,self.arms,asdict(self.settings),workload_version) if checkpoint else None
        if resume and not checkpoint:raise ValueError('resume requires a checkpoint path')
        started_at=checkpoints.now()
        resumed_pairs=0
        if resume:
            previous=checkpoints.load(checkpoint,run_identity,schedule)
            pairs=previous['pairs'];started_at=previous['started_at']
            resumed_pairs=sum(len(p) for p in pairs.values())
        completed={(p['block'],name) for name,rows in pairs.items() for p in rows}
        done=len(completed)
        def save(status,error=None):
            if checkpoint:checkpoints.write(checkpoint,run_identity,pairs,schedule,status,started_at,error)
        save('running')
        by_name={a.name:a for a in self.arms}
        try:
            for planned in schedule:
                block,arm=planned['block'],by_name[planned['arm']]
                if (block,arm.name) in completed:continue
                measurements={}
                for mode in planned['order']:
                    measurements[mode]=await self._block(arm if mode=='treatment' else None,trace=block==0)
                control,treatment=measurements['control'],measurements['treatment']
                applied=treatment['interventions'] if arm.kind=='delay' else treatment['replacement_calls']
                if not applied:
                    raise ValueError(f'Arm {arm.name!r} did not reach instrumented site {arm.site!r}; no sensitivity conclusion is valid')
                control_hashes=control.pop('output_hashes')
                treatment_hashes=treatment.pop('output_hashes')
                mismatches=[i for i,(left,right) in enumerate(zip(control_hashes,treatment_hashes)) if left!=right]
                control['batch_output_hash']=fingerprint(control_hashes)
                treatment['batch_output_hash']=fingerprint(treatment_hashes)
                pairs[arm.name].append({'block':block,'order':planned['order'],
                    'control':control,'treatment':treatment,
                    'outputs_equal':not mismatches,'output_mismatch_ids':mismatches})
                done+=1
                save('running')
                if progress:progress(done,total,arm.name)
            if checkpoint and run_identity!=checkpoints.identity(self.workload,self.arms,asdict(self.settings),workload_version):
                raise RuntimeError('Source code changed during measurement; paired data retained but no final report is verified')
        except BaseException as exc:
            save('interrupted' if isinstance(exc,(asyncio.CancelledError,KeyboardInterrupt)) else 'failed',type(exc).__name__)
            raise
        save('complete')
        comparisons=[]
        for arm in self.arms:
            samples=pairs[arm.name]
            controls=[p['control']['latency']['mean_ms'] for p in samples]
            treatments=[p['treatment']['latency']['mean_ms'] for p in samples]
            effect=paired_effect(controls,treatments,self.settings.seed)
            equivalent=all(p['outputs_equal'] for p in samples)
            comparison={'name':arm.name,'kind':arm.kind,'site':arm.site,'delay_ms':arm.delay_ms,
                'control_mean_ms':statistics.fmean(controls),'treatment_mean_ms':statistics.fmean(treatments),
                'output_equivalence':equivalent,'effect':effect,
                'descriptive_p95_change_pct':100*(statistics.fmean(p['treatment']['latency']['p95_ms'] for p in samples)/
                    statistics.fmean(p['control']['latency']['p95_ms'] for p in samples)-1),
                'blocks':samples}
            if arm.kind=='delay':
                observed=statistics.fmean(p['treatment']['injection']['mean_observed_ms'] for p in samples)
                comparison['observed_injection_mean_ms']=observed
                comparison['sensitivity_ms_per_injected_ms']=effect['mean_delta_ms']/observed
                comparison['timer_overshoot_warning']=observed>arm.delay_ms*1.5
                comparison['interpretation']='response to extra cooperative delay; not an acceleration prediction'
            else:
                comparison['observed_gain']=equivalent and effect['mean_change_pct']<0
                comparison['randomization']=paired_randomization(controls,treatments,self.settings.seed)
                comparison['interpretation']='actual replacement under this workload; output equality is observed on tested request IDs only'
            comparisons.append(comparison)
        family={c['name']:c['randomization']['pvalue'] for c in comparisons if c['kind']=='replacement'}
        adjusted=holm_adjust(family)
        for c in comparisons:
            if c['kind']!='replacement':continue
            c['holm_adjusted_p']=adjusted[c['name']]
            c['evidence_level']=evidence_level(c['output_equivalence'],c['effect']['mean_change_pct'],
                c['holm_adjusted_p'],c['randomization']['exact'],self.settings.alpha,self.settings.min_gain_pct)
            c['candidate_improvement']=c['evidence_level']=='supported_in_this_experiment'
        return {'schema_version':4,'library_version':__version__,'settings':asdict(self.settings),'comparisons':comparisons,
            'measurement_basis':{'latency':'handler await including request trace; excludes its own output check',
                'worker_cycle':'handler plus synchronous output check, excluding the outer worker scheduling loop',
                'wall':'all workers, output checks and orchestration; excludes workload setup, warmup and teardown',
                'interference':'output checks can change request pacing and delay other tasks even when outside the current request timer'},
            'evidence_policy':{'family':list(family),'correction':'Holm, replacement arms only',
                'alpha':self.settings.alpha,'min_point_gain_pct':self.settings.min_gain_pct,
                'scope':'exploratory within-workload support; not preregistered confirmation or a lower bound on the practical margin',
                'monte_carlo_classification':'approximate p-values are reported but never classified as supported'},
            'run':{'started_at':started_at,'completed_at':checkpoints.now(),'identity':run_identity,'resumed_pairs':resumed_pairs},
            'method':'randomized paired closed-loop blocks; percentile bootstrap over block mean differences',
            'limitations':['cooperative readiness delay does not simulate CPU work',
                'delay sensitivity is not inverse speedup prediction',
                'output hash agreement on tested inputs does not prove semantic equivalence',
                'p95 changes are descriptive; no inferential tail-latency claim',
                'replacement p-values use Holm; all conclusions remain exploratory and workload-specific',
                'synchronous output checks affect closed-loop pacing and may delay other concurrent requests',
                'explicitly instrumented parent spans are not a complete await/dependency graph']}
