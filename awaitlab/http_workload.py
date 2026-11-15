"""Compare existing GET/JSON services; only the client is owned by AwaitLab."""
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError,version
import asyncio
import json
import math
from urllib.parse import urlsplit
from .experiment import Arm,Experiment,fingerprint
from .trace import operation


def _origin(url):
    try:
        parsed=urlsplit(url);parsed.port
        valid=parsed.scheme in ('http','https') and parsed.hostname and not (
            parsed.username or parsed.password or parsed.fragment)
    except ValueError:valid=False
    if not valid or any(c in url.replace('{id}','') for c in '{}\r\n'):
        raise ValueError('Use an HTTP(S) URL without credentials/fragments; only {id} is supported')
    return f'{parsed.scheme}://{parsed.netloc}'


def make_experiment(before,after,settings,*,timeout=10,first_id=0,max_response_bytes=1048576):
    origins={'before':_origin(before),'after':_origin(after)}
    if not math.isfinite(timeout) or timeout<=0:raise ValueError('HTTP timeout must be positive and finite')
    if max_response_bytes<1:raise ValueError('HTTP response byte limit must be positive')
    versions={}
    for name in ['httpx','httpcore','anyio','h11','certifi']:
        try:versions[name]=version(name)
        except PackageNotFoundError:versions[name]='not installed'

    async def get(client,url,i,label):
        import httpx
        request_id=first_id+(i if i>=0 else (-i-1)%settings.requests)
        async def receive():
            async with client.stream('GET',url.replace('{id}',str(request_id)),headers={'Accept-Encoding':'identity'}) as response:
                if not 200<=response.status_code<300:
                    raise RuntimeError(f'HTTP {label} returned status {response.status_code}; measurement rejected')
                content=bytearray()
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    if len(content)+len(chunk)>max_response_bytes:
                        raise RuntimeError(f'HTTP {label} response exceeds {max_response_bytes} bytes')
                    content.extend(chunk)
                return response.status_code,content
        try:status,content=await asyncio.wait_for(receive(),timeout=timeout)
        except (asyncio.TimeoutError,httpx.HTTPError,httpx.InvalidURL) as error:
            raise RuntimeError(f'HTTP {label} request failed ({type(error).__name__})') from error
        try:body=json.loads(content)
        except ValueError as error:raise RuntimeError(f'HTTP {label} response is not JSON') from error
        return {'status':status,'body':body}

    @operation('http.get')
    async def original(client,i):return await get(client,before,i,'before')

    async def candidate(client,i):return await get(client,after,i,'after')

    @asynccontextmanager
    async def workload():
        import httpx
        from .local_http import _client_ssl_context
        async with httpx.AsyncClient(timeout=timeout,trust_env=False,verify=_client_ssl_context(),
                limits=httpx.Limits(max_connections=settings.concurrency,max_keepalive_connections=settings.concurrency)) as client:
            async def handler(i):return await original(client,i)
            yield handler

    experiment=Experiment(workload,[
        Arm('http_candidate','replacement','http.get',replacements={'http.get':candidate}),
        Arm('http_control','replacement','http.get',replacements={'http.get':original.__wrapped__},role='negative_control')],settings)
    spec={'method':'GET','origins':origins,'url_sha256':{'before':fingerprint(before),'after':fingerprint(after)},
        'id_template':{'before':'{id}' in before,'after':'{id}' in after},
        'receive_deadline_seconds':timeout,'max_response_bytes':max_response_bytes,'first_id':first_id,'ids_per_block':settings.requests,
        'warmup':'reuse IDs from the measured range','dependency_versions':versions,
        'boundary':'fresh client and connection pool per block; external service state/caches are not reset',
        'timing':'client response, JSON decoding and tracing; not server-internal timing'}
    return experiment,spec
