"""Apply explicitly annotated control roles to immutable measured reports.

This is a post-measurement interpretation replay, not native predeclared-role
evidence. The input protocols used the original callable for 'unchanged'.
Neither measured data nor historical p-values are recomputed or overwritten.
"""
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from awaitlab import __version__
from awaitlab.experiment import assess_quality
from awaitlab.report import write_report


def replay(source,label):
    raw=json.loads(source.read_text(encoding='utf-8'));report=copy.deepcopy(raw)
    roles={'formula':'candidate','unchanged':'negative_control'}
    assert {c['name'] for c in report['comparisons']}==set(roles)
    for c in report['comparisons']:c['role']=roles[c['name']]
    report['quality']=assess_quality(report['comparisons'],report['settings']['alpha'],report['settings']['min_gain_pct'])
    report['analysis_replay']={'policy_sdk_version':__version__,'source':str(source),
        'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'new_measurements':False,
        'roles':'post-measurement annotation from known protocol callable identities; not a native predeclared-role run'}
    report['title']='旧数据的对照角色解释回放（未重新测量）'
    report['output_contract']='输出核对及计时来自原始报告；本文件只补充已知对照角色和解释，不提供新的确认性证据。'
    for before,after in zip(raw['comparisons'],report['comparisons']):
        for key in ['effect','randomization','holm_adjusted_p','evidence_level','blocks']:
            assert before[key]==after[key]
    target=ROOT/f'artifacts/control-role-{label}-replay-v{__version__}.json'
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    write_report(report,target.with_suffix('.html'))
    assert hashlib.sha256(source.read_bytes()).hexdigest()==report['analysis_replay']['source_sha256']
    return {'source':str(source),'output':str(target),'quality':report['quality'],
        'original_candidate_flags':{c['name']:c['candidate_improvement'] for c in raw['comparisons']},
        'replayed_candidate_flags':{c['name']:c['candidate_improvement'] for c in report['comparisons']},
        'measured_fields_unchanged':True,'new_measurements':False}


def main():
    cases=[replay(ROOT/'artifacts/extended-exact-v0.7.0.json','anomaly'),
        replay(ROOT/'artifacts/negative-control-diagnosis-v0.7.0/short-01.json','no-alarm')]
    assert cases[0]['quality']['status']=='warning'
    assert not any(cases[0]['replayed_candidate_flags'].values())
    assert cases[1]['quality']['status']=='no_alarm_detected'
    result={'policy_sdk_version':__version__,'cases':cases}
    (ROOT/f'artifacts/control-role-replay-check-v{__version__}.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('Recorded anomaly: warning, candidate recommendations withheld; all measured fields unchanged')


if __name__=='__main__':main()
