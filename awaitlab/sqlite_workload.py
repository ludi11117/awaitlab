"""Real SQLite reads: identical table data, with/without an email index."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager,closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
from .trace import operation
from .experiment import Arm

DEFAULT_ROOT=Path('D:/CodexWork/temp/awaitlab/sqlite-fixture-v1')
DEFAULT_ROWS=50000
SQL='SELECT id, name, balance FROM customers WHERE email = ? ORDER BY id'


def file_digest(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda:source.read(65536),b''):digest.update(chunk)
    return digest.hexdigest()


def readonly(path):
    return sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)


def table_digest(path):
    digest=hashlib.sha256()
    with closing(readonly(path)) as con:
        for row in con.execute('SELECT id,email,name,balance FROM customers ORDER BY id'):
            digest.update(json.dumps(row,separators=(',',':')).encode()+b'\n')
    return digest.hexdigest()


def query_plan(path):
    with closing(readonly(path)) as con:
        return [list(row) for row in con.execute('EXPLAIN QUERY PLAN '+SQL,('user-17@example.test',))]


def prepare_fixture(root=DEFAULT_ROOT,rows=DEFAULT_ROWS):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    paths={'unindexed':root/f'customers-{rows}-unindexed.sqlite',
           'indexed':root/f'customers-{rows}-indexed.sqlite'}
    manifest_path=root/f'customers-{rows}.json'
    if manifest_path.exists():
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        if manifest['rows']!=rows or any(file_digest(paths[k])!=manifest['files'][k]['sha256'] for k in paths):
            raise ValueError('SQLite fixture changed; use a fresh fixture directory instead of mixing data')
    else:
        temporary=[]
        try:
            for _ in range(2):
                with tempfile.NamedTemporaryFile(dir=root,suffix='.sqlite',delete=False) as f:temporary.append(Path(f.name))
            with closing(sqlite3.connect(temporary[0])) as plain:
                plain.execute('CREATE TABLE customers (id INTEGER PRIMARY KEY,email TEXT NOT NULL,name TEXT NOT NULL,balance INTEGER NOT NULL)')
                plain.executemany('INSERT INTO customers VALUES (?,?,?,?)',
                    ((i,f'user-{i}@example.test',f'Customer {i}',(i*37)%100000) for i in range(1,rows+1)))
                plain.commit()
                with closing(sqlite3.connect(temporary[1])) as indexed:
                    plain.backup(indexed)
                    indexed.execute('CREATE INDEX idx_customer_email ON customers(email)')
                    indexed.commit()
            logical=[table_digest(p) for p in temporary]
            if logical[0]!=logical[1]:raise RuntimeError('SQLite fixtures do not contain identical logical rows')
            for key,path in zip(paths,temporary):os.replace(path,paths[key])
            manifest={'fixture_version':'sqlite-v1','rows':rows,'logical_data_sha256':logical[0],
                      'files':{k:{'sha256':file_digest(p),'bytes':p.stat().st_size} for k,p in paths.items()}}
            temp_manifest=manifest_path.with_suffix('.json.tmp')
            temp_manifest.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
            os.replace(temp_manifest,manifest_path)
        finally:
            for path in temporary:path.unlink(missing_ok=True)
    return {'paths':paths,'manifest':manifest,'sqlite_version':sqlite3.sqlite_version,
            'plans':{k:query_plan(p) for k,p in paths.items()}}


def read_customer(path,email):
    # Each executor thread creates and explicitly closes its own read-only connection.
    with closing(readonly(path)) as con:
        return {'customers':[list(row) for row in con.execute(SQL,(email,))]}


def request_key(i,rows):
    return 'missing@example.test' if i%7==0 else f'user-{(i*7919+17)%rows+1}@example.test'


@operation('customer.lookup')
async def lookup(store,email):
    return await asyncio.get_running_loop().run_in_executor(store['executor'],read_customer,store['paths']['unindexed'],email)


async def indexed_lookup(store,email):
    return await asyncio.get_running_loop().run_in_executor(store['executor'],read_customer,store['paths']['indexed'],email)


async def unchanged_lookup(store,email):
    return await asyncio.get_running_loop().run_in_executor(store['executor'],read_customer,store['paths']['unindexed'],email)


@asynccontextmanager
async def open_store(root=DEFAULT_ROOT,rows=DEFAULT_ROWS,workers=8):
    fixture=await asyncio.to_thread(prepare_fixture,root,rows)
    # Read both complete files, including index pages. This warms OS cache,
    # not a future connection's SQLite page cache.
    with ThreadPoolExecutor(max_workers=workers,thread_name_prefix='awaitlab-sqlite') as executor:
        loop=asyncio.get_running_loop();barrier=threading.Barrier(workers,timeout=10)
        def prime(index):
            order=['unindexed','indexed'] if index%2==0 else ['indexed','unindexed']
            for name in order:read_customer(fixture['paths'][name],request_key(index+1,rows))
            barrier.wait()
        await asyncio.gather(*(loop.run_in_executor(executor,prime,i) for i in range(workers)))
        yield {'paths':fixture['paths'],'executor':executor}
    # Executor shutdown also waits for SQLite work whose awaiting task cancelled.


def make_workload(root=DEFAULT_ROOT,rows=DEFAULT_ROWS,workers=8):
    @asynccontextmanager
    async def workload():
        async with open_store(root,rows,workers) as store:
            async def handler(i):return await lookup(store,request_key(i,rows))
            yield handler
    return workload


async def evidence():
    fixture=await asyncio.to_thread(prepare_fixture)
    return {'kind':'actual SQLite SELECT, no artificial sleep','rows':DEFAULT_ROWS,
            'sqlite_version':fixture['sqlite_version'],'sql':SQL,'fixture':fixture['manifest'],
            'query_plans':fixture['plans'],'connections':'fresh read-only connection per query',
            'cache_policy':'both complete files read before each block; new connections have new SQLite page caches',
            'thread_policy':'fresh executor per block, all configured workers primed before timing',
            'limits':['read-only synthetic customer data','warm OS cache, not guaranteed cold-disk performance',
                      'connection setup and executor queueing are included in lookup latency']}


ARMS=[Arm('indexed_lookup','replacement','customer.lookup',replacements={'customer.lookup':indexed_lookup}),
      Arm('unchanged_lookup','replacement','customer.lookup',replacements={'customer.lookup':unchanged_lookup},role='negative_control')]
