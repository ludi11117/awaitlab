"""Real integer-event algorithms: compare separate and combined replacements."""
from collections import Counter
from contextlib import asynccontextmanager
from awaitlab import Arm,Experiment,Settings,operation


@operation('events.unique')
async def unique(events):
    result=[]
    for event in events:
        if event not in result:result.append(event)
    return result


@operation('events.count')
async def counts(events,ids):
    return [[event,events.count(event)] for event in ids]


async def hash_unique(events):return list(dict.fromkeys(events))


async def counter_counts(events,ids):
    histogram=Counter(events)
    return [[event,histogram[event]] for event in ids]


@asynccontextmanager
async def workload():
    async def handler(i):
        events=[(j*7919+i*13)%1000 for j in range(3000)]
        ids=await unique(events)
        return {'unique_ids':ids,'counts':await counts(events,ids)}
    yield handler


experiment=Experiment(workload,[
    Arm('only_unique','replacement','events.unique',replacements={'events.unique':hash_unique}),
    Arm('only_count','replacement','events.count',replacements={'events.count':counter_counts}),
    Arm('unique_and_count','replacement','events.unique',replacements={
        'events.unique':hash_unique,'events.count':counter_counts})],
    Settings(blocks=10,requests=8,concurrency=1,warmup=1))
workload_version='events-3000-1000-unique-frequency-v1'
title='真实事件计算：分别替换去重、计数，以及组合替换'
output_contract='核对全部保序unique_ids与每个ID的频次；组合臂同时替换两个操作，收益属于整个配置。'
