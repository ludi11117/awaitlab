"""Exercise the CLI and apply its loop edits to a controlled fixture copy."""
import argparse
import hashlib
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types


ROOT=Path(__file__).resolve().parents[1]


def compare_corpus(version):
    baseline_commit='5c423186fa173a889eac660e7cf5b41889b2d87f'
    data=subprocess.run(['git','show',baseline_commit+':awaitlab/code_audit.py'],
        cwd=ROOT,capture_output=True,check=True).stdout
    prior=types.ModuleType('awaitlab._loop_baseline');prior.__package__='awaitlab'
    exec(compile(data,'git:'+baseline_commit+':awaitlab/code_audit.py','exec'),prior.__dict__)
    from awaitlab.code_audit import audit_source
    raw=subprocess.run(['git','ls-files','--cached','--others','--exclude-standard','-z','--','*.py'],
        cwd=ROOT,capture_output=True,check=True).stdout.decode('utf-8')
    names=sorted(set(raw.rstrip('\0').split('\0')));changes=[]
    for name in names:
        source=(ROOT/name).read_text(encoding='utf-8');old=prior.audit_source(source,name);new=audit_source(source,name)
        if old!=new:
            changes.append({'path':name,'before_findings':old[0],'after_findings':new[0],
                'before_proposed_sha256':hashlib.sha256(old[1].encode()).hexdigest(),
                'after_proposed_sha256':hashlib.sha256(new[1].encode()).hexdigest()})
    assert [row['path'] for row in changes]==['examples/defensive_loop_sample.py'],changes
    assert not changes[0]['before_findings'] and len(changes[0]['after_findings'])==2
    record={'version':version,'baseline_commit':baseline_commit,'baseline_source_sha256':hashlib.sha256(data).hexdigest(),
        'files':names,'files_compared':len(names),'unchanged_files':len(names)-len(changes),'changes':changes,
        'scope':'Current Git-listed corpus; intended new loop fixture differs. No target imported or executed.'}
    (ROOT/f'artifacts/loop-corpus-check-v{version}.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(f'Corpus: {len(names)} files; only intended loop fixture differs from 0.15')


def main():
    sys.path.insert(0,str(ROOT))
    from awaitlab import __version__
    parser=argparse.ArgumentParser();parser.add_argument('--corpus',action='store_true');args=parser.parse_args()
    if args.corpus:
        compare_corpus(__version__);return
    stem=ROOT/f'artifacts/loop-flow-v{__version__}'
    temp=Path('D:/CodexWork/temp/awaitlab');temp.mkdir(parents=True,exist_ok=True)
    source=(ROOT/'examples/defensive_loop_sample.py').read_bytes()
    env={**os.environ,'PYTHONPATH':str(ROOT),'PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1',
        'TEMP':str(temp),'TMP':str(temp)}
    with tempfile.TemporaryDirectory(dir=temp,prefix='loop-flow-') as directory:
        project=Path(directory);path=project/'case.py';path.write_bytes(source)
        def cli(*args):
            return subprocess.run([sys.executable,'-m','awaitlab',*args],cwd=project,
                env=env,capture_output=True,encoding='utf-8')
        first=cli('audit','case.py','--check','--output',str(stem)+'.json',
            '--patch',str(stem)+'.patch','--html',str(stem)+'.html')
        assert first.returncode==1,first.stdout+first.stderr
        report=json.loads(Path(str(stem)+'.json').read_text(encoding='utf-8'))
        assert len(report['findings'])==2 and all(item['patch_available'] for item in report['findings'])
        assert path.read_bytes()==source
        for args in (['--check'],[]):
            subprocess.run(['git','apply',*args,str(stem)+'.patch'],cwd=project,env=env,capture_output=True,check=True)
        before={};after={};exec(source,before);exec(path.read_bytes(),after)
        count=0
        for length in range(4):
            for row in itertools.product((None,True,False,0,'',[],{'id':1}),repeat=length):
                for name in ('collect','prefix'):
                    assert before[name](row)==after[name](row),(name,row)
                    count+=1
        second=cli('audit','case.py','--check')
        assert second.returncode==0,second.stdout+second.stderr
    record={'version':__version__,'fixture':'controlled loop fixture copy; no user project executed',
        'findings':2,'patches_apply':True,'audit_did_not_modify_source':True,
        'before_check_exit':first.returncode,'after_check_exit':second.returncode,
        'runtime_output_pairs':count,'all_outputs_equal':True,
        'scope':'continue and break, loop else, finite values and sequences of length 0 to 3; no general equivalence proof'}
    (ROOT/f'artifacts/loop-flow-check-v{__version__}.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(f'Loop CLI: 2 findings patched; {count} fixture outputs equal; check 1 -> 0')


if __name__=='__main__':main()
