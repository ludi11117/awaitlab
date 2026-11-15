"""Demonstrate explicit excludes and reasoned ignores on a D: project fixture."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT=Path(__file__).resolve().parents[1]
SOURCE='''def read(value):
    if value is None:
        return None
    if value is None:
        return 'redundant fallback'
    return value


def optional_plugin(loader):
    try:
        return loader()
    except Exception:  # awaitlab: ignore[ALD002] -- plugin is optional; failure leaves it disabled
        return None
'''


def main():
    temp=Path('D:/CodexWork/temp/awaitlab');temp.mkdir(parents=True,exist_ok=True)
    stem=ROOT/'artifacts/audit-policy-v0.13.0'
    env={**os.environ,'PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(ROOT),'TEMP':str(temp),'TMP':str(temp)}
    with tempfile.TemporaryDirectory(dir=temp) as directory:
        project=Path(directory);source=project/'app.py';source.write_text(SOURCE,encoding='utf-8',newline='\n')
        (project/'generated').mkdir();(project/'generated'/'broken.py').write_text('intentionally invalid python!!',encoding='utf-8')
        (project/'legacy').mkdir();(project/'legacy'/'old.py').write_text(SOURCE,encoding='utf-8')
        base=[sys.executable,'-m','awaitlab','audit',str(project),'--check','--exclude','generated/**','--exclude','legacy/**']
        command=base+['--output',str(stem)+'.json','--patch',str(stem)+'.patch','--html',str(stem)+'.html']
        first=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8')
        assert first.returncode==1,first.stderr
        report=json.loads(Path(str(stem)+'.json').read_text(encoding='utf-8'))
        assert report['files_scanned']==1 and report['errors']==[]
        assert len(report['findings'])==len(report['ignored_findings'])==1
        assert report['excluded_paths']==['generated/','legacy/']
        subprocess.run(['git','apply','--check',str(stem)+'.patch'],cwd=project,capture_output=True,check=True)
        subprocess.run(['git','apply',str(stem)+'.patch'],cwd=project,capture_output=True,check=True)
        second=subprocess.run(base+['--output',str(project/'after.json')],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8')
        assert second.returncode==0,second.stderr
        after=json.loads((project/'after.json').read_text(encoding='utf-8'))
        assert not after['findings'] and len(after['ignored_findings'])==1
        before_scope={};after_scope={};exec(SOURCE,before_scope);exec(source.read_text(encoding='utf-8'),after_scope)
        for value in (None,True,False,0,'',[],{'id':1}):assert before_scope['read'](value)==after_scope['read'](value)
    record={'version':'0.13.0','fixture':'temporary project, not user business code','scanned_files':1,
        'excluded_paths':['generated/','legacy/'],'initial_active_findings':1,'reasoned_ignores':1,
        'first_check_exit':1,'after_patch_check_exit':0,'ignore_reason_retained':True,'differential_inputs':7,
        'all_demo_outputs_equal':True,'excluded_invalid_source_not_parsed':True}
    (ROOT/'artifacts/audit-policy-check-v0.13.0.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8',newline='\n')
    print('Policy verified: exclusions recorded, optional fallback reason retained, active guard patched; --check 1 -> 0')


if __name__=='__main__':main()
