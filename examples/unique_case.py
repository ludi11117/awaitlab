"""User-module example: preserve event order while removing duplicate integer IDs."""
from contextlib import asynccontextmanager
from awaitlab import Arm,Experiment,Settings,operation


@operation('events.unique')
async def list_unique(events):
    result=[]
    for event in events:
        if event not in result:result.append(event)
    return result


async def hash_unique(events):
    return list(dict.fromkeys(events))


@asynccontextmanager
async def workload():
    async def handler(request_id):
        events=[(i*7919+request_id*13)%1000 for i in range(3000)]
        return {'event_ids':await list_unique(events)}
    yield handler


experiment=Experiment(workload,[Arm('ordered_hash_set','replacement','events.unique',
    replacements={'events.unique':hash_unique})],Settings(blocks=10,requests=12,concurrency=1,warmup=2))
workload_version='synthetic-events-3000-values-1000-unique-v1'
title='按首次出现顺序去重：线性扫描列表与哈希表，真实算法替换'
