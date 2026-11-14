import asyncio
import importlib.util
import unittest
from contextlib import asynccontextmanager
from unittest.mock import patch


@unittest.skipUnless(all(importlib.util.find_spec(m) for m in ['httpx','uvicorn']),
                     'Optional HTTP dependencies not installed')
class LocalHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def test_body_cancellation_survives_a_stuck_shutdown(self):
        from awaitlab.local_http import serve_local
        entered=asyncio.Event();stopped=asyncio.Event()
        class FakeServer:
            def __init__(self,config):self.started=False;self.should_exit=False
            async def serve(self,sockets):
                try:
                    self.started=True
                    await asyncio.Event().wait()
                finally:stopped.set()
        async def app(scope,receive,send):pass
        async def runner():
            async with serve_local(app):
                entered.set();await asyncio.Event().wait()
        real_wait=asyncio.wait_for
        async def bounded(future,timeout):return await real_wait(future,.02)
        with patch('uvicorn.Server',FakeServer),patch('awaitlab.local_http.asyncio.wait_for',bounded):
            task=asyncio.create_task(runner());await entered.wait();task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
        self.assertTrue(stopped.is_set())

    async def test_cancellation_during_shutdown_is_not_swallowed(self):
        from awaitlab.local_http import serve_local
        closing=asyncio.Event()
        class FakeServer:
            def __init__(self,config):self.started=False;self.should_exit=False
            async def serve(self,sockets):
                self.started=True
                while not self.should_exit:await asyncio.sleep(0)
                closing.set()
                await asyncio.Event().wait()
        async def app(scope,receive,send):pass
        async def runner():
            async with serve_local(app):pass
        with patch('uvicorn.Server',FakeServer):
            task=asyncio.create_task(runner())
            await closing.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task


@unittest.skipUnless(all(importlib.util.find_spec(m) for m in ['fastapi','httpx','uvicorn']),
                     'Optional FastAPI dependencies not installed')
