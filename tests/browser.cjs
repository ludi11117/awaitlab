const fs=require('node:fs'),path=require('node:path'),{pathToFileURL}=require('node:url');
const assert=require('node:assert/strict');
const {chromium}=require(process.env.AWAITLAB_PLAYWRIGHT||'D:/CodexWork/cache/branchforge-browser/node_modules/playwright');
const root=path.resolve(__dirname,'..'),temp='D:/CodexWork/temp/awaitlab/browser';
fs.mkdirSync(temp,{recursive:true});process.env.TEMP=temp;process.env.TMP=temp;
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.AWAITLAB_CHROMIUM||'D:/CodexWork/cache/ms-playwright/chromium-1243/chrome-win64/chrome.exe'});
 const page=await browser.newPage({viewport:{width:1440,height:1080}});
 const errors=[],remote=[];page.on('pageerror',e=>errors.push(e.message));
 page.on('request',r=>{if(/^https?:/.test(r.url()))remote.push(r.url());});
 try{
  await page.goto(pathToFileURL(path.join(root,'artifacts','parallel-latest.html')).href);
  await page.getByRole('heading',{name:'把优化方向，交给实验。'}).waitFor();
  assert.equal(await page.locator('[data-arm]').count(),4);
  await page.screenshot({path:path.join(root,'artifacts','report-desktop.png'),fullPage:true});
  await page.locator('[data-arm="0"]').click();
  await page.getByRole('heading',{name:'测量对额外等待的敏感度'}).waitFor();
  await page.locator('#trace-mode').selectOption('treatment');
  assert((await page.locator('.lane').count())>1);
  await page.locator('[data-arm="3"]').click();
  await page.getByRole('heading',{name:'此负载下观察到收益'}).waitFor();
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:path.join(root,'artifacts','report-mobile.png'),fullPage:true});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.goto(pathToFileURL(path.join(root,'artifacts','pool-latest.html')).href);
  await page.locator('.calibration summary').click();
  assert.equal(await page.locator('.calibration tbody tr').count(),8);
  await page.goto(pathToFileURL(path.join(root,'artifacts','fastapi-tcp.html')).href);
  await page.getByRole('heading',{name:'把优化方向，交给实验。'}).waitFor();
  assert((await page.locator('.context').innerText()).includes('loopback TCP'));
  assert((await page.locator('footer').innerText()).includes('0.2.0'));
  await page.screenshot({path:path.join(root,'artifacts','tcp-report-mobile.png'),fullPage:true});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  assert.deepEqual(errors,[]);assert.deepEqual(remote,[]);
  const summary={passed:true,checks:['local standalone report','four selectable arms','delay interpretation','control/treatment timeline','actual replacement result','mobile width','timer calibration','TCP transport scope','report library version','TCP mobile width','no JS exceptions','no network requests']};
  fs.writeFileSync(path.join(root,'artifacts','browser-check.json'),JSON.stringify(summary,null,2));
  console.log('12 browser checks passed');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
