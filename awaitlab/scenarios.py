import asyncio
from contextlib import asynccontextmanager
from .trace import operation,stage
from .experiment import Arm


@operation('inventory.lookup')
async def inventory(item):
    await asyncio.sleep(.012)
    return {'id':item,'available':True}


async def fast_inventory(item):
    await asyncio.sleep(.003)
    return {'id':item,'available':True}


@operation('pricing.quote')
async def pricing(order):
    await asyncio.sleep(.032)
    return {'total':order*2+100}


async def fast_pricing(order):
    await asyncio.sleep(.012)
    return {'total':order*2+100}


@asynccontextmanager
async def parallel():
    async def handler(i):
        stock,price=await asyncio.gather(asyncio.gather(*(inventory(x) for x in range(12))),pricing(i))
        return {'stock':stock,'price':price}
    yield handler


@operation('database.query')
async def query(i):
    await asyncio.sleep(.030)
    return {'id':i,'value':i*3}


async def fast_query(i):
    await asyncio.sleep(.008)
    return {'id':i,'value':i*3}


@asynccontextmanager
async def pool():
    semaphore=asyncio.Semaphore(2)
    async def handler(i):
        async with stage('database.pool_wait'):
            await semaphore.acquire()
        try:
            # Both the work and injected readiness delay hold the connection.
            # Moving this operation outside the semaphore changes the experiment.
            value=await query(i)
        finally:
            semaphore.release()
        return value
    yield handler


SCENARIOS={
    'parallel':{'factory':parallel,'title':'并行订单查询：累计最耗时未必最值得优化',
        'arms':[Arm('delay_inventory','delay','inventory.lookup',4),
                Arm('delay_pricing','delay','pricing.quote',4),
                Arm('faster_inventory','replacement','inventory.lookup',replacements={'inventory.lookup':fast_inventory}),
                Arm('faster_pricing','replacement','pricing.quote',replacements={'pricing.quote':fast_pricing})]},
    'pool':{'factory':pool,'title':'共享连接池：服务时间与排队放大',
        'arms':[Arm('delay_query','delay','database.query',4),
                Arm('faster_query','replacement','database.query',replacements={'database.query':fast_query})]}}

from . import sqlite_workload
SCENARIOS['sqlite']={'factory':sqlite_workload.make_workload(),
    'factory_for':lambda cfg:sqlite_workload.make_workload(workers=cfg.concurrency),
    'title':'真实 SQLite：相同数据的全表扫描与索引查询，包含不改实现的对照',
    'arms':sqlite_workload.ARMS,'prepare':sqlite_workload.evidence,'default_blocks':10}
from . import sqlite_http_workload
SCENARIOS['sqlite-http']={'factory':sqlite_http_workload.make_workload(),
    'factory_for':lambda cfg:sqlite_http_workload.make_workload(workers=cfg.concurrency),
    'title':'真实客户查询接口：通过 TCP 比较 SQLite 索引与原实现',
    'arms':sqlite_workload.ARMS,'prepare':sqlite_http_workload.evidence,'default_blocks':10}
