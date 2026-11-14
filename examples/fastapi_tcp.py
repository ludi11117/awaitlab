"""Loopback TCP + HTTPX + Uvicorn + FastAPI, one process and one event loop."""
import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fastapi import FastAPI
from awaitlab import Arm,Experiment,Settings
from awaitlab.local_http import serve_local
from awaitlab.scenarios import inventory,pricing,fast_inventory,fast_pricing
from awaitlab.calibration import calibrate
from awaitlab.report import write_report


@asynccontextmanager
async def application():
    app=FastAPI()
    @app.get('/orders/{order_id}')
    async def order(order_id:int):
        stock,price=await asyncio.gather(asyncio.gather(*(inventory(i) for i in range(12))),pricing(order_id))
        return {'order':order_id,'stock':stock,'price':price}
    async with serve_local(app) as (client,bridge):
        async def handler(i):
            with bridge.headers() as headers:
                response=await client.get(f'/orders/{i}',headers=headers)
            response.raise_for_status()
            return response.json()
        yield handler


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
