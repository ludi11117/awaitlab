"""Real FastAPI routing + serialization, in-process ASGI transport (no socket).

Run from the project root: python examples/fastapi_lab.py
Optional existing dependencies: fastapi, httpx.
"""
import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from fastapi import FastAPI
from httpx import ASGITransport,AsyncClient
from awaitlab import Arm,Experiment,Settings
from awaitlab.scenarios import inventory,pricing,fast_inventory,fast_pricing
from awaitlab.report import write_report
from awaitlab.calibration import calibrate


@asynccontextmanager
async def application():
    app=FastAPI()
    @app.get('/orders/{order_id}')
    async def order(order_id:int):
        stock,price=await asyncio.gather(asyncio.gather(*(inventory(i) for i in range(12))),pricing(order_id))
        return {'order':order_id,'stock':stock,'price':price}
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://local-asgi') as client:
        async def handler(i):
            response=await client.get(f'/orders/{i}')
            response.raise_for_status()
            return response.json()
        yield handler


async def main():
    arms=[Arm('faster_inventory','replacement','inventory.lookup',replacements={'inventory.lookup':fast_inventory}),
          Arm('faster_pricing','replacement','pricing.quote',replacements={'pricing.quote':fast_pricing})]
    calibration=await calibrate()
    report=await Experiment(application,arms,Settings(blocks=6,requests=40,concurrency=8)).run(
        lambda done,total,name:print(f'[{done}/{total}] {name}',flush=True),
        checkpoint=ROOT/'artifacts/fastapi-asgi.checkpoint.json',workload_version='local-asgi-order-fixture-v1')
    report.update(scenario='fastapi-asgi',title='FastAPI 订单路由：路由、验证与响应序列化均参与测量',
                  timer_calibration=calibration,
                  transport='in-process ASGI; excludes TCP, uvicorn workers and external databases')
    path=ROOT/'artifacts/fastapi-asgi.json'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    write_report(report,path.with_suffix('.html'))
    for c in report['comparisons']:
        print(c['name'],round(c['effect']['mean_change_pct'],1),'%', 'outputs_equal=',c['output_equivalence'])
    print(path.with_suffix('.html'))


if __name__=='__main__':asyncio.run(main())
