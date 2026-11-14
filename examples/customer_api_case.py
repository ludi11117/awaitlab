"""Real customer API: lifespan resources, pooled HTTP client, explicit output scope."""
from contextlib import asynccontextmanager
from importlib.metadata import version
import time
import uuid
from awaitlab import Experiment,Settings
from awaitlab.experiment import fingerprint
from awaitlab.local_http import serve_local
from awaitlab import sqlite_workload as database


def business_output(response):
    """Choose the checked contract explicitly; dynamic metadata is outside it."""
    body=response.json()
    return {'status':response.status_code,'customers':body['customers']}


def make_workload(root=database.DEFAULT_ROOT,rows=database.DEFAULT_ROWS,workers=4,*,project=True,audit=None):
    @asynccontextmanager
    async def workload():
        from fastapi import FastAPI,Request
        state={'startups':0,'shutdowns':0,'requests':0,'client_closed':False,'pending_tickets':None}
        peers=set()
        if audit is not None:audit.append(state)
        @asynccontextmanager
        async def lifecycle(app):
            async with database.open_store(root,rows,workers) as store:
                app.state.store=store;state['startups']+=1
                try:yield
                finally:app.state.store=None
            state['shutdowns']+=1
        app=FastAPI(lifespan=lifecycle)
        @app.get('/customers')
        async def customer(email:str,request:Request):
            result=await database.lookup(app.state.store,email)
            state['requests']+=1;peers.add(request.client.port)
            return {**result,'metadata':{'request_id':uuid.uuid4().hex,'served_at_ns':time.time_ns()}}
        client=None;bridge=None
        try:
            async with serve_local(app) as (client,bridge):
                async def handler(i):
                    with bridge.headers() as headers:
                        response=await client.get('/customers',params={'email':database.request_key(i,rows)},headers=headers)
                    response.raise_for_status()
                    return business_output(response) if project else response.json()
                yield handler
        finally:
            state['pending_tickets']=bridge.pending_tickets if bridge else None
            state['client_closed']=client is not None and client.is_closed
            state['http_connections']=len(peers)
    return workload


# Only fixture fingerprints/configuration are imported; live resources open in lifespan.
fixture=database.prepare_fixture()
dependency_versions={name:version(name) for name in ('fastapi','httpx','uvicorn')}
lifecycle_audit=[]
experiment=Experiment(make_workload(audit=lifecycle_audit),database.ARMS,
    Settings(blocks=10,requests=24,concurrency=4,warmup=2))
workload_version=fingerprint({'protocol':'customer-http-projection-v1','fixture':fixture['manifest'],
    'sql':database.SQL,'dependency_versions':dependency_versions})
title='真实客户接口：生命周期资源、HTTP连接复用与显式业务输出核对'
transport='loopback TCP / HTTPX keep-alive / FastAPI lifespan / executor / SQLite'
output_contract='核对 HTTP 状态与完整 customers（id、name、balance）；接入代码明确排除 metadata.request_id 与 metadata.served_at_ns。未核对整个响应体。'
