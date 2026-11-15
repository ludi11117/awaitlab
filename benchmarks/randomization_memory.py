"""One fresh process per implementation; descriptive resource check only."""
import json
from pathlib import Path
import subprocess
import sys
import time
import tracemalloc

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from awaitlab import __version__


def child(mode):
    if mode=='baseline':import baseline_v064_statistics as module
    else:from awaitlab import statistics as module
    n=32;c=[100.]*n;t=[100.+(i%5-2)*.2-.15 for i in range(n)]
    start=time.perf_counter()
    for _ in range(10):result=module.paired_randomization(c,t)
    elapsed=(time.perf_counter()-start)*1000
    tracemalloc.start();module.paired_randomization(c,t);_,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
    try:
        import psutil
        info=psutil.Process().memory_info()
        memory={'rss_end_mib':info.rss/1024**2,'peak_working_set_mib':getattr(info,'peak_wset',info.rss)/1024**2}
    except ImportError:memory=None
    print(json.dumps({'mode':mode,'blocks':n,'repeats':10,'total_ms':elapsed,
        'exact':result['exact'],'pvalue':result['pvalue'],'traced_peak_kib':peak/1024,
        'process_memory':memory}))


def main():
    rows={}
    for mode in ['baseline','current']:
        run=subprocess.run([sys.executable,str(Path(__file__).resolve()),mode],cwd=ROOT,
            capture_output=True,text=True,encoding='utf-8',check=True)
        rows[mode]=json.loads(run.stdout)
    result={'version':__version__,'processes':rows,'limits':[
        'one new process per mode, descriptive only, no memory inference',
        'baseline is approximate at 32 blocks; current is exact',
        'process peaks include imports, all 10 calls, and separate tracemalloc probe',
        'traced peaks exclude interpreter/native/runtime allocations; not a universal memory bound']}
    target=ROOT/f'artifacts/randomization-memory-v{__version__}.json'
    target.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(rows,indent=2))


if __name__=='__main__':
    if len(sys.argv)>1:child(sys.argv[1])
    else:main()
