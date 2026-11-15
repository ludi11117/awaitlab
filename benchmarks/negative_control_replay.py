"""Flag a known unchanged implementation that was presented as a candidate.

The control's identity comes from this benchmark protocol, not a generic name
heuristic in the SDK. Historical input is immutable and expected to be red.
"""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
path=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'artifacts/extended-exact-v0.7.0.json'
report=json.loads(path.read_text(encoding='utf-8'))
control=next(c for c in report['comparisons'] if c['name']=='unchanged')
print(json.dumps({k:control[k] for k in ['name','evidence_level','candidate_improvement','holm_adjusted_p']}|
    {'change_pct':control['effect']['mean_change_pct']},indent=2),flush=True)
if control['candidate_improvement']:
    raise SystemExit('RED: protocol-declared unchanged implementation is presented as an optimization candidate')
print('GREEN: unchanged implementation is not presented as an optimization candidate')
