import asyncio
import importlib.util
import unittest
from unittest.mock import patch


@unittest.skipUnless(all(importlib.util.find_spec(m) for m in ['httpx','uvicorn']),
                     'Optional HTTP dependencies not installed')
class LocalHTTPTests(unittest.IsolatedAsyncioTestCase):
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


if __name__=='__main__':unittest.main()
