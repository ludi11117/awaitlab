"""Exercise read-only staged review, then apply its patch to a temporary index."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT=Path(__file__).resolve().parents[1]
GOOD='def read(value):\n    return value\n'
BAD='def read(value):\n    if value is None:\n        return None\n    if value is None:\n        return 1\n    return value\n'


def main():
    temp=Path('D:/CodexWork/temp/awaitlab');temp.mkdir(parents=True,exist_ok=True)
    stem=ROOT/'artifacts/git-index-v0.15.0'
    with tempfile.TemporaryDirectory(dir=temp,prefix='awaitlab-staged-demo-') as directory:
        project=Path(directory);hooks=project/'empty-hooks';hooks.mkdir()
        env={**os.environ,'GIT_DIR':str(project/'.git'),'GIT_WORK_TREE':str(project),'GIT_INDEX_FILE':str(project/'.git/index'),
            'PYTHONPATH':str(ROOT),'PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1','TEMP':str(temp),'TMP':str(temp)}
        def git(*args):
            return subprocess.run(['git','-C',str(project),*args],env=env,capture_output=True,check=True).stdout
        git('init','-q');git('config','core.autocrlf','false');git('config','commit.gpgsign','false')
        git('config','core.hooksPath',str(hooks))
        path=project/'case.py';path.write_bytes(GOOD.encode());git('add','case.py')
        git('-c','user.name=AwaitLabDemo','-c','user.email=demo@example.invalid','commit','-qm','baseline')
        path.write_bytes(BAD.encode());git('add','case.py')
        worktree=b'# unstaged sentinel\n'+GOOD.encode();path.write_bytes(worktree)
        index_before=(project/'.git/index').read_bytes()
        command=[sys.executable,'-m','awaitlab','audit','--staged','--check',
            '--output',str(stem)+'.json','--patch',str(stem)+'.patch','--html',str(stem)+'.html']
        first=subprocess.run(command,cwd=project,env=env,capture_output=True,text=True,encoding='utf-8')
        assert first.returncode==1,first.stderr
        report=json.loads(Path(str(stem)+'.json').read_text(encoding='utf-8'))
        assert report['files_scanned']==1 and len(report['findings'])==1 and not report['errors']
        assert report['sources']['case.py']['sha256']==hashlib.sha256(BAD.encode()).hexdigest()
        assert (project/'.git/index').read_bytes()==index_before and path.read_bytes()==worktree
        ordinary=subprocess.run([sys.executable,'-m','awaitlab','audit','--check','--output',str(project/'worktree.json')],
            cwd=project,env=env,capture_output=True,text=True,encoding='utf-8')
        assert ordinary.returncode==0,ordinary.stderr
        apply_command=[sys.executable,'-m','awaitlab','apply-index',str(stem)+'.json']
        checked=subprocess.run(apply_command+['--check'],cwd=project,env=env,capture_output=True,text=True,encoding='utf-8')
        assert checked.returncode==0,checked.stdout+checked.stderr
        assert (project/'.git/index').read_bytes()==index_before
        applied=subprocess.run(apply_command,cwd=project,env=env,capture_output=True,text=True,encoding='utf-8')
        assert applied.returncode==0,applied.stdout+applied.stderr
        fixed=git('show',':case.py')
        assert path.read_bytes()==worktree and b'return 1' not in fixed
        second=subprocess.run([sys.executable,'-m','awaitlab','audit','--staged','--check','--output',str(project/'after.json')],
            cwd=project,env=env,capture_output=True,text=True,encoding='utf-8')
        assert second.returncode==0,second.stderr
        before={};after={};exec(BAD,before);exec(fixed,after)
        for value in (None,True,False,0,'',[],{'id':1}):assert before['read'](value)==after['read'](value)
        blob=report['sources']['case.py']['git_blob']
        stale=subprocess.run(apply_command,cwd=project,env=env,capture_output=True,text=True,encoding='utf-8')
        assert stale.returncode==2 and path.read_bytes()==worktree
    record={'version':'0.15.0','fixture':'temporary Git repository, not user business code',
        'staged_check_exit':1,'ordinary_worktree_check_exit':0,'after_cached_patch_check_exit':0,
        'audited_git_blob':blob,'scan_did_not_modify_index':True,'scan_did_not_modify_worktree_source':True,
        'version_check_exit':checked.returncode,'version_check_did_not_modify_index':True,
        'version_checked_apply_exit':applied.returncode,'repeated_stale_report_exit':stale.returncode,
        'cached_patch_left_worktree_source_unchanged':True,'differential_inputs':7,'all_demo_outputs_equal':True,
        'scope':'Whole staged file review; does not attribute every finding to newly changed lines.'}
    (ROOT/'artifacts/git-index-check-v0.15.0.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8',newline='\n')
    print('Index review verified: staged problem found despite clean worktree, read-only scan, cached patch preserves worktree, 7 outputs equal')


if __name__=='__main__':main()