class LifespanTests(unittest.IsolatedAsyncioTestCase):
    async def test_lifespan_orphan_is_cleaned_without_cancelling_foreign_task(self):
        import gc
        from fastapi import FastAPI
        from awaitlab import Arm,Experiment,Settings,operation
        from awaitlab.local_http import serve_local
        finalized=[]
        async def orphan():
            try:await asyncio.Event().wait()
            finally:finalized.append('cancelled')
        @asynccontextmanager
        async def lifecycle(app):
            asyncio.create_task(orphan())
            yield # deliberately missing application cleanup
        @operation('read')
        async def read():gc.collect();return {'ok':True}
        @asynccontextmanager
        async def workload():
            app=FastAPI(lifespan=lifecycle)
            app.get('/')(read)
            async with serve_local(app) as (client,bridge):
                async def handler(i):
                    with bridge.headers() as headers:response=await client.get('/',headers=headers)
                    return response.json()
                yield handler
        unrelated=asyncio.create_task(asyncio.Event().wait())
        try:
            experiment=Experiment(workload,[Arm('delay','delay','read',1)],Settings(blocks=2,requests=2,warmup=0))
            with self.assertRaisesRegex(RuntimeError,'leaked background tasks'):
                await experiment.run()
            self.assertEqual(finalized,['cancelled']);self.assertFalse(unrelated.done())
        finally:
            unrelated.cancel();await asyncio.gather(unrelated,return_exceptions=True)

    async def test_startup_failure_never_yields_a_client(self):
        from fastapi import FastAPI
        from awaitlab.local_http import serve_local
        closed=[]
        @asynccontextmanager
        async def lifecycle(app):
            try:raise RuntimeError('startup resource unavailable')
            finally:closed.append(True)
            yield
        with self.assertLogs('uvicorn.error',level='ERROR'):
            with self.assertRaisesRegex(RuntimeError,'stopped before startup'):
                async with serve_local(FastAPI(lifespan=lifecycle)):
                    self.fail('failed startup must not yield')
        self.assertEqual(closed,[True])

    async def test_startup_resource_is_ready_and_shutdown_runs(self):
        from fastapi import FastAPI,Request
        from awaitlab.local_http import serve_local
        events=[];ports=[]
        @asynccontextmanager
        async def lifecycle(app):
            events.append('open');app.state.resource={'ready':True}
            try:yield
            finally:app.state.resource.clear();events.append('close')
        app=FastAPI(lifespan=lifecycle)
        @app.get('/')
        async def read(request:Request):
            ports.append(request.client.port)
            return app.state.resource
        async with serve_local(app) as (client,bridge):
            for _ in range(3):self.assertEqual((await client.get('/')).json(),{'ready':True})
            self.assertEqual(events,['open'])
        self.assertEqual(events,['open','close'])
        self.assertEqual(len(set(ports)),1) # one persistent HTTP connection
        self.assertTrue(client.is_closed)

    async def test_shutdown_failure_rejects_the_measurement(self):
        from fastapi import FastAPI
        from awaitlab import Arm,Experiment,Settings,operation
        from awaitlab.local_http import serve_local
        @asynccontextmanager
        async def lifecycle(app):
            yield
            raise RuntimeError('cannot close test resource')
        @operation('value')
        async def value(i):return i
        app=FastAPI(lifespan=lifecycle)
        @app.get('/')
        async def read(i:int):return await value(i)
        @asynccontextmanager
        async def factory():
            async with serve_local(app) as (client,bridge):
                async def handler(i):
                    with bridge.headers() as headers:response=await client.get('/',params={'i':i},headers=headers)
                    return response.json()
                yield handler
        experiment=Experiment(factory,[Arm('delay','delay','value',1)],Settings(blocks=2,requests=2,warmup=0))
        with self.assertLogs('uvicorn.error',level='ERROR'):
            with self.assertRaisesRegex(RuntimeError,'ASGI lifespan failed'):
                await experiment.run()

    async def test_cancelled_startup_cleans_its_lifespan_task(self):
        from fastapi import FastAPI
        from awaitlab.local_http import serve_local
        entered=asyncio.Event();released=asyncio.Event()
        @asynccontextmanager
        async def lifecycle(app):
            entered.set()
            try:await asyncio.Event().wait();yield
            finally:released.set()
        app=FastAPI(lifespan=lifecycle)
        async def runner():
            async with serve_local(app):self.fail('startup should not complete')
        real_wait=asyncio.wait_for
        async def bounded(future,timeout):return await real_wait(future,.02)
        with self.assertLogs('uvicorn.error',level='ERROR'):
            with patch('awaitlab.local_http.asyncio.wait_for',bounded):
                task=asyncio.create_task(runner());await entered.wait();task.cancel()
                with self.assertRaises(asyncio.CancelledError):await task
        self.assertTrue(released.is_set())

    async def test_explicit_off_supports_http_only_asgi(self):
        from awaitlab.local_http import serve_local
        async def app(scope,receive,send):
            self.assertEqual(scope['type'],'http')
            await send({'type':'http.response.start','status':200,'headers':[]})
            await send({'type':'http.response.body','body':b'ok'})
        async with serve_local(app,lifespan='off') as (client,bridge):
            self.assertEqual((await client.get('/')).text,'ok')

    async def test_raw_asgi_shutdown_exception_cannot_be_hidden_by_server(self):
        from awaitlab.local_http import serve_local
        async def app(scope,receive,send):
            if scope['type']=='lifespan':
                self.assertEqual((await receive())['type'],'lifespan.startup')
                await send({'type':'lifespan.startup.complete'})
                self.assertEqual((await receive())['type'],'lifespan.shutdown')
                raise RuntimeError('raw ASGI cleanup failed')
            await send({'type':'http.response.start','status':200,'headers':[]})
            await send({'type':'http.response.body','body':b'ok'})
        with self.assertLogs('uvicorn.error',level='ERROR'):
            with self.assertRaisesRegex(RuntimeError,'raw ASGI cleanup failed'):
                async with serve_local(app) as (client,bridge):
                    self.assertEqual((await client.get('/')).text,'ok')


if __name__=='__main__':unittest.main()
