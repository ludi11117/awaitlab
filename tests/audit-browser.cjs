const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const {chromium}=require(process.env.AWAITLAB_PLAYWRIGHT||'D:/CodexWork/cache/branchforge-browser/node_modules/playwright');
const root=path.resolve(__dirname,'..');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.AWAITLAB_CHROMIUM||'D:/CodexWork/cache/ms-playwright/chromium-1243/chrome-win64/chrome.exe'});
 const page=await browser.newPage(),errors=[],remote=[],checks=[];
 page.on('pageerror',e=>errors.push(String(e)));
 page.on('request',r=>{if(/^https?:/.test(r.url()))remote.push(r.url());});
 try{
  await page.setViewportSize({width:1280,height:900});
  await page.goto(pathToFileURL(path.join(root,'artifacts/defensive-logic-v0.11.0.html')).href);
  await page.getByRole('heading',{name:'防御代码审查',exact:true}).waitFor();checks.push('offline audit heading');
  assert.equal(await page.locator('.finding').count(),4);checks.push('all four findings rendered');
  assert.equal(await page.locator('.labels').filter({hasText:'路径确定的冗余'}).count(),3);checks.push('three proven path findings');
  assert.equal(await page.locator('.labels').filter({hasText:'需要业务复核'}).count(),1);checks.push('review-only exception separated');
  assert((await page.locator('.finding').first().innerText()).includes('第 5 行'));checks.push('related guard line visible');
  assert((await page.locator('.source').first().innerText()).includes('None is customer'));checks.push('source snippet visible');
  assert((await page.locator('.patch').innerText()).includes('-    if None is customer:'));checks.push('actual unified diff visible');
  await page.locator('.finding summary').first().click();
  assert.equal(await page.locator('.finding details').first().getAttribute('open'),null);checks.push('native evidence disclosure works');
  await page.screenshot({path:path.join(root,'artifacts/defensive-logic-desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));checks.push('mobile page stays within viewport');
  await page.screenshot({path:path.join(root,'artifacts/defensive-logic-mobile.png'),fullPage:true});
  assert.deepEqual(errors,[]);checks.push('no browser exceptions');
  assert.deepEqual(remote,[]);checks.push('no remote requests');
  assert.equal(await page.locator('script').count(),0);checks.push('report needs no JavaScript');
  fs.writeFileSync(path.join(root,'artifacts/audit-browser-v0.11.0.json'),JSON.stringify({passed:true,checks},null,2)+'\n');
  console.log(`${checks.length} audit browser checks passed`);
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
