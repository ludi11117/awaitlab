"""Loopback TCP + HTTPX + Uvicorn + FastAPI, one process and one event loop."""
import asyncio
from contextlib import asynccontextmanager,contextmanager
import json
from pathlib import Path
import socket
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fastapi import FastAPI
import httpx
import uvicorn
from awaitlab import Arm,Experiment,Settings
from awaitlab.asgi import LocalASGITrace
from awaitlab.scenarios import inventory,pricing,fast_inventory,fast_pricing
from awaitlab.calibration import calibrate
from awaitlab.report import write_report


class EmbeddedServer(uvicorn.Server):
    @contextmanager
    def capture_signals(self):
        # The enclosing experimental runner owns KeyboardInterrupt/cancellation.
        yield


@asynccontextmanager
async def application():
    bridge=LocalASGITrace()
    app=FastAPI()
    @app.get('/orders/{order_id}')
    async def order(order_id:int):
        stock,price=await asyncio.gather(asyncio.gather(*(inventory(i) for i in range(12))),pricing(order_id))
        return {'order':order_id,'stock':stock,'price':price}
    # Prebind an ephemeral loopback port, avoiding fixed-port collisions.
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as listener:
        listener.bind(('127.0.0.1',0))
        address=listener.getsockname()
        config=uvicorn.Config(bridge.middleware(app),host='127.0.0.1',port=address[1],
                              lifespan='off',access_log=False,log_config=None,
                              proxy_headers=False,ws='none',timeout_graceful_shutdown=2)
        server=EmbeddedServer(config)
        server_task=asyncio.create_task(server.serve(sockets=[listener]))
        try:
            while not server.started:
                if server_task.done():
                    await server_task
                    raise RuntimeError('Local ASGI server stopped before startup')
                await asyncio.sleep(.005)
            async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{address[1]}',
                                         trust_env=False,timeout=10) as client:
                async def handler(i):
                    with bridge.headers() as headers:
                        response=await client.get(f'/orders/{i}',headers=headers)
                    response.raise_for_status()
                    return response.json()
                yield handler
        finally:
            server.should_exit=True
            try:await asyncio.wait_for(asyncio.shield(server_task),5)
            except (TimeoutError,asyncio.CancelledError):
                server_task.cancel()
                await asyncio.gather(server_task,return_exceptions=True)


async def main():
    arms=[Arm('faster_inventory','replacement','inventory.lookup',replacements={'inventory.lookup':fast_inventory}),
          Arm('faster_pricing','replacement','pricing.quote',replacements={'pricing.quote':fast_pricing})]
    calibration=await calibrate()
    report=await Experiment(application,arms,Settings(blocks=6,requests=40,concurrency=8)).run(
        lambda done,total,name:print(f'[{done}/{total}] {name}',flush=True),
        checkpoint=ROOT/'artifacts/fastapi-tcp.checkpoint.json',workload_version='local-tcp-order-fixture-v1')
    report.update(scenario='fastapi-tcp',title='真实本机 TCP / HTTPX / Uvicorn / FastAPI 订单接口',
                  timer_calibration=calibration,
                  transport='loopback TCP, single process and event loop; one-use local context tickets')
    target=ROOT/'artifacts/fastapi-tcp.json'
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    write_report(report,target.with_suffix('.html'))
    for c in report['comparisons']:
        print(c['name'],round(c['effect']['mean_change_pct'],1),'%', 'outputs_equal=',c['output_equivalence'])
    print(target.with_suffix('.html'))


if __name__=='__main__':asyncio.run(main())
