"""Optional same-process loopback HTTP host for controlled ASGI experiments."""
import asyncio
from contextlib import asynccontextmanager,contextmanager
import socket
from .asgi import LocalASGITrace


@asynccontextmanager
async def serve_local(app):
    import httpx
    import uvicorn
    class EmbeddedServer(uvicorn.Server):
        @contextmanager
        def capture_signals(self):yield
    bridge=LocalASGITrace()
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as listener:
        listener.bind(('127.0.0.1',0))
        address=listener.getsockname()
        server=EmbeddedServer(uvicorn.Config(bridge.middleware(app),host='127.0.0.1',port=address[1],
            lifespan='off',access_log=False,log_config=None,proxy_headers=False,ws='none',timeout_graceful_shutdown=2))
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
            server.should_exit=True
            try:await asyncio.wait_for(asyncio.shield(task),5)
            except TimeoutError:
                task.cancel();await asyncio.gather(task,return_exceptions=True)
                raise RuntimeError('Local ASGI server did not shut down within the experiment deadline')
            except asyncio.CancelledError:
                task.cancel();await asyncio.gather(task,return_exceptions=True)
                raise
