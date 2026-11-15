"""Verify compound audit findings and apply a reviewed patch to a D: copy."""
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT=Path(__file__).resolve().parents[1]


def main():
    temp=Path('D:/CodexWork/temp/awaitlab');temp.mkdir(parents=True,exist_ok=True)
    stem=ROOT/'artifacts/defensive-logic-v0.11.0'
    env={**os.environ,'PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(ROOT),'TEMP':str(temp),'TMP':str(temp)}
    command=[sys.executable,'-m','awaitlab','audit','examples/defensive_logic_sample.py','--check',
        '--output',str(stem)+'.json','--patch',str(stem)+'.patch','--html',str(stem)+'.html']
    result=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8')
    assert result.returncode==1,result.stderr
    data=json.loads(Path(str(stem)+'.json').read_text(encoding='utf-8'))
    assert len(data['findings'])==4 and sum(item['patch_available'] for item in data['findings'])==3
    original=(ROOT/'examples/defensive_logic_sample.py').read_bytes()
    with tempfile.TemporaryDirectory(dir=temp) as folder:
        copy=Path(folder);(copy/'examples').mkdir();target=copy/'examples/defensive_logic_sample.py';target.write_bytes(original)
        subprocess.run(['git','apply','--check',str(stem)+'.patch'],cwd=copy,capture_output=True,check=True)
        subprocess.run(['git','apply',str(stem)+'.patch'],cwd=copy,capture_output=True,check=True)
        after=subprocess.run([sys.executable,'-m','awaitlab','audit',str(target),'--check','--output',str(copy/'after.json')],
            cwd=copy,env=env,capture_output=True,text=True,encoding='utf-8')
        assert after.returncode==0,after.stderr
        remaining=json.loads((copy/'after.json').read_text(encoding='utf-8'))['findings']
        assert len(remaining)==1 and remaining[0]['rule']=='ALD002'
        before_scope={};after_scope={};exec(original,before_scope);exec(target.read_bytes(),after_scope)
        customers=[None,0,'',[],{}, {'id':1}];flags=[None,True,False,1,0,'',[]]
        for customer,flag in itertools.product(customers,flags):
            assert before_scope['customer_result'](customer,flag)==after_scope['customer_result'](customer,flag)
        for flag in flags:assert before_scope['enabled'](flag)==after_scope['enabled'](flag)
    assert (ROOT/'examples/defensive_logic_sample.py').read_bytes()==original
    record={'version':'0.11.0','initial_path_findings':3,'initial_review_findings':1,'patch_applied_to_temp_copy':True,
        'remaining_path_findings':0,'remaining_review_findings':1,'differential_input_count':49,
        'all_demo_outputs_equal':True,'original_source_unchanged':True,
        'report':'defensive-logic-v0.11.0.html','scope':'Known demonstration only; arbitrary audit targets are never executed.'}
    (ROOT/'artifacts/defensive-logic-check-v0.11.0.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8',newline='\n')
    print('Compound audit verified: 3 redundant guards patched, 49 demo outputs equal, 1 review-only exception retained')


if __name__=='__main__':main()
