"""Apply reviewed findings to the active index, guarded by full source identity."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from . import __version__
from .git_index import GitReader,audit_index


def load_report(path):
    report=json.loads(Path(path).read_text(encoding='utf-8'))
    types={'patch_root':str,'scan_target':str,'scan_root':str,'exclude_patterns':list,
        'errors':list,'sources':dict,'index_snapshot':dict,'patch':str}
    if (not isinstance(report,dict) or report.get('kind')!='defensive_code_audit' or
            report.get('source_scope')!='git_index' or
            any(not isinstance(report.get(key),kind) for key,kind in types.items()) or
            any(not isinstance(pattern,str) for pattern in report['exclude_patterns'])):
        raise ValueError('需要完整的暂存区审查JSON报告；请重新 audit --staged --output 报告.json')
    if report.get('library_version')!=__version__:raise ValueError('报告工具版本不同，请重新审查')
    if report['errors']:raise ValueError('报告存在扫描错误，请先解决错误并重新审查')
    return report


def verify_report(report):
    live=audit_index(report['scan_target'],exclude=report['exclude_patterns'])
    fields=('patch_root','scan_root','scan_target','index_snapshot','sources','patch')
    if live['errors'] or any(live[field]!=report[field] for field in fields):
        raise ValueError('暂存区版本或补丁与报告不一致，请重新审查；未应用补丁')
    return live


def entries(reader):
    result={}
    for row in reader.read('ls-files','--stage','-z').split(b'\0'):
        if row:
            metadata,name=row.split(b'\t',1);mode,oid,stage=metadata.split()
            result[name,stage]=(mode,oid)
    return result


def verify_result(before,reader,report):
    after=entries(reader)
    changed={name.encode('utf-8'):source['patched_sha256'] for name,source in report['sources'].items()
        if 'patched_sha256' in source}
    if before.keys()!=after.keys():raise ValueError('补丁意外增删暂存条目，未应用补丁')
    selected=[]
    for key,(mode,oid) in after.items():
        name,stage=key
        if name in changed and stage==b'0':
            if before[key][0]!=mode:raise ValueError('补丁意外改变文件模式，未应用补丁')
            selected.append((name.decode('utf-8'),oid.decode('ascii'),mode.decode('ascii')))
        elif before[key]!=(mode,oid):raise ValueError('补丁意外改变其他暂存条目，未应用补丁')
    def check_blob(name,oid,mode,data):
        if hashlib.sha256(data).hexdigest()!=changed[name.encode('utf-8')]:
            raise ValueError(f'补丁结果与已复核源码不一致：{name}；未应用补丁')
    reader.visit_blobs(selected,check_blob)
    return len(selected)


def owned_lock(path,identity):
    try:current=path.stat()
    except FileNotFoundError:return False
    return (current.st_dev,current.st_ino)==identity


def apply_index(path,*,check=False):
    report=load_report(path);reader=GitReader(Path(report['patch_root']))
    if check:
        live=verify_report(report)
        if live['patch']:reader.read('apply','--cached','--check','-',input=live['patch'].encode('utf-8'))
        snapshot=live['index_snapshot']
        if (reader.head_oid()!=snapshot['base_head'] or
                hashlib.sha256(reader.staged_diff(snapshot['base_head'])).hexdigest()!=snapshot['diff_sha256']):
            raise ValueError('核验期间HEAD或暂存区发生变化，请重新审查')
        return sum('patched_sha256' in source for source in live['sources'].values())
    index=reader.index_path();lock=index.with_name(index.name+'.lock')
    try:descriptor=os.open(lock,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o666)
    except FileExistsError:raise ValueError(f'Git暂存区被占用：{lock}；请等待其他Git操作结束') from None
    info=os.fstat(descriptor);identity=(info.st_dev,info.st_ino)
    try:
        with os.fdopen(descriptor,'wb') as destination:
            live=verify_report(report)
            if not live['patch']:return 0
            original=index.read_bytes();before=entries(reader)
            temp_root=Path('D:/CodexWork/temp/awaitlab');temp_root.mkdir(parents=True,exist_ok=True)
            with tempfile.TemporaryDirectory(dir=temp_root,prefix='index-apply-') as directory:
                copy=Path(directory)/'index';shutil.copy2(index,copy)
                alternate=GitReader(reader.root);alternate.env['GIT_INDEX_FILE']=str(copy)
                alternate.read('-c','core.splitIndex=false','update-index','--no-split-index')
                alternate.read('-c','core.splitIndex=false','apply','--cached','--whitespace=nowarn','-',
                    input=live['patch'].encode('utf-8'))
                count=verify_result(before,alternate,live)
                if index.read_bytes()!=original or reader.head_oid()!=live['index_snapshot']['base_head']:
                    raise ValueError('应用期间HEAD或暂存区发生变化，未应用补丁')
                with copy.open('rb') as source:shutil.copyfileobj(source,destination)
                destination.flush();os.fsync(destination.fileno())
                os.chmod(lock,index.stat().st_mode)
        if not owned_lock(lock,identity):raise ValueError('暂存区锁已变化，未应用补丁')
        os.replace(lock,index)
        return count
    finally:
        if owned_lock(lock,identity):lock.unlink()


def run_cli(path,*,check=False):
    try:
        count=apply_index(path,check=check)
        print(f'暂存区补丁{"核验通过" if check else "已应用"}：{count} 个文件；工作区源码未改动。')
        return 0
    except (OSError,ValueError) as error:
        print(f'AwaitLab apply-index: {error}')
        return 2
