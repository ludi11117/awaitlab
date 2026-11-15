import asyncio
from contextlib import asynccontextmanager
from contextvars import ContextVar
import gc
import unittest
import weakref
from awaitlab import Arm,Experiment,Session,Settings,operation,stage
from awaitlab.trace import capture_context


class TraceLifetimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_cleanup_only_primary_does_not_prove_measured_reach(self):
        @operation('primary')
        async def primary(i):return i
        @operation('other')
        async def other(i):return i
        async def candidate(i):return i
        @asynccontextmanager
        async def workload():
            closing=asyncio.Event();task=None
            async def handler(i):
                nonlocal task
                if i==0:
                    async def late():await closing.wait();await primary(0)
                    task=asyncio.create_task(late())
                return await other(i)
            try:yield handler
            finally:
                closing.set()
                if task is not None:await task
        arm=Arm('bundle','replacement','primary',replacements={'primary':candidate,'other':candidate})
        with self.assertRaisesRegex(ValueError,"did not reach instrumented site 'primary'"):
            await Experiment(workload,[arm],Settings(blocks=2,requests=2,warmup=0)).run()

    async def test_captured_context_expires_and_cannot_revive_on_reentry(self):
        calls=[]
        @operation('read')
        async def read(i):calls.append(('original',i));return i
        async def candidate(i):calls.append(('replacement',i));return i
        session=Session(replacements={'read':candidate})
        with session:
            outer=capture_context()
            with session:
                inner=capture_context();await read(0)
            with inner.attach():
                self.assertIsNone(capture_context());await read(1)
            await read(2)
        with outer.attach():
            self.assertIsNone(capture_context());await read(3)
        with session:
            with outer.attach():await read(4)
            await read(5)
        self.assertEqual(calls,[('replacement',0),('original',1),('replacement',2),
            ('original',3),('original',4),('replacement',5)])
        self.assertEqual(session.replacement_calls_by_site,{'read':3})

    async def test_expired_context_records_no_new_spans_or_delay(self):
        @operation('read')
        async def read():return 7
        with Session(delay_site='read',delay_ms=1) as session:
            context=capture_context()
        before=list(session.summaries())
        with context.attach():
            self.assertEqual(await read(),7)
            async with stage('late observation'):pass
            with session.span('late direct span'):pass
        self.assertEqual(session.interventions,0)
        self.assertEqual(session.summaries(),before)

    async def test_operation_resuming_after_scope_exit_does_not_inject_delay(self):
        resume=asyncio.Event();entered=asyncio.Event()
        @operation('read')
        async def read():entered.set();await resume.wait();return 7
        with Session(delay_site='read',delay_ms=1) as session:
            task=asyncio.create_task(read());await entered.wait()
        resume.set();self.assertEqual(await task,7)
        self.assertEqual(session.interventions,0)

    async def test_expired_capture_does_not_retain_creator_task_context(self):
        marker=ContextVar('application_task')
        async def create():
            marker.set(asyncio.current_task())
            with Session():return capture_context()
        task=asyncio.create_task(create());context=await task;reference=weakref.ref(task)
        del task
        await asyncio.sleep(0);gc.collect()
        self.assertIsNone(reference())
        self.assertFalse(context.is_active)


if __name__=='__main__':unittest.main()
