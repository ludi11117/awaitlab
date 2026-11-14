"""Actual SQLite index comparison through loopback TCP and FastAPI."""
from contextlib import asynccontextmanager
from importlib.metadata import version
from .local_http import serve_local
from . import sqlite_workload as database


def make_workload(root=database.DEFAULT_ROOT,rows=database.DEFAULT_ROWS,workers=8):
    @asynccontextmanager
    async def workload():
        from fastapi import FastAPI
        async with database.open_store(root,rows,workers) as store:
            app=FastAPI()
            @app.get('/customers')
            async def customer(email:str):return await database.lookup(store,email)
            async with serve_local(app) as (client,bridge):
                async def handler(i):
                    with bridge.headers() as headers:
                        response=await client.get('/customers',params={'email':database.request_key(i,rows)},headers=headers)
                    response.raise_for_status();return response.json()
                yield handler
    return workload


async def evidence():
    data=await database.evidence()
    data['transport']='loopback TCP / HTTPX / Uvicorn / FastAPI / dedicated executor / SQLite'
    data['dependency_versions']={name:version(name) for name in ['fastapi','httpx','uvicorn']}
    data['limits'].append('single process and event loop; no remote or multi-worker service')
    return data
