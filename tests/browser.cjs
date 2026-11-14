const fs=require('node:fs'),path=require('node:path'),{pathToFileURL}=require('node:url');
const assert=require('node:assert/strict'),{execFileSync}=require('node:child_process');
const {chromium}=require(process.env.AWAITLAB_PLAYWRIGHT||'D:/CodexWork/cache/branchforge-browser/node_modules/playwright');
const root=path.resolve(__dirname,'..'),temp='D:/CodexWork/temp/awaitlab/browser';
fs.mkdirSync(temp,{recursive:true});process.env.TEMP=temp;process.env.TMP=temp;
execFileSync('python',['-c',"import json;from awaitlab.report import write_report;from pathlib import Path;p=Path('artifacts');write_report(json.loads((p/'parallel-initial.json').read_text(encoding='utf-8')),p/'legacy-current-renderer.html')"],{cwd:root});
execFileSync('python',['-c',`import json,copy
from pathlib import Path
from awaitlab.report import write_report
r=json.loads(Path('artifacts/sqlite-http-latest.json').read_text(encoding='utf-8'))
r['title']='UI fixture: replayed trace, no new measurement'
for c in r['comparisons']:
 for mode in ['control','treatment']:c['blocks'][1][mode]['trace']=copy.deepcopy(c['blocks'][0][mode]['trace'])
write_report(r,Path('${temp}/trace-fixture.html'))
for c in r['comparisons']:
 for b in c['blocks']:
  for mode in ['control','treatment']:b[mode]['trace']=[]
write_report(r,Path('${temp}/empty-trace-fixture.html'))`],{cwd:root});
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.AWAITLAB_CHROMIUM||'D:/CodexWork/cache/ms-playwright/chromium-1243/chrome-win64/chrome.exe'});
 const page=await browser.newPage({viewport:{width:1440,height:1080}});
 const errors=[],remote=[],checks=[];page.on('pageerror',e=>errors.push(e.message));
 page.on('request',r=>{if(/^https?:/.test(r.url()))remote.push(r.url());});
 try{
  await page.goto(pathToFileURL(path.join(root,'artifacts','sqlite-latest.html')).href);
  await page.getByRole('heading',{name:'把优化方向，交给实验。'}).waitFor();
  checks.push('standalone SQLite report');
  assert.equal(await page.locator('[data-arm]').count(),2);checks.push('two real replacement arms');
  await page.getByRole('heading',{name:'本轮支持继续验证此优化'}).waitFor();checks.push('supported evidence grade');
  assert((await page.locator('body').innerText()).includes('Holm 调整 p='));checks.push('adjusted inference visible');
  assert.equal(await page.getByRole('heading',{name:'真实工作负载证据'}).count(),1);checks.push('workload provenance');
  assert((await page.locator('body').innerText()).includes('50000 行'));checks.push('actual fixture size');
  assert((await page.locator('pre').allTextContents()).some(t=>t.includes('SELECT id, name, balance')));checks.push('actual SQL');
  await page.screenshot({path:path.join(root,'artifacts','sqlite-report-desktop.png'),fullPage:true});
  const placebo=JSON.parse(fs.readFileSync(path.join(root,'artifacts','sqlite-latest.json'),'utf8')).comparisons[1];
  const titles={no_observed_gain:'本轮未观察到收益',below_practical_threshold:'变化未达到实用门槛',inconclusive:'收益证据尚不充分'};
  await page.locator('[data-arm="1"]').click();
  await page.getByRole('heading',{name:titles[placebo.evidence_level]}).waitFor();checks.push('placebo not promoted');
  assert(await page.locator('.metrics strong').evaluate(el=>el.classList.contains('neutral')));checks.push('placebo neutral presentation');
  await page.locator('#trace-mode').selectOption('treatment');
  assert((await page.locator('.lane').count())>0);checks.push('treatment timeline');
  await page.goto(pathToFileURL(path.join(root,'artifacts','sqlite-http-latest.html')).href);
  assert((await page.locator('.context').innerText()).includes('loopback TCP'));checks.push('real HTTP transport scope');
  const httpReport=JSON.parse(fs.readFileSync(path.join(root,'artifacts','sqlite-http-latest.json'),'utf8'));
  assert((await page.locator('footer').innerText()).includes(httpReport.library_version));checks.push('library version');
  assert.equal(await page.locator('.observer tbody tr').count(),5);checks.push('response, worker cycle and check separately shown');
  const expectedCheck=httpReport.comparisons[0].blocks.reduce((sum,b)=>sum+b.control.output_check.mean_ms,0)/httpReport.settings.blocks;
  assert((await page.locator('.observer tbody tr').nth(2).innerText()).includes(expectedCheck.toFixed(3)));checks.push('check cost matches recorded block mean');
  assert.deepEqual(await page.locator('#trace-request option').evaluateAll(es=>es.map(e=>e.value)),['0','1']);checks.push('sampled request selector');
  assert.equal(await page.locator('.bar').count(),3);assert.equal(await page.locator('.lane').count(),3);checks.push('HTTP and database spans both visible');
  await page.locator('.coverage summary').click();assert.equal(await page.locator('.coverage tbody tr').count(),2);checks.push('sampled HTTP and operation coverage');
  assert((await page.locator('.coverage').innerText()).includes('不能解释为 CPU 时间'));checks.push('uncovered window not called CPU time');
  const boxes=await page.locator('.bar').evaluateAll(es=>es.map(e=>{const b=e.getBoundingClientRect();return {x:b.x,y:b.y,w:b.width,h:b.height};}));
  for(let a=0;a<boxes.length;a++)for(let b=a+1;b<boxes.length;b++)assert(!(Math.min(boxes[a].x+boxes[a].w,boxes[b].x+boxes[b].w)>Math.max(boxes[a].x,boxes[b].x)&&Math.min(boxes[a].y+boxes[a].h,boxes[b].y+boxes[b].h)>Math.max(boxes[a].y,boxes[b].y)));
  checks.push('no overlap hides nested spans');
  await page.getByRole('button',{name:/http.server · #/}).click();assert((await page.locator('#span-detail').innerText()).includes('request'));checks.push('server parent linked to request');
  await page.getByRole('button',{name:/customer.lookup · #/}).focus();await page.keyboard.press('Enter');assert((await page.locator('#span-detail').innerText()).includes('http.server'));checks.push('keyboard-accessible recorded parent');
  await page.locator('#trace-request').selectOption('1');assert.equal(await page.locator('.timeline').getAttribute('data-request'),'1');checks.push('switch sampled request');
  await page.locator('#trace-mode').selectOption('treatment');assert.equal(await page.locator('.timeline').getAttribute('data-request'),'1');checks.push('preserve request across modes');
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:path.join(root,'artifacts','sqlite-http-mobile.png'),fullPage:true});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));checks.push('mobile width');
  await page.locator('.calibration summary').click();
  assert.equal(await page.locator('.calibration tbody tr').count(),8);checks.push('timer calibration');
  await page.goto(pathToFileURL(path.join(temp,'trace-fixture.html')).href);
  await page.locator('#trace-block').selectOption('1');assert.equal(await page.locator('.timeline').getAttribute('data-block'),'1');checks.push('sampled block selector with replay fixture');
  await page.goto(pathToFileURL(path.join(temp,'empty-trace-fixture.html')).href);
  assert.equal(await page.locator('.bar').count(),0);assert((await page.locator('body').innerText()).includes('此批次未采样该请求'));checks.push('empty sampling remains usable');
  await page.goto(pathToFileURL(path.join(root,'artifacts','legacy-current-renderer.html')).href);
  await page.locator('[data-arm="0"]').click();await page.getByRole('heading',{name:'测量对额外等待的敏感度'}).waitFor();checks.push('legacy delay interpretation');
  await page.locator('[data-arm="3"]').click();await page.getByRole('heading',{name:'历史报告：未按新版规则分级'}).waitFor();checks.push('legacy result not silently upgraded');
  assert((await page.locator('.observer').innerText()).includes('历史数据未记录'));checks.push('legacy check cost not assumed zero');
  assert(!(await page.locator('body').innerText()).includes('NaN'));checks.push('missing legacy values handled');
  assert.deepEqual(errors,[]);checks.push('no JavaScript exceptions');assert.deepEqual(remote,[]);checks.push('no network requests');
  const summary={passed:true,checks};
  fs.writeFileSync(path.join(root,'artifacts','browser-check.json'),JSON.stringify(summary,null,2));
  console.log(`${checks.length} browser checks passed`);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
