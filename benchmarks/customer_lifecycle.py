"""Run the real user CLI and verify lifespan/connection cleanup and full resume."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from awaitlab import __version__
from awaitlab.__main__ import main
from examples import customer_api_case as case


target=ROOT/f'artifacts/customer-api-v{__version__}.json'
original_argv=sys.argv[:]
try:
    sys.argv=['awaitlab','run','examples.customer_api_case','--output',str(target)]
    main()
    measured=json.loads(target.read_text(encoding='utf-8'))
    audit=[dict(state) for state in case.lifecycle_audit]
    expected=case.experiment.settings.blocks*len(case.experiment.arms)*2
    assert len(audit)==expected
    for state in audit:
        assert state['startups']==state['shutdowns']==1
        assert state['client_closed'] and state['pending_tickets']==0
        assert state['requests']==case.experiment.settings.requests+case.experiment.settings.warmup
        assert 1<=state['http_connections']<=case.experiment.settings.concurrency
    case.lifecycle_audit.clear()
    sys.argv.append('--resume');main()
    resumed=json.loads(target.read_text(encoding='utf-8'))
    assert case.lifecycle_audit==[]
    assert measured['comparisons']==resumed['comparisons']
    assert resumed['run']['resumed_pairs']==case.experiment.settings.blocks*len(case.experiment.arms)
finally:sys.argv=original_argv
result={'version':__version__,'report':str(target),'lifetimes':len(audit),'lifecycle_audit':audit,
    'fixture':case.fixture['manifest'],'sql':case.database.SQL,'dependency_versions':case.dependency_versions,
    'resumed_pairs':resumed['run']['resumed_pairs'],'resume_created_no_resources':True,
    'comparisons_unchanged_after_resume':True,'output_contract':resumed['output_contract'],
    'limits':['business projection checks declared fields only','HTTP connections persist within a block, not across blocks',
              'SQLite connections remain per query; executor is lifespan-managed','single process, synthetic customer rows']}
try:
    import psutil
    info=psutil.Process().memory_info()
    result['process_memory_mib']={'rss_end':info.rss/1024**2,'peak_working_set':getattr(info,'peak_wset',info.rss)/1024**2,
        'scope':'whole driver process, imports and all lifetimes; not isolated service memory or OS file cache'}
except ImportError:result['process_memory_mib']=None
check=ROOT/f'artifacts/customer-lifecycle-check-v{__version__}.json'
check.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(f'Checked {len(audit)} lifetimes; full resume created no new app or connections',flush=True)
