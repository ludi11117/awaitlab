const report=JSON.parse(document.getElementById('data').textContent);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=(n,d=2)=>Number.isFinite(Number(n))?Number(n).toFixed(d):'—';
const pnum=(n,d=4)=>Number(n)>0&&Number(n)<10**-d?Number(n).toExponential(2):num(n,d);
const msnum=n=>Number(n)!==0&&Math.abs(Number(n))<.0001?Number(n).toExponential(2):num(n,Math.abs(Number(n))<.01?4:Math.abs(Number(n))<1?3:2);
const names={delay_inventory:'给库存查询增加等待',delay_pricing:'给定价查询增加等待',faster_inventory:'替换为更快的库存查询',faster_pricing:'替换为更快的定价查询',delay_query:'延长数据库连接占用',faster_query:'替换为更快的数据库查询'};
let selected=report.comparisons.findIndex(canRecommend);
if(selected<0)selected=0;
let traceMode='control',requestId=0,traceBlock=0;
Object.assign(names,{indexed_lookup:'为客户查询建立索引',unchanged_lookup:'保持原实现（对照）'});
function replacementAudit(c){
 const manifest=report.run?.identity?.manifest?.arms?.find(a=>a.name===c.name);
 const sites=c.replacement_sites||Object.keys(manifest?.replacement_names||{});
 const native=c.blocks.every(b=>b.treatment.replacement_calls_by_site!==undefined);
 const single=sites.length===1&&sites[0]===c.site;
 const maps=c.blocks.map(b=>b.treatment.replacement_calls_by_site??(single&&Number.isFinite(b.treatment.replacement_calls)?{[c.site]:b.treatment.replacement_calls}:null));
 const known=maps.every(m=>m!==null);
 return {sites,native,maps,known,valid:known&&maps.every(m=>(m[c.site]||0)>0)};
}
function canRecommend(c){return c.kind==='replacement'&&(c.role??'candidate')==='candidate'&&report.quality?.status!=='warning'&&c.candidate_improvement&&replacementAudit(c).valid;}
function replacementView(c){
 if(c.kind!=='replacement')return '';
 const audit=replacementAudit(c);
 return `<details class="card replacement-reach"><summary>替换范围与实际触达</summary><p>主站点：${esc(c.site)}。响应变化对应本臂整组替换配置，不能按调用次数分摊为各站点收益。</p>${!audit.native?`<p class="hint">${audit.known?'旧版仅记录总次数，本臂声明单一站点，因此可归属到该站点。':'历史数据未保存逐站点明细，无法从总次数证明主站点实际触达。'}</p>`:''}<div class="scroll"><table><thead><tr><th>声明的替换站点</th><th>实验组替换调用</th><th>触达配对批次</th></tr></thead><tbody>${audit.sites.map(site=>`<tr><td>${esc(site)}${site===c.site?'<small class="type">主站点</small>':''}</td><td>${audit.known?audit.maps.reduce((sum,m)=>sum+(m[site]||0),0):'—'}</td><td>${audit.known?audit.maps.filter(m=>(m[site]||0)>0).length:'—'} / ${c.blocks.length}</td></tr>`).join('')}</tbody></table></div><p class="hint">计数来自测量阶段的真实替换调用，排除预热和纯观测跨度；配置但未执行的额外站点显示0。</p></details>`;
}
function statusText(c){
 if(!c.output_equivalence)return '输出不一致，不能视为有效优化';
 const states={no_observed_gain:'本轮未观察到收益',below_practical_threshold:'变化未达到实用门槛',inconclusive:'收益证据尚不充分',supported_in_this_experiment:'本轮支持继续验证此优化',invalid_output:'输出不一致，不能视为有效优化'};
 if(!states[c.evidence_level])return '历史报告：未按新版规则分级';
 const audit=replacementAudit(c);
 if(!audit.valid)return audit.known?'主站点未触达，不能视为有效实验':'历史报告：主站点触达证据不足';
 if(c.role==='negative_control')return {change_detected:'负面对照出现变化，需检查实验条件',no_alarm_detected:'未检出对照异常，不代表等价',not_assessed:'负面对照：本轮无法作精确判定'}[c.control_status]||'负面对照：状态未记录';
 if(report.quality?.status==='warning'&&c.evidence_level==='supported_in_this_experiment')return '负面对照异常，候选收益需独立复验';
 return states[c.evidence_level];
}
function qualityView(){
 const q=report.quality;
 if(!q)return '<div class="card quality"><h3>历史数据未记录负面对照角色</h3><p class="hint">不根据实验名称猜测角色，也不补造对照已通过的结论。</p></div>';
 const titles={not_checked:'未配置负面对照',warning:'负面对照异常，本轮暂停候选推荐',no_alarm_detected:'未检出负面对照异常',inconclusive:'负面对照尚无法精确判定'};
 const labels={change_detected:'检出变化',output_mismatch:'输出不一致',no_alarm_detected:'未检出异常',not_assessed:'无法精确判定'};
 const rows=q.controls.map(control=>{const c=report.comparisons.find(c=>c.name===control.name);return `<tr><td>${esc(control.name)}</td><td>${num(c.effect.mean_change_pct,2)}%</td><td>${pnum(c.holm_adjusted_p)}</td><td>${labels[control.status]||esc(control.status)}</td></tr>`;}).join('');
 return `<div class="card quality ${q.status==='warning'?'quality-warning':''}"><h3>${titles[q.status]||'负面对照状态'}</h3>${rows?`<div class="scroll"><table><thead><tr><th>声明的负面对照</th><th>响应变化</th><th>Holm p</th><th>判定</th></tr></thead><tbody>${rows}</tbody></table></div>`:'<p>本次实验没有预先声明负面对照，无法提供这项检查。</p>'}<p class="hint">对照与候选保留在同一替换比较组；任一方向变化达到 ${esc(q.min_point_change_pct)}% 点估计且精确调整 p &lt; ${esc(q.alpha)}，或输出不一致，均提示检查。未检出异常不证明等价，也不保证无测量干扰；原始效应、区间和 p 不变。</p></div>`;
}
function observerView(c){
 if(!c.blocks.every(b=>b.control.output_check&&b.treatment.output_check))return '<div class="card observer"><h3>测量与校验开销</h3><p>历史数据未记录校验段与 worker 周期，不能按零开销解释。</p></div>';
 const avg=(mode,read)=>c.blocks.reduce((sum,b)=>sum+read(b[mode]),0)/c.blocks.length;
 const rows=[['业务响应均值（含追踪）',b=>b.latency.mean_ms,'ms'],['worker 周期均值（含校验）',b=>b.worker_cycle.mean_ms,'ms'],['同步校验段均值',b=>b.output_check.mean_ms,'ms'],['校验段 / worker 周期',b=>b.output_check.share_of_worker_cycle_pct,'%'],['整批 wall 均值',b=>b.wall_ms,'ms']];
 return `<div class="card observer"><h3>测量与校验开销</h3><div class="scroll"><table><thead><tr><th>按配对批次取均值</th><th>控制组</th><th>实验组</th></tr></thead><tbody>${rows.map(([label,read,unit])=>`<tr><td>${label}</td><td>${num(avg('control',read),3)} ${unit}</td><td>${num(avg('treatment',read),3)} ${unit}</td></tr>`).join('')}</tbody></table></div><p class="hint">响应时间不含该请求自身的输出校验；同步校验仍会影响其他任务和闭环节拍。校验段包含计时记账，记录的是同步经过时间，不是隔离 CPU 时间；占比不代表测量误差上界。</p></div>`;
}
function designView(){
 const d=report.inference_design;
 if(!d||d.status==='not_applicable')return '';
 const titles={resolution_limited:'批次数限制了检验分辨率',approximate_only:'本版本只报告近似检验',feasible:'预定检验具备理论分辨率'};
 const detail=d.status==='resolution_limited'?`即使所有配对改善都同向，最佳 Holm p=${pnum(d.holm_p_floor,6)}，仍不能满足 p &lt; ${esc(d.alpha)}。增加每批请求数不能消除这个限制。`:d.status==='approximate_only'?`当前 ${esc(d.blocks)} 批次超过精确枚举上限 ${esc(d.exact_max_blocks)}；近似 p 仍报告，本版本不会自动标为支持。`:`最佳 Holm p=${pnum(d.holm_p_floor,6)}，理论上可以低于 ${esc(d.alpha)}；实际结果仍受波动、输出一致性和改善门槛约束。`;
 return `<div class="card inference-design"><h3>${titles[d.status]||'预定检验设计'}</h3><p>${esc(d.blocks)} 个配对批次 · ${esc(d.replacement_family_size)} 个替换比较（含已声明对照）</p><p>${detail}</p><p class="hint">${d.minimum_exact_blocks!==null?`同一预定比较组理论上至少需 ${esc(d.minimum_exact_blocks)} 批次才有足够分辨率。`:''}这是离散检验的最佳情况，不是统计功效或成功保证。请在新实验前固定方案，勿补样直到显著，也勿截取已测数据。</p></div>`;
}
function workloadView(){
 const data=report.workload_evidence;if(!data)return '';
 return `<section class="card"><h3>真实工作负载证据</h3><p>${esc(data.kind)} · ${esc(data.rows)} 行 · SQLite ${esc(data.sqlite_version)}</p><pre>${esc(data.sql)}</pre><p class="hint">两份文件的表数据摘要相同：${esc(data.fixture.logical_data_sha256)}。执行计划仅作诊断展示，不按文本格式判断实验是否通过。</p>${Object.entries(data.query_plans).map(([name,plan])=>`<h4>${name==='indexed'?'有索引':'无索引'}</h4><pre>${esc(JSON.stringify(plan,null,2))}</pre>`).join('')}<p class="hint">${esc(data.cache_policy)}<br>${esc(data.thread_policy)}</p></section>`;
}
function render(){
 const c=report.comparisons[selected],e=c.effect,real=c.kind==='replacement';
 const sampled=c.blocks.filter(b=>b.control.trace.length||b.treatment.trace.length);
 if(!sampled.some(b=>b.block===traceBlock))traceBlock=sampled[0]?.block??0;
 const pair=c.blocks.find(b=>b.block===traceBlock)||c.blocks[0];
 const requests=[...new Set(pair[traceMode].trace.map(r=>r.request))].filter(r=>r!==null).sort((a,b)=>a-b);
 if(!requests.includes(requestId))requestId=requests[0]??0;
 const cfg=report.settings;
 const bounds=report.comparisons.flatMap(x=>x.effect.ci95_delta_ms);
 const low=Math.min(0,...bounds)-2,high=Math.max(0,...bounds)+2;
 const scale=x=>150+(x-low)/(high-low)*400;
 document.getElementById('app').innerHTML=`<header><a class="brand" href="#">◈ &nbsp; AwaitLab <small>EXPERIMENT REPORT</small></a><span class="local">● 本地报告 · 无网络请求</span></header><main><div class="eyebrow">ASYNC PERFORMANCE / ${esc(report.scenario||'CUSTOM WORKLOAD')}</div><h1>把优化方向，交给实验。</h1><p class="intro">${esc(report.title||'异步工作负载测量')}。额外等待与真实替换分开报告，结果可以逐个批次核对。</p><div class="context"><span>${cfg.blocks} 个配对批次</span><span>每批 ${cfg.requests} 个请求</span><span>${cfg.concurrency} 个闭环并发 worker</span><span>样本输出按请求 ID 核对</span>${report.transport?`<span>${esc(report.transport)}</span>`:''}</div><div class="layout"><section class="overview"><div class="section-title"><h2>01 &nbsp; 端到端响应变化</h2><span>负值表示更快 · 毫秒</span></div><div class="chart"><div class="axis-label"><span>← 更快</span><span>更慢 →</span></div><svg viewBox="0 0 580 ${report.comparisons.length*56+25}" role="img" aria-label="各实验臂响应时间变化与百分位bootstrap区间"><line x1="${scale(0)}" x2="${scale(0)}" y1="0" y2="${report.comparisons.length*56}" stroke="#b8c4cd" stroke-dasharray="3 5"/>${report.comparisons.map((x,i)=>{const y=i*56+24,a=x.effect.ci95_delta_ms,color=x.role==='negative_control'?'#7c8c99':x.kind==='replacement'?'#58a58c':'#c79757';return `<text x="1" y="${y+4}" fill="#7c8c99" font-size="11">${esc(x.site)}${x.kind==='replacement'&&replacementAudit(x).sites.length>1?' +'+(replacementAudit(x).sites.length-1):''}</text><line x1="${scale(a[0])}" x2="${scale(a[1])}" y1="${y}" y2="${y}" stroke="${color}" stroke-width="5"/><circle cx="${scale(x.effect.mean_delta_ms)}" cy="${y}" r="5" fill="${color}"/><text x="${scale(x.effect.mean_delta_ms)}" y="${y+21}" text-anchor="middle" fill="#6c7d89" font-size="10">${msnum(x.effect.mean_delta_ms)} ms</text>`}).join('')}</svg><p class="hint">线段：按配对批次均值重采样的 95% 百分位区间。多组比较属探索性结果，不是生产环境效果保证。</p></div><div class="arms">${report.comparisons.map((x,i)=>`<button data-arm="${i}" class="arm ${i===selected?'active':''}"><span class="arm-kind ${x.role==='negative_control'?'negative_control':x.kind}">${x.role==='negative_control'?'负面对照':x.kind==='replacement'?'真实替换':'等待干预'}</span><strong>${esc(names[x.name]||x.name)}</strong><span>${num(x.effect.mean_change_pct,1)}% <i>→</i></span></button>`).join('')}</div><div class="card constraints"><h3>这份报告能说明什么</h3><p>等待干预测量操作变慢时的响应敏感度；真实替换测量已提供实现的实际变化。不能把等待敏感度反向当成“优化 50% 会快多少”。</p><p>同一请求 ID 的输出哈希一致，只说明这些已测输入没有观察到输出差异；不证明所有输入的业务语义等价。</p><p class="output-contract"><b>输出核对范围：</b>${esc(report.output_contract||'以接入 handler 返回的稳定 JSON 为准；若使用业务投影，不代表整个原始响应相同。')}</p><details><summary>查看完整方法与环境</summary><p>${esc(report.method)}</p><ul>${report.limitations.map(x=>`<li>${esc(x)}</li>`).join('')}</ul><pre>${esc(JSON.stringify(report.environment||{},null,2))}</pre></details></div></section><section class="detail"><div class="section-title"><h2>02 &nbsp; ${esc(names[c.name]||c.name)}</h2></div><div class="card"><span class="badge ${real&&c.role!=='negative_control'?'green':'amber'}">${c.role==='negative_control'?'负面对照':real?'真实实现 A/B':'协作式等待实验'}</span><h2>${real?statusText(c):'测量对额外等待的敏感度'}</h2><div class="metrics"><div><small>平均响应变化</small><strong class="${real?(canRecommend(c)?'good':'neutral'):(e.mean_delta_ms<0?'good':'')}">${num(e.mean_change_pct,1)}<em>%</em></strong></div><div><small>控制组 → 实验组</small><b>${msnum(c.control_mean_ms)} → ${msnum(c.treatment_mean_ms)} <em>ms</em></b></div></div><div class="evidence"><span>均值差区间</span><b>[${e.ci95_delta_ms.map(x=>msnum(x)).join(', ')}] ms</b><span>输出核对</span><b>${c.output_equivalence?'已测输入逐项一致':'存在不一致'}</b></div>${!real?`<div class="timing-note">名义增加 ${num(c.delay_ms)} ms / 次，负载下实际平均增加 ${num(c.observed_injection_mean_ms)} ms / 次。${c.timer_overshoot_warning?'实际等待明显超出设定值；结果按实测等待归一化。':''}</div>`:''}${real?`<p class="hint">${c.role==='negative_control'?'对照报警门槛：任一方向点估计变化至少':'实用门槛：点估计改善至少'} ${report.settings.min_gain_pct??5}%；Holm 调整 p=${pnum(c.holm_adjusted_p)}。${c.randomization?.exact?(c.randomization?.algorithm==='meet_in_middle_integer'?'精确配对随机化检验（分治计数）。':'精确配对随机化检验。'):'未使用可分级的精确检验。'} ${c.role==='negative_control'?'未检出异常不证明等价；检出变化的原因须另查。':'本轮支持不等于改善幅度下界，也不构成已注册的确认性结论。'}</p>`:''}<p class="hint">p95 描述性变化 ${num(c.descriptive_p95_change_pct,1)}%；不提供尾分位的显著性结论。</p></div>${qualityView()}${designView()}${observerView(c)}${replacementView(c)}<div class="card"><h3>逐批次核对</h3><div class="scroll"><table><thead><tr><th>批次</th><th>执行顺序</th><th>控制组</th><th>实验组</th><th>输出</th></tr></thead><tbody>${c.blocks.map(b=>`<tr><td>${b.block+1}</td><td>${b.order[0]==='control'?'控制 → 实验':'实验 → 控制'}</td><td>${msnum(b.control.latency.mean_ms)} ms</td><td>${msnum(b.treatment.latency.mean_ms)} ms</td><td>${b.outputs_equal?'✓ 一致':'× 不一致'}</td></tr>`).join('')}</tbody></table></div></div><div class="card"><div class="section-title"><h3>采样任务时间线</h3><div class="trace-controls"><select id="trace-block" aria-label="时间线配对批次" ${sampled.length<2?'disabled':''}>${sampled.map(b=>`<option value="${b.block}" ${b.block===traceBlock?'selected':''}>批次 ${b.block+1}</option>`).join('')}</select><select id="trace-request" aria-label="时间线请求">${requests.map(r=>`<option value="${r}" ${r===requestId?'selected':''}>请求 ${r}</option>`).join('')}</select><select id="trace-mode" aria-label="时间线实验组"><option value="control" ${traceMode==='control'?'selected':''}>控制组</option><option value="treatment" ${traceMode==='treatment'?'selected':''}>实验组</option></select></div></div>${timeline(c,pair)}${coverageView(pair[traceMode])}<div id="span-detail" class="span-detail" aria-live="polite">选择跨度可查看已记录的父跨度。</div><p class="hint">仅列出已有跨度采样的批次与请求。重叠跨度分轨显示；轨道序号不表示父子层级。不是完整 await 依赖图。</p></div><div class="card"><h3>批次 ${pair.block+1} 控制组累计跨度耗时</h3><p class="hint">累计时间包含并行重叠与等待，不可直接相加为响应时间。</p><div class="scroll"><table><thead><tr><th>跨度</th><th>次数</th><th>累计</th><th>单次均值</th></tr></thead><tbody>${pair.control.operations.map(o=>`<tr><td>${esc(o.name)}<small class="type">${esc(o.kind)}</small></td><td>${o.count}</td><td>${num(o.total_ms)} ms</td><td>${num(o.mean_ms)} ms</td></tr>`).join('')}</tbody></table></div></div></section></div>${workloadView()}${calibrationView()}<footer>AwaitLab ${esc(report.library_version||'0.1')} · 可重跑的测量，不是对任意程序的加速承诺。</footer></main>`;
 document.querySelectorAll('[data-arm]').forEach(el=>el.onclick=()=>{selected=+el.dataset.arm;render();});
 document.getElementById('trace-mode').onchange=ev=>{traceMode=ev.target.value;render();};
 document.getElementById('trace-request').onchange=ev=>{requestId=+ev.target.value;render();};
 document.getElementById('trace-block').onchange=ev=>{traceBlock=+ev.target.value;render();};
 document.querySelectorAll('[data-span]').forEach(el=>el.onclick=()=>{
  const rows=pair[traceMode].trace,span=rows.find(r=>r.id===+el.dataset.span);
  const parent=rows.find(r=>r.id===span.parent);
  document.getElementById('span-detail').textContent=`#${span.id} ${span.name} · ${num(span.duration_ms)} ms · ${span.failed?'失败':'完成'} · 父跨度：${span.parent===null?'无（已记录根跨度）':parent?`#${parent.id} ${parent.name}`:`#${span.parent}（未采样）`}`;
 });
}
function timeline(c,pair){
 const sample=pair[traceMode],layout=AwaitLabTimeline.layout(sample.trace,requestId);
 if(!layout)return '<p class="hint">此批次未采样该请求。</p>';
 const {start,width,lanes}=layout;
 return `<div class="timeline" data-request="${requestId}" data-block="${pair.block}">${lanes.map(lane=>`<div class="lane"><span>${esc(lane.name)}</span><div>${lane.spans.map(r=>`<button type="button" data-span="${r.id}" class="bar ${esc(r.kind)} ${r.failed?'failed':''}" style="left:${100*(r.start_ms-start)/width}%;width:${100*r.duration_ms/width}%" title="${esc(r.name)} · ${num(r.duration_ms)} ms · #${r.id}" aria-label="${esc(r.name)} · #${r.id}">${esc(r.name)}</button>`).join('')}</div></div>`).join('')}</div><p class="hint">批次 ${pair.block+1} · 请求 ${requestId} · ${num(width)} ms · ${sample.trace_dropped?'部分跨度因采样上限被省略':'未触及跨度采样上限'}</p>`;
}
function coverageView(sample){
 const c=AwaitLabTimeline.coverage(sample.trace,requestId);
 if(!c)return '';
 return `<details class="coverage"><summary>请求窗口覆盖 · 重叠时间不重复相加</summary><p class="hint">已标记跨度覆盖 ${num(c.covered_ms)} / ${num(c.request_ms)} ms；其余 ${num(c.uncovered_ms)} ms 未被采样跨度覆盖。未覆盖时间不能解释为 CPU 时间，标记的等待也不等于有效计算。</p><div class="scroll"><table><thead><tr><th>跨度</th><th>窗口内累计</th><th>区间并集</th></tr></thead><tbody>${c.groups.map(g=>`<tr><td>${esc(g.name)}<small class="type">${esc(g.kind)}</small></td><td>${num(g.cumulative_ms)} ms</td><td>${num(g.covered_ms)} ms</td></tr>`).join('')}</tbody></table></div><p class="hint">各行之间仍可能重叠，不能相加为请求时长。仅按采样记录裁剪到请求窗口，不是完整关键路径或组件 CPU 分解。${sample.trace_dropped?'有跨度因上限被省略，覆盖结果可能不完整。':''}</p></details>`;
}
function calibrationView(){
 const calibration=report.timer_calibration;
 if(!calibration)return '';
 return `<details class="calibration"><summary>定时器校准 · 检查名义等待与实际等待的偏差</summary><div class="scroll"><table><thead><tr><th>请求等待</th><th>实测中位数</th><th>实测 p95</th></tr></thead><tbody>${calibration.sleep_samples.map(x=>`<tr><td>${x.requested_ms} ms</td><td>${num(x.p50_ms)} ms</td><td>${num(x.p95_ms)} ms</td></tr>`).join('')}</tbody></table></div><p class="hint">校准时空闲，实际干预还会受到运行中的任务调度影响。程序未修改系统定时器分辨率。</p></details>`;
}
render();
