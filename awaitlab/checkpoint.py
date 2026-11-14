"""Atomic paired-block checkpoints bound to declared workload and known code."""
import hashlib
import inspect
import json
import os
from pathlib import Path
import platform
from datetime import datetime,timezone


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def identity(workload,arms,settings,workload_version,source_files=()):
    if not workload_version or not isinstance(workload_version,str):
        raise ValueError('Checkpointing requires an explicit workload_version for data/config dependencies')
    paths=set(Path(__file__).parent.glob('*.py'))
    paths.update(Path(path).resolve() for path in source_files)
    for func in [workload]+[f for arm in arms for f in arm.replacements.values()]:
        source=inspect.getsourcefile(inspect.unwrap(func))
        if source:paths.add(Path(source).resolve())
    sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
    manifest={'checkpoint_schema':1,'workload_version':workload_version,'settings':settings,
        'arms':[{'name':a.name,'kind':a.kind,'site':a.site,'delay_ms':a.delay_ms,
                 'replacement_names':{k:f'{v.__module__}.{v.__qualname__}' for k,v in a.replacements.items()}} for a in arms],
        'sources':sources,'python':platform.python_version(),'platform':platform.platform()}
    return {'digest':digest(manifest),'manifest':manifest}


def now():return datetime.now(timezone.utc).isoformat()


def write(path,run_identity,pairs,schedule,status,started_at,error=None):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    state={'identity':run_identity,'status':status,'started_at':started_at,'updated_at':now(),
           'schedule':schedule,'pairs':pairs,'pairs_digest':digest(pairs),'error_type':error}
    temporary=path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(state,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    os.replace(temporary,path)


def load(path,expected_identity,schedule):
    state=json.loads(Path(path).read_text(encoding='utf-8'))
    if state.get('identity')!=expected_identity:
        raise ValueError('Checkpoint identity differs: code, settings, environment or workload_version changed; start a new run')
    if state.get('schedule')!=schedule or state.get('pairs_digest')!=digest(state.get('pairs')):
        raise ValueError('Checkpoint schedule or paired-block data checksum is invalid')
    expected={(p['block'],p['arm']) for p in schedule}
    actual=[]
    for name,pairs in state['pairs'].items():
        for pair in pairs:actual.append((pair['block'],name))
    if len(actual)!=len(set(actual)) or not set(actual)<=expected:
        raise ValueError('Checkpoint has duplicate or unknown completed pairs')
    return state
