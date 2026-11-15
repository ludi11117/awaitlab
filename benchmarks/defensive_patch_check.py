"""Check else/comment patches without dropping a separate manual-only finding."""
from collections import Counter
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tokenize


ROOT=Path(__file__).resolve().parents[1]


def comments(source):
    return Counter(token.string for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type==tokenize.COMMENT)


def main():
    temp=Path('D:/CodexWork/temp/awaitlab');temp.mkdir(parents=True,exist_ok=True)
    stem=ROOT/'artifacts/defensive-patches-v0.12.0'
    env={**os.environ,'PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(ROOT),'TEMP':str(temp),'TMP':str(temp)}
    command=[sys.executable,'-m','awaitlab','audit','examples/defensive_patch_sample.py','--check',
        '--output',str(stem)+'.json','--patch',str(stem)+'.patch','--html',str(stem)+'.html']
    first=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8')
    assert first.returncode==1,first.stderr
    data=json.loads(Path(str(stem)+'.json').read_text(encoding='utf-8'))
    assert len(data['findings'])==5 and sum(item['patch_available'] for item in data['findings'])==3
    original=(ROOT/'examples/defensive_patch_sample.py').read_bytes()
    with tempfile.TemporaryDirectory(dir=temp) as directory:
        copy=Path(directory);(copy/'examples').mkdir();target=copy/'examples/defensive_patch_sample.py';target.write_bytes(original)
        subprocess.run(['git','apply','--check',str(stem)+'.patch'],cwd=copy,capture_output=True,check=True)
        subprocess.run(['git','apply',str(stem)+'.patch'],cwd=copy,capture_output=True,check=True)
        patched=target.read_bytes()
        assert comments(original.decode('utf-8'))==comments(patched.decode('utf-8'))
        second=subprocess.run([sys.executable,'-m','awaitlab','audit',str(target),'--check','--output',str(copy/'after.json')],
            cwd=copy,env=env,capture_output=True,text=True,encoding='utf-8')
        assert second.returncode==1,second.stderr  # one manual path finding remains
        remaining=json.loads((copy/'after.json').read_text(encoding='utf-8'))['findings']
        assert len(remaining)==2 and {item['rule'] for item in remaining}=={'ALD001','ALD002'}
        assert not any(item['patch_available'] for item in remaining)
        before={};after={};exec(original,before);exec(patched,after)
        for name in ('with_else','with_comments','manual_only','true_else'):
            for value in (None,True,False,0,'',[],{'id':1}):assert before[name](value)==after[name](value)
    assert (ROOT/'examples/defensive_patch_sample.py').read_bytes()==original
    record={'version':'0.12.0','initial_path_findings':4,'initial_review_findings':1,'applicable_patches':3,
        'initial_check_exit':1,'after_patch_check_exit':1,'remaining_manual_path_findings':1,'remaining_review_findings':1,
        'all_comment_texts_preserved':True,'comment_count':sum(comments(original.decode('utf-8')).values()),
        'patch_applied_to_temp_copy':True,'differential_input_count':28,'all_demo_outputs_equal':True,
        'original_source_unchanged':True,'scope':'Controlled demo only; manual-only finding intentionally retained.'}
    (ROOT/'artifacts/defensive-patch-check-v0.12.0.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8',newline='\n')
    print('Patch audit verified: 3 fixes applied, 6 comments retained, 28 outputs equal; 1 manual path finding and 1 exception review remain')


if __name__=='__main__':main()
