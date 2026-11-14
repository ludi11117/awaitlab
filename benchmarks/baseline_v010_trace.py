import asyncio
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
import itertools
import time
import weakref

_session = ContextVar('awaitlab_session', default=None)
_parent = ContextVar('awaitlab_parent', default=None)
_request = ContextVar('awaitlab_request', default=None)


@dataclass(frozen=True)
class Record:
    id: int
    parent: int | None
    request: int | None
    task: int
    name: str
    kind: str
    start_ms: float
    duration_ms: float
    failed: bool


class Session:
    def __init__(self, delay_site=None, delay_ms=0, replacements=None,
                 trace_requests=2, max_records=4096):
        if delay_ms < 0 or trace_requests < 0 or max_records < 0:
            raise ValueError('Delay and trace limits must be nonnegative')
        self.delay_site, self.delay_ms = delay_site, delay_ms
        self.replacements = replacements or {}
        self.trace_requests, self.max_records = trace_requests, max_records
        self.records = []
        self.dropped_records = 0
        self.stats = {}
        self.interventions = 0
        self.replacement_calls = 0
        self.observed_injection_ms = 0.0
        self.max_injection_ms = 0.0
        self._ids = itertools.count(1)
        self._task_ids = weakref.WeakKeyDictionary()
        self._task_counter = itertools.count(1)
        self.start_ns = time.perf_counter_ns()

    def __enter__(self):
        self._token = _session.set(self)
        return self

    def __exit__(self, *_):
        _session.reset(self._token)

    @asynccontextmanager
    async def request(self, request_id):
        token = _request.set(request_id)
        parent_token = _parent.set(None)
        try:
            async with self.span('request', 'request'):
                yield
        finally:
            _parent.reset(parent_token)
            _request.reset(token)

    @asynccontextmanager
    async def span(self, name, kind='operation'):
        span_id = next(self._ids)
        parent_id = _parent.get()
        token = _parent.set(span_id)
        start = time.perf_counter_ns()
        failed = False
        try:
            yield
        except BaseException:
            failed = True
            raise
        finally:
            end = time.perf_counter_ns()
            _parent.reset(token)
            duration = (end-start)/1_000_000
            stats = self.stats.setdefault((name,kind), {'name':name,'kind':kind,'count':0,
                'total_ms':0.0,'max_ms':0.0,'failed':0})
            stats['count'] += 1
            stats['total_ms'] += duration
            stats['max_ms'] = max(stats['max_ms'],duration)
            stats['failed'] += failed
            rid = _request.get()
            if rid is not None and rid < self.trace_requests:
                if len(self.records) < self.max_records:
                    task = asyncio.current_task()
                    if task not in self._task_ids:
                        self._task_ids[task] = next(self._task_counter)
                    self.records.append(Record(span_id,parent_id,rid,self._task_ids[task],name,kind,
                                               (start-self.start_ns)/1_000_000,duration,failed))
                else:
                    self.dropped_records += 1

    def summaries(self):
        return [dict(s,mean_ms=s['total_ms']/s['count']) for s in
                sorted(self.stats.values(),key=lambda s:s['total_ms'],reverse=True)]


@asynccontextmanager
async def stage(name, kind='wait'):
    session = _session.get()
    if session is None:
        yield
    else:
        async with session.span(name,kind):
            yield


def operation(name):
    """Instrument one async operation. Replacements retain the original signature."""
    def decorate(func):
        @wraps(func)
        async def wrapped(*args,**kwargs):
            session = _session.get()
            if session is None:
                return await func(*args,**kwargs)
            async with session.span(name):
                target = session.replacements.get(name,func)
                if name in session.replacements:
                    session.replacement_calls += 1
                result = await target(*args,**kwargs)
                # Cooperative delay: this extends operation readiness, never blocks
                # the event-loop thread and never claims to emulate extra CPU work.
                if session.delay_site == name and session.delay_ms:
                    session.interventions += 1
                    delay_start = time.perf_counter_ns()
                    await asyncio.sleep(session.delay_ms/1000)
                    observed = (time.perf_counter_ns()-delay_start)/1_000_000
                    session.observed_injection_ms += observed
                    session.max_injection_ms = max(session.max_injection_ms,observed)
                return result
        wrapped.__awaitlab_name__ = name
        return wrapped
    return decorate
