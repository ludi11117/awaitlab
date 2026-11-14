"""Optional export figure; uses existing matplotlib, not a product dependency."""
import json
import os
import argparse
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from awaitlab import __version__

os.environ.setdefault('MPLCONFIGDIR','D:/CodexWork/cache/awaitlab-matplotlib')
os.environ['TEMP']='D:/CodexWork/temp/awaitlab'
os.environ['TMP']=os.environ['TEMP']
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--folder',type=Path,default=ROOT/f'artifacts/concurrency-v1-{__version__}')
folder=parser.parse_args().folder
summary=json.loads((folder/'summary.json').read_text(encoding='utf-8'))
if summary['state']!='complete':raise ValueError('Only plot a completed fixed sweep')
fig,ax=plt.subplots(figsize=(9,5.6),layout='constrained')
fig.set_facecolor('#f5f8fa');ax.set_facecolor('#ffffff')
for scenario,label,color in [('sqlite','Direct SQLite','#217b68'),('sqlite-http','HTTP + SQLite','#466fa0')]:
 cases=[c for c in summary['cases'] if c['scenario']==scenario]
 for arm,style in [('indexed_lookup','-'),('unchanged_lookup','--')]:
  effects=[next(x for x in c['comparisons'] if x['name']==arm)['effect']['mean_change_pct'] for c in cases]
  ax.plot([c['concurrency'] for c in cases],effects,style,marker='o' if style=='-' else 'x',
      color=color,alpha=1 if style=='-' else .55,linewidth=2 if style=='-' else 1,
      label=label+(' / index' if style=='-' else ' / unchanged'))
  if style=='-':
   for case,value in zip(cases,effects):ax.annotate(f'{value:.1f}%',(case['concurrency'],value),xytext=(0,-17),textcoords='offset points',ha='center',fontsize=9,color=color)
ax.axhline(0,color='#8494a1',linewidth=.8)
ax.set_xticks([1,4,8]);ax.set_xlabel('Closed-loop workers');ax.set_ylabel('Mean response change (%) - negative is faster')
ax.set_ylim(-98,24);ax.grid(axis='y',alpha=.15);ax.spines[['top','right']].set_visible(False)
ax.set_title('The same index yields different end-to-end gains',loc='left',fontsize=15,pad=18)
ax.legend(loc='upper center',ncol=2,fontsize=8.5,frameon=False)
plan=summary['plan']
fig.suptitle(f'AwaitLab {plan["library_version"]} | 50,000 rows | {plan["blocks"]} paired blocks x {plan["requests"]} requests | seed {plan["seed"]}',fontsize=9,color='#687c8d')
fig.supxlabel(f'Exploratory point estimates; no cross-case inference. Fixed protocol and raw blocks: {folder.name}/',fontsize=8,color='#687c8d')
fig.savefig(folder/'latency-change.svg');fig.savefig(folder/'latency-change.png',dpi=170)
plt.close(fig)
print(folder/'latency-change.svg')
