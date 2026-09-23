import {chromium} from 'playwright';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const output=process.env.P0_GAP_OUTPUT;await fs.mkdir(output,{recursive:true});
const secret=JSON.parse((await fs.readFile(new URL('../p0-integration/credentials.json',import.meta.url),'utf8')).replace(/^\uFEFF/,''));
const browser=await chromium.launch({channel:'msedge',headless:true,args:['--enable-unsafe-swiftshader','--use-angle=swiftshader']});
const page=await browser.newPage({viewport:{width:1600,height:1000}});const network=[],checks=[];let disconnected=false,failure=null;
page.on('response',async r=>{if(/\/api\/(voice|algorithm-runs)/.test(r.url()))try{network.push({at:new Date().toISOString(),url:r.url(),status:r.status(),method:r.request().method(),request:r.request().postDataJSON(),body:await r.json()});}catch{}});
let arm=false,held=false,active=0,maxActive=0;
await page.route('**/api/voice/contexts/*/presentation/challenges',async route=>{
 active++;maxActive=Math.max(maxActive,active);
 try {
  const response=await route.fetch();
  if(arm&&!held&&route.request().postDataJSON()?.kind==='SCENE_READY'){
   held=true;checks.push({kind:'scene-response-delayed',at:new Date().toISOString()});
   await new Promise(r=>setTimeout(r,8000));
  }
  checks.push({kind:"challenge-response-release",at:new Date().toISOString()});
  await route.fulfill({response});
 } finally {active--;}
});
const diagnostics=[];
page.on('console',m=>{if(diagnostics.length<150)diagnostics.push({type:m.type(),text:m.text().slice(0,500)})});
page.on('pageerror',e=>diagnostics.push({error:String(e)}));
await page.addInitScript(()=>{window.__p0Messages=[];window.addEventListener('message',e=>{try{let d=typeof e.data==='string'?JSON.parse(e.data):e.data;let m=d?.message??d;if(m?.type&&window.__p0Messages.length<300)window.__p0Messages.push(m)}catch{}})});
const click=async name=>page.getByRole('button',{name,exact:true}).click({timeout:25000});
try {
 await page.goto('http://127.0.0.1:15174/?workspace=simulation');await page.getByPlaceholder('请输入用户名').fill('p0_admin');await page.getByPlaceholder('请输入密码').fill(secret.adminPassword);await click('进入控制台');await click('语音控制');
 await page.waitForResponse(r=>r.url().endsWith('/presentation/reports')&&r.status()===200&&r.request().postDataJSON()?.kind==='SCENE_READY',{timeout:90000});
 await click('开始任务 创建并核对指令提案');
 arm=true;
 for(let i=0;i<100&&!held;i++)await page.waitForTimeout(100);
 assert(held,'No scene probe held');
 await click('确认执行');
 await page.waitForFunction(()=>document.body.innerText.includes('算法结果：SUCCESS')&&document.body.innerText.includes('Unity 已应用'),null,{timeout:60000});
 const heldAt=checks.find(c=>c.kind==='scene-response-delayed').at;
 const released=checks.find(c=>c.kind==='challenge-response-release'&&c.at>heldAt).at;
 assert(network.some(n=>n.at>heldAt&&n.at<released&&(n.body?.data?.execution??n.body?.data)?.state==='SUCCEEDED'),'No actual execution success observed while scene request held');
 assert.equal(maxActive,1,'Concurrent challenge HTTP requests');
 assert(network.some(n=>n.url.endsWith('/presentation/challenges')&&n.request?.kind==='FRAME_APPLIED'&&n.status===200));
 checks.push({caseId:'X08',result:'PASS',maxActiveChallenges:maxActive,at:new Date().toISOString()});
 await page.screenshot({path:output+'/browser-competition.png',timeout:20000});
} catch(e){failure=String(e);process.exitCode=1;console.error(e);await page.screenshot({path:output+'/failure.png',timeout:15000}).catch(()=>{});}
finally {
 try {const prep=network.find(n=>n.url.endsWith('/prepare')&&n.status===200);if(prep){const run=prep.url.match(/algorithm-runs\/(\d+)/)[1];const cleanup=await page.evaluate(async run=>{const c=await(await fetch('/api/auth/csrf')).json();const r=await fetch('/api/algorithm-runs/'+run+'/stop',{method:'POST',headers:{'Content-Type':'application/json',[c.data.headerName]:c.data.token},body:'{}'});return {status:r.status,body:await r.json()}},run);checks.push({cleanup});}}catch(e){checks.push({cleanupError:String(e)})}
 try{await fs.writeFile(output+'/diagnostics.json',JSON.stringify({diagnostics,text:await page.locator('body').innerText(),messages:await page.evaluate(()=>window.__p0Messages),frames:page.frames().map(f=>f.url())},null,2))}catch{}
 await fs.writeFile(output+'/browser-competition.json',JSON.stringify({checks,failure,network},null,2));await browser.close();
}
console.log(JSON.stringify({failure,checks:checks.map(c=>({caseId:c.caseId,result:c.result,kind:c.kind}))}));
