import asyncio
from contextlib import asynccontextmanager
import gc
import sys
import unittest
import weakref
from awaitlab import Arm,Experiment,Settings,operation
from awaitlab.ownership import owned_tasks


class OwnershipTests(unittest.IsolatedAsyncioTestCase):
    def experiment(self,workload):
        return Experiment(workload,[Arm('delay','delay','read',1)],Settings(blocks=2,requests=2,concurrency=1,warmup=0))

    async def test_lost_reference_task_survives_gc_and_is_rejected(self):
        refs=[];finalized=[];logs=[]
        loop=asyncio.get_running_loop();handler=loop.get_exception_handler()
        loop.set_exception_handler(lambda loop,context:logs.append(context['message']))
        async def orphan():
            try:await asyncio.Event().wait()
            finally:finalized.append(type(sys.exc_info()[1]).__name__)
        @operation('read')
        async def read(i):
            gc.collect()
            self.assertIsNotNone(refs[0]())
            return i
        @asynccontextmanager
        async def workload():
            task=asyncio.create_task(orphan());refs.append(weakref.ref(task));del task
            await asyncio.sleep(0)
            yield read
        try:
            with self.assertRaisesRegex(RuntimeError,'leaked background tasks'):
                await self.experiment(workload)._block(None)
            self.assertEqual(finalized,['CancelledError'])
            self.assertFalse(logs)
        finally:loop.set_exception_handler(handler)

    async def test_tasks_created_during_cancellation_are_also_cleaned(self):
        finalized=[]
        async def child():
            try:await asyncio.Event().wait()
            finally:finalized.append('child')
        async def parent():
            try:await asyncio.Event().wait()
            finally:asyncio.create_task(child());finalized.append('parent')
        @operation('read')
        async def read(i):return i
        @asynccontextmanager
        async def workload():
            asyncio.create_task(parent());await asyncio.sleep(0)
            yield read
        unrelated=asyncio.create_task(asyncio.Event().wait())
        try:
            with self.assertRaisesRegex(RuntimeError,'leaked background tasks'):
                await self.experiment(workload)._block(None)
            self.assertEqual(finalized,['parent','child'])
            self.assertFalse(unrelated.done())
        finally:
            unrelated.cancel();await asyncio.gather(unrelated,return_exceptions=True)

    async def test_completed_tasks_are_released_instead_of_retained(self):
        refs=[]
        async def done(i):return i
        with owned_tasks() as registry:
            for _ in range(8):
                batch=[asyncio.create_task(done(i)) for i in range(64)]
                refs.extend(weakref.ref(task) for task in batch)
                self.assertEqual(await asyncio.gather(*batch),list(range(64)))
                del batch
                await asyncio.sleep(0)
                self.assertFalse(registry)
            gc.collect()
            self.assertTrue(all(ref() is None for ref in refs))

    @unittest.skipUnless(hasattr(asyncio,'eager_task_factory'),'Requires Python 3.12+')
    async def test_existing_eager_factory_is_chained_and_restored(self):
        loop=asyncio.get_running_loop();previous=loop.get_task_factory()
        async def immediate():return 7
        loop.set_task_factory(asyncio.eager_task_factory)
        try:
            with owned_tasks() as registry:
                task=asyncio.create_task(immediate())
                self.assertTrue(task.done());self.assertEqual(await task,7)
                self.assertFalse(registry)
                pending=asyncio.create_task(asyncio.sleep(0))
                self.assertIn(pending,registry)
                await pending;await asyncio.sleep(0)
                self.assertFalse(registry)
            self.assertIs(loop.get_task_factory(),asyncio.eager_task_factory)
        finally:loop.set_task_factory(previous)


if __name__=='__main__':unittest.main()
