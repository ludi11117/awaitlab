"""Remove repeated customer reads when enriching an ordered list of orders."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager,closing
import threading

from awaitlab import Arm,Experiment,Settings,operation
from awaitlab.sqlite_workload import DEFAULT_ROWS,prepare_fixture,readonly


SELECT='SELECT id,name,balance FROM customers WHERE email=? ORDER BY id'
BATCH_SIZE=256


def order_inputs(i,rows=DEFAULT_ROWS):
    # 48 orders share 12 existing customers and one missing customer.
    keys=[f'user-{(i*7919+j*37)%rows+1}@example.test' for j in range(12)]+['missing@example.test']
    return [{'id':i*1000+j,'customer_email':keys[j%13]} for j in range(48)]


def per_order(con,keys):
    return [[list(row) for row in con.execute(SELECT,(key,))] for key in keys]


def per_customer(con,keys):
    found={key:[list(row) for row in con.execute(SELECT,(key,))] for key in dict.fromkeys(keys)}
    return [found[key] for key in keys]


def batched(con,keys):
    unique=list(dict.fromkeys(keys));found={key:[] for key in unique}
    for start in range(0,len(unique),BATCH_SIZE):
        chunk=unique[start:start+BATCH_SIZE]
        sql='SELECT email,id,name,balance FROM customers WHERE email IN ('+','.join('?' for _ in chunk)+') ORDER BY id'
        for key,*row in con.execute(sql,chunk):found[key].append(row)
    return [found[key] for key in keys]


def read_orders(path,orders,reader=per_order):
    """One connection/read transaction per request; no cache survives this call."""
    selects=0
    def trace(sql):
        nonlocal selects
        if sql.lstrip().upper().startswith('SELECT'):selects+=1
    with closing(readonly(path)) as con:
        con.set_trace_callback(trace)
        con.execute('BEGIN')
        customers=reader(con,[order['customer_email'] for order in orders])
    output={'orders':[{'id':order['id'],'customer_email':order['customer_email'],'customers':customer}
                      for order,customer in zip(orders,customers)]}
    return output,selects


async def execute(store,orders,reader):
    output,count=await asyncio.get_running_loop().run_in_executor(store['executor'],read_orders,store['path'],orders,reader)
    # Counts cover all measured requests, not only sampled tracing requests.
    store['select_counts'].append(count)
    return output


@operation('orders.customers')
async def load_orders(store,orders):return await execute(store,orders,per_order)


async def deduplicated_orders(store,orders):return await execute(store,orders,per_customer)


async def batched_orders(store,orders):return await execute(store,orders,batched)


def make_workload(root=None,rows=DEFAULT_ROWS,workers=4,audit=None):
    @asynccontextmanager
    async def workload():
        fixture=await asyncio.to_thread(prepare_fixture,**({'root':root,'rows':rows} if root else {'rows':rows}))
        path=fixture['paths']['indexed']
        with ThreadPoolExecutor(max_workers=workers,thread_name_prefix='awaitlab-orders') as executor:
            loop=asyncio.get_running_loop();barrier=threading.Barrier(workers,timeout=10)
            def prime(i):
                for reader in (per_order,per_customer,batched):read_orders(path,order_inputs(i,rows),reader)
                barrier.wait()
            await asyncio.gather(*(loop.run_in_executor(executor,prime,i) for i in range(workers)))
            store={'path':path,'executor':executor,'select_counts':[]}
            async def handler(i):return await load_orders(store,order_inputs(i,rows))
            try:yield handler
            finally:
                if audit is not None:audit.append(list(store['select_counts']))
    return workload


ARMS=[Arm('deduplicate_customers','replacement','orders.customers',replacements={'orders.customers':deduplicated_orders}),
      Arm('batch_customers','replacement','orders.customers',replacements={'orders.customers':batched_orders}),
      Arm('unchanged_orders','replacement','orders.customers',replacements={'orders.customers':load_orders.__wrapped__},role='negative_control')]
query_audit=[]
experiment=Experiment(make_workload(audit=query_audit),ARMS,Settings(blocks=10,requests=16,concurrency=4,warmup=2))
workload_version='orders-48-existing-customers-12-missing-1-sqlite-v1'
title='订单客户补全：逐条查询 → 请求内去重 → 批量查询'
transport='真实SQLite只读事务；每请求一个连接、每块独立线程池，无跨请求缓存、无人为sleep'
output_contract='核对全部48条订单顺序、重复客户关联、客户完整行及缺失客户空列表；该负载逐条/去重/批量分别执行48/13/1次SELECT，逐请求实测明细见order-query-check-v1.json，不计BEGIN为业务查询。'
