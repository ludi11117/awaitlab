"""Optional static phase chart from paired setup data; matplotlib only for export."""
import json
import argparse
import os
from pathlib import Path
import statistics
import sys

root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from awaitlab import __version__

os.environ['MPLCONFIGDIR']='D:/CodexWork/cache/awaitlab-matplotlib'
os.environ['TEMP']='D:/CodexWork/temp/awaitlab';os.environ['TMP']=os.environ['TEMP']
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--report',type=Path,default=root/f'artifacts/http-setup-v{__version__}.json')
report=json.loads(parser.parse_args().report.read_text())
measured_version=report['plan']['version']
fig,ax=plt.subplots(figsize=(9,4.8),layout='constrained')
fig.set_facecolor('#f5f8fa');ax.set_facecolor('#ffffff')
modes=['baseline','cached'];left=[0.,0.]
for field,label,color in [('setup_ms','Setup until client ready','#456e91'),('three_requests_ms','Three HTTP requests','#59a88d'),('shutdown_ms','Shutdown','#c1a16b')]:
    values=[statistics.fmean(p[mode][field] for p in report['helpers']) for mode in modes]
    ax.barh([1,0],values,left=left,color=color,label=label,height=.4)
    left=[a+b for a,b in zip(left,values)]
for y,total in zip([1,0],left):ax.text(total+8,y,f'{total:.1f} ms',va='center',fontsize=10,color='#415b70')
ax.set_yticks([1,0],['0.6.1 / fresh trust store',f'{measured_version} / warm shared trust store'])
ax.set_xlabel('Mean elapsed time per helper lifetime (ms)')
ax.set_xlim(0,max(left)*1.2);ax.set_ylim(-.65,1.65)
ax.spines[['top','right','left']].set_visible(False);ax.grid(axis='x',alpha=.12)
ax.legend(loc='upper center',bbox_to_anchor=(.5,1.08),ncol=3,frameon=False,fontsize=8)
ax.set_title('Reuse setup configuration, keep fresh client pools',loc='left',fontsize=14,pad=40)
fig.suptitle('12 randomized paired samples | 3 sequential loopback requests per lifetime',fontsize=9,color='#687c8d')
fig.supxlabel(f'First trust-store load: {report["plan"]["cold_context_ms"]:.1f} ms (not included in warm bar). Point means; exploratory.\nSetup savings are not business-request speedup.',fontsize=9,color='#687c8d')
for suffix in ['png','svg']:fig.savefig(root/f'artifacts/http-setup-phases-v{measured_version}.{suffix}',dpi=170)
plt.close(fig)
