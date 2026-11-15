"""Export measured algorithm costs; old approximate cases are separate."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from awaitlab import __version__
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

data=json.loads((ROOT/f'artifacts/randomization-cost-v{__version__}.json').read_text())
fig,axes=plt.subplots(1,2,figsize=(10,4.3),gridspec_kw={'width_ratios':[3,2]})
for ax,cases,title in zip(axes,[[8,12,16],[24,32]],
        ['Same fixture, equal tail counts','Changed precision mode (descriptive)']):
    x=list(range(len(cases)))
    for j,(name,label,color) in enumerate([('baseline','Frozen 0.6.4','#9aaebc'),('current','0.7.0 integer MITM','#3a8a74')]):
        values=[data['measurements'][str(n)][f'{name}_mean_ms'] for n in cases]
        positions=[i+(-.19 if j==0 else .19) for i in x]
        ax.bar(positions,values,width=.36,label=label,color=color)
        for position,value in zip(positions,values):
            ax.text(position,value*1.16,f'{value:.3g}',ha='center',va='bottom',fontsize=8)
    ax.set_yscale('log');ax.set_ylim(.006,500);ax.set_xticks(x,[str(n) for n in cases]);ax.set_xlabel('Paired blocks')
    ax.set_title(title,fontsize=11);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
axes[0].set_ylabel('Time per statistical test (ms, log scale)');axes[0].legend(loc='upper left',fontsize=8)
fig.suptitle('AwaitLab: measured cost of paired sign-flip inference',fontsize=14)
fig.text(.04,.025,'12 randomized pairs, fixed seed 2409. 24/32 blocks: frozen Monte Carlo vs current exact count.\nCosts exclude workloads. Integer boundary convention is versioned; memory measured separately.',fontsize=9)
fig.tight_layout(rect=[0,.13,1,.94])
for extension in ['png','svg']:
    fig.savefig(ROOT/f'artifacts/randomization-cost-v{__version__}.{extension}',dpi=170)
print('Exported PNG and SVG statistical-cost figures')
