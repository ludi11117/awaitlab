"""Optional same-process loopback HTTP host for controlled ASGI experiments."""
import asyncio
from contextlib import asynccontextmanager,contextmanager
import socket
import sys
from .asgi import LocalASGITrace


@asynccontextmanager
async def serve_local(app, *, lifespan='on'):
    import httpx
    import uvicorn
    class EmbeddedServer(uvicorn.Server):
        @contextmanager
        def capture_signals(self):yield
        async def serve(self,**kwargs):
            try:await super().serve(**kwargs)
            except SystemExit as error:
                raise RuntimeError(f'Local ASGI server stopped before startup (Uvicorn exit {error.code})') from error
    bridge=LocalASGITrace()
    instrumented=bridge.middleware(app)
    lifespan_task=None;lifespan_failure=None
    async def application(scope,receive,send):
        nonlocal lifespan_task,lifespan_failure
        if scope['type']!='lifespan':return await instrumented(scope,receive,send)
        lifespan_task=asyncio.current_task()
        async def status(message):
            nonlocal lifespan_failure
            if message['type'] in ('lifespan.startup.failed','lifespan.shutdown.failed'):
                lifespan_failure=message.get('message') or message['type']
            await send(message)
        try:await instrumented(scope,receive,status)
        except BaseException as error:
            if lifespan_failure is None:lifespan_failure=f'{type(error).__name__}: {error}'
            raise
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as listener:
        listener.bind(('127.0.0.1',0))
        address=listener.getsockname()
        server=EmbeddedServer(uvicorn.Config(application,host='127.0.0.1',port=address[1],
            lifespan=lifespan,access_log=False,log_config=None,proxy_headers=False,ws='none',timeout_graceful_shutdown=2))
        task=asyncio.create_task(server.serve(sockets=[listener]))
        try:
            while not server.started:
                if task.done():
                    await task
                    raise RuntimeError('Local ASGI server stopped before startup')
                await asyncio.sleep(.005)
            async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{address[1]}',trust_env=False,timeout=10) as client:
                yield client,bridge
        finally:
            primary_error=sys.exc_info()[1]
            server.should_exit=True
            async def finish():
                await task
                if lifespan_task is not None:await lifespan_task
            closing=asyncio.create_task(finish())
            try:await asyncio.wait_for(asyncio.shield(closing),5)
            except BaseException as error:
                owned=[t for t in (task,lifespan_task,closing) if t is not None]
                for pending in owned:
                    if not pending.done():pending.cancel()
                await asyncio.gather(*owned,return_exceptions=True)
                if isinstance(error,asyncio.TimeoutError):
                    if primary_error is None:
                        raise RuntimeError('Local ASGI server did not shut down within the experiment deadline') from error
                elif primary_error is None or isinstance(error,asyncio.CancelledError):raise
            if lifespan_failure is not None and primary_error is None:
                raise RuntimeError(f'ASGI lifespan failed: {lifespan_failure}')
