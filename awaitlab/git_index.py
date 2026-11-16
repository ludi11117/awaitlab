"""Read staged Python blobs directly; never checkout, filter, or modify them."""
from fnmatch import fnmatchcase
from functools import partial
import hashlib
import os
from pathlib import Path,PurePosixPath
import subprocess

from .code_audit import AuditRun,patch_text


def quoted_path(path):
    # Git's quoted patch paths escape UTF-8 bytes in C/octal form, not JSON \u escapes.
    parts=[]
    for byte in path.encode('utf-8'):
        if byte in (34,92):parts.append('\\'+chr(byte))
        elif 32<=byte<127:parts.append(chr(byte))
        else:parts.append(f'\\{byte:03o}')
    return '"'+''.join(parts)+'"'


def blob_oid(data,object_format):
    return hashlib.new(object_format,b'blob '+str(len(data)).encode('ascii')+b'\0'+data).hexdigest()


def index_patch(name,source,patched,*,old_oid,mode,object_format):
    if blob_oid(source.encode('utf-8'),object_format)!=old_oid:
        raise ValueError(f'读取源码与暂存Git对象不一致：{name}')
    new_oid=blob_oid(patched.encode('utf-8'),object_format)
    before=quoted_path('a/'+name);after=quoted_path('b/'+name)
    return (f'diff --git {before} {after}\nindex {old_oid}..{new_oid} {mode}\n'+
        patch_text(source,patched,before,after))


class GitReader:
    def __init__(self,root):
        self.root=root
        self.env={**os.environ,'GIT_OPTIONAL_LOCKS':'0','GIT_NO_LAZY_FETCH':'1','GIT_TERMINAL_PROMPT':'0'}

    def command(self,*args):
        return ['git','--no-replace-objects','-c','core.fsmonitor=false','-C',str(self.root),*args]

    def read(self,*args,input=None):
        result=subprocess.run(self.command(*args),env=self.env,input=input,capture_output=True)
        if result.returncode:raise ValueError('Git读取失败：'+result.stderr.decode('utf-8',errors='replace').strip())
        return result.stdout

    def head_oid(self):
        result=subprocess.run(self.command('rev-parse','--verify','--quiet','HEAD'),env=self.env,capture_output=True)
        if result.returncode==1:return None
        if result.returncode:raise ValueError('无法读取Git HEAD：'+result.stderr.decode('utf-8',errors='replace').strip())
        return result.stdout.strip().decode('ascii')

    def staged_diff(self,baseline):
        args=['diff','--cached','--raw','-z','--no-abbrev','--no-ext-diff','--no-textconv','--no-renames']
        if baseline is not None:args.append(baseline)
        return self.read(*args,'--')

    def index_path(self):
        return Path(os.fsdecode(self.read('rev-parse','--path-format=absolute','--git-path','index')).strip())

    def visit_blobs(self,entries,consumer):
        if not entries:return
        with subprocess.Popen(self.command('cat-file','--batch'),env=self.env,stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE) as process:
            try:
                for name,oid,mode in entries:
                    process.stdin.write(oid.encode('ascii')+b'\n');process.stdin.flush()
                    header=process.stdout.readline().split()
                    if len(header)!=3 or header[0]!=oid.encode('ascii') or header[1]!=b'blob':
                        raise ValueError(f'暂存对象不可读：{name}；请确认本地Git对象完整')
                    size=int(header[2]);data=process.stdout.read(size)
                    if len(data)!=size or process.stdout.read(1)!=b'\n':raise ValueError(f'Git对象读取不完整：{name}')
                    consumer(name,oid,mode,data)
            finally:
                process.stdin.close()
            code=process.wait()
            if code:raise ValueError('Git对象读取失败：'+process.stderr.read().decode('utf-8',errors='replace').strip())


def audit_index(target,*,exclude=()):
    target=Path(os.path.abspath(target));anchor=target if target.is_dir() else target.parent
    reader=GitReader(anchor)
    root=Path(reader.read('rev-parse','--show-toplevel').decode('utf-8').strip()).resolve();reader.root=root
    if not target.is_relative_to(root):raise ValueError('暂存区扫描目标必须位于Git仓库内')
    directory=target.is_dir();scan_root=target if directory else target.parent
    patterns=tuple(pattern.replace('\\','/') for pattern in exclude)
    run=AuditRun(root,scan_root,patterns,'git_index');report=run.report
    report['scan_target']=str(target)
    baseline=reader.head_oid();staged=reader.staged_diff(baseline)
    object_format=reader.read('rev-parse','--show-object-format').decode('ascii').strip()
    selected=[];skipped=[];deleted=[]
    rows=staged.split(b'\0')
    for metadata,raw_name in zip(rows[0:-1:2],rows[1:-1:2]):
        old_mode,mode,old_oid,oid,status=metadata[1:].split()
        name=raw_name.decode('utf-8');path=root.joinpath(*PurePosixPath(name).parts)
        if not name.endswith('.py') or (not path.is_relative_to(target) if directory else path!=target):continue
        relative=path.relative_to(scan_root).as_posix()
        if any(fnmatchcase(relative,pattern) for pattern in patterns):
            report['excluded_paths'].append(relative);continue
        if status==b'D':deleted.append(name);continue
        if status==b'U':
            report['errors'].append({'path':name,'error':'暂存区存在未解决的合并冲突；未选择任意一侧源码'})
            continue
        if mode not in (b'100644',b'100755'):
            skipped.append(name);continue
        selected.append((name,oid.decode('ascii'),mode.decode('ascii')))
    report['index_snapshot']={'base_head':baseline,'diff_sha256':hashlib.sha256(staged).hexdigest(),
        'index_file':str(reader.index_path()),
        'selected_blobs':{name:oid for name,oid,mode in selected},'object_format':object_format,
        'skipped_nonregular_paths':skipped,
        'deleted_python_paths':sorted(deleted),
        'scope':'Whole staged Python files differing from captured HEAD; not changed-line attribution. No untracked or unstaged content.'}
    def analyze(name,oid,mode,data):
        run.add_source(name,data,git_blob=oid,patch_builder=partial(index_patch,
            old_oid=oid,mode=mode,object_format=object_format))
    reader.visit_blobs(selected,analyze)
    if staged!=reader.staged_diff(baseline) or baseline!=reader.head_oid():
        report['errors'].append({'path':str(root),'error':'扫描期间HEAD或暂存区发生变化，请重新审查'})
    report['excluded_paths']=sorted(set(report['excluded_paths']))
    return run.finish()
