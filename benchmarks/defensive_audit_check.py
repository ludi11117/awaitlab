"""Exercise scan -> reviewed diff -> apply to a D: copy -> rescan and outputs."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT=Path(__file__).resolve().parents[1]


def main():
    temp=Path('D:/CodexWork/temp/awaitlab');temp.mkdir(parents=True,exist_ok=True)
    report=ROOT/'artifacts/defensive-audit-demo.json';patch=ROOT/'artifacts/defensive-audit-demo.patch'
    env={**os.environ,'PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(ROOT),'TEMP':str(temp),'TMP':str(temp)}
    command=[sys.executable,'-m','awaitlab','audit','examples/defensive_sample.py','--check','--output',str(report),'--patch',str(patch)]
    first=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8')
    assert first.returncode==1,first.stderr
    data=json.loads(report.read_text(encoding='utf-8'))
    assert len(data['findings'])==3 and sum(f['patch_available'] for f in data['findings'])==2
    original=(ROOT/'examples/defensive_sample.py').read_bytes()
    with tempfile.TemporaryDirectory(dir=temp) as folder:
        copy=Path(folder);(copy/'examples').mkdir()
        target=copy/'examples/defensive_sample.py';target.write_bytes(original)
        subprocess.run(['git','apply','--check',str(patch)],cwd=copy,capture_output=True,check=True)
        subprocess.run(['git','apply',str(patch)],cwd=copy,capture_output=True,check=True)
        fixed=target.read_bytes()
        second=subprocess.run([sys.executable,'-m','awaitlab','audit',str(target),'--check','--output',str(copy/'fixed.json')],
            cwd=copy,env=env,capture_output=True,text=True,encoding='utf-8')
        assert second.returncode==0,second.stderr
        after=json.loads((copy/'fixed.json').read_text(encoding='utf-8'))
        assert len(after['findings'])==1 and after['findings'][0]['rule']=='ALD002'
        # Execute only this known demonstration fixture for differential checks.
        before_scope={};after_scope={};exec(original,before_scope);exec(fixed,after_scope)
        values=[None,0,'',[],{}, {'id':1}]
        assert all(before_scope['customer_result'](v)==after_scope['customer_result'](v) for v in values)
        assert (ROOT/'examples/defensive_sample.py').read_bytes()==original
    record={'version':'0.10.0','original_findings':3,'path_proven':2,'review_only':1,
        'patch_applied_to_temp_copy':True,'original_source_unchanged':True,'remaining_review_only':1,
        'differential_input_count':len(values),'all_demo_outputs_equal':True,
        'original_sha256':hashlib.sha256(original).hexdigest(),'patch_sha256':hashlib.sha256(patch.read_bytes()).hexdigest(),
        'patched_sha256':hashlib.sha256(fixed).hexdigest(),
        'scope':'Differential execution covers this trusted demonstration only. The scanner never imports/executes audit targets.'}
    (ROOT/'artifacts/defensive-audit-check-v0.10.0.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8',newline='\n')
    print('Audit verified: 2 path facts -> applicable patch -> 0 residual path findings; 6 demo outputs equal; review-only exception retained')


if __name__=='__main__':main()
