"""Run a fixed query-elimination experiment and audit actual SQLite SELECTs."""
from contextlib import redirect_stdout,redirect_stderr
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from awaitlab.__main__ import main
from examples import order_query_case as case


def run():
    target=ROOT/'artifacts/order-queries-v1.json'
    temp=Path('D:/CodexWork/temp/awaitlab');temp.mkdir(parents=True,exist_ok=True)
    argv=sys.argv[:]
    try:
        with (temp/'order-query-check-v1.log').open('w',encoding='utf-8') as log,redirect_stdout(log),redirect_stderr(log):
            sys.argv=['awaitlab','run','examples.order_query_case','--output',str(target),'--plan']
            main();assert not case.query_audit
            sys.argv=sys.argv[:-1];main()
            measured=json.loads(target.read_text(encoding='utf-8'))
            audit=[counts[:] for counts in case.query_audit];case.query_audit.clear()
            sys.argv.append('--resume');main()
            resumed=json.loads(target.read_text(encoding='utf-8'))
        settings=case.experiment.settings
        assert len(audit)==60
        assert all(len(counts)==18 and len(set(counts))==1 for counts in audit)
        assert sorted(counts[0] for counts in audit)==sorted([48]*40+[13]*10+[1]*10)
        assert not case.query_audit
        assert measured['comparisons']==resumed['comparisons'] and resumed['run']['resumed_pairs']==30
        assert all(c['output_equivalence'] for c in measured['comparisons'])
        assert not measured['comparisons'][-1]['candidate_improvement']
        record={'sdk_version':measured['library_version'],'report':str(target),
            'settings':vars(settings),'orders_per_request':48,'distinct_customer_keys':13,
            'selects_per_request':{'per_order':48,'request_deduplicated':13,'batched':1},
            'count_method':'sqlite3.set_trace_callback counts actual SELECT statements; BEGIN excluded',
            'all_block_query_counts_including_warmup':audit,
            'total_selects_including_warmup':sum(map(sum,audit)),
            'measured_selects':sum(counts[0]*settings.requests for counts in audit),
            'resumed_pairs':30,'plan_and_resume_issued_no_queries':True,'all_outputs_equal':True,
            'quality':measured['quality'],
            'limits':['Synthetic ordered list; not an ORM or automatic N+1 detector.',
                'All variants use one read-only connection/transaction per request and the same indexed file.',
                'No cross-request cache; input construction, worker queue, SQL and assembly remain in request timing.',
                'SELECT count reduction is not the percentage reduction in response latency.',
                'One fixed run; negative-control alarms and inconclusive results are retained.']}
        (ROOT/'artifacts/order-query-check-v1.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8',newline='\n')
        print(f'Orders verified: {record["total_selects_including_warmup"]} actual SELECTs; 48 / 13 / 1 per request; 30 pairs resumed without queries')
        for c in measured['comparisons']:
            print(c['name'],json.dumps({'effect':c['effect'],'holm_p':c['holm_adjusted_p'],'recommended':c['candidate_improvement']}))
    finally:sys.argv=argv


if __name__=='__main__':run()
