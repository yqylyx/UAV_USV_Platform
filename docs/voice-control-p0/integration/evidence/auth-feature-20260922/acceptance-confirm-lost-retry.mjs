import {chromium} from 'playwright';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const output=process.env.P0_GAP_OUTPUT;await fs.mkdir(output,{recursive:true});
const secret=JSON.parse((await fs.readFile(new URL('../p0-integration/credentials.json',import.meta.url),'utf8')).replace(/^\uFEFF/,''));
const browser=await chromium.launch({channel:'msedge',headless:true,args:['--enable-unsafe-swiftshader','--use-angle=swiftshader']});
const page=await browser.newPage({viewport:{width:1600,height:1000}});const network=[],checks=[];let disconnected=false,failure=null;
page.on('response',async r=>{if(/\/api\/(voice|algorithm-runs)/.test(r.url()))try{network.push({at:new Date().toISOString(),url:r.url(),status:r.status(),method:r.request().method(),request:r.request().postDataJSON(),body:await r.json()});}catch{}});
let dropped=null;
await page.route('**/api/voice/commands/proposals',async route=>{
 if(!dropped){const response=await route.fetch();if(response.status()===201){dropped={body:await response.json(),request:route.request().postDataJSON(),key:route.request().headers()['idempotency-key']};await route.abort('failed');return;}await route.fulfill({response});return;}
 await route.continue();
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
 await page.waitForFunction(()=>document.body.innerText.includes('上次写请求结果未知'),null,{timeout:15000});
 assert(dropped);const original=dropped.body.data;
 await page.reload();await click('语音控制');
 const recovered=await page.waitForResponse(r=>r.url().endsWith('/commands/proposals')&&r.status()===200,{timeout:20000});
 const recoveredBody=await recovered.json();assert.equal(recoveredBody.data.proposalId,original.proposalId);assert.equal(recoveredBody.data.expiresAt,original.expiresAt);
 assert.deepEqual(recovered.request().postDataJSON(),dropped.request);assert.equal(recovered.request().headers()['idempotency-key'],dropped.key);
 checks.push({caseId:'X14',result:'PASS',proposalId:original.proposalId,expiresAt:original.expiresAt});
 await page.waitForResponse(r=>r.url().endsWith('/presentation/reports')&&r.status()===200&&r.request().postDataJSON()?.kind==='SCENE_READY',{timeout:45000});
 let lostConfirm=null;await page.route('**/api/voice/commands/*/confirm',async route=>{if(!lostConfirm){const response=await route.fetch();lostConfirm={status:response.status(),body:await response.json()};await route.abort('failed');}else await route.continue();});
 const repeated=await page.evaluate(async p=>{const csrf=(await(await fetch('/api/auth/csrf')).json()).data;const key=crypto.randomUUID();const body={expectedPlanVersion:p.planVersion,expectedPlanHash:p.planHash};const url='/api/voice/commands/'+p.proposalId+'/confirm';const opts={method:'POST',headers:{'Content-Type':'application/json',[csrf.headerName]:csrf.token,'Idempotency-Key':key},body:JSON.stringify(body)};let a;try{await fetch(url,opts);a={unexpectedResponse:true}}catch(e){a={networkError:true}};const second=await fetch(url,opts);const b={status:second.status,body:await second.json()};return {first:a,second:b,key}},original);
 assert.equal(repeated.first.networkError,true);assert.equal(lostConfirm.status,202);assert.equal(repeated.second.status,200);assert.equal(lostConfirm.body.data.execution.executionId,repeated.second.body.data.execution.executionId);assert.equal(lostConfirm.body.data.execution.commandId,repeated.second.body.data.execution.commandId);
 checks.push({caseId:'I08',result:'PASS',lostConfirm,...repeated});
 await page.screenshot({path:output+'/proposal-recovery.png',timeout:20000});
} catch(e){failure=String(e);process.exitCode=1;console.error(e);await page.screenshot({path:output+'/failure.png',timeout:15000}).catch(()=>{});}
finally {
 try {const prep=network.find(n=>n.url.endsWith('/prepare')&&n.status===200);if(prep){const run=prep.url.match(/algorithm-runs\/(\d+)/)[1];const cleanup=await page.evaluate(async run=>{const c=await(await fetch('/api/auth/csrf')).json();const r=await fetch('/api/algorithm-runs/'+run+'/stop',{method:'POST',headers:{'Content-Type':'application/json',[c.data.headerName]:c.data.token},body:'{}'});return {status:r.status,body:await r.json()}},run);checks.push({cleanup});}}catch(e){checks.push({cleanupError:String(e)})}
 try{await fs.writeFile(output+'/diagnostics.json',JSON.stringify({diagnostics,text:await page.locator('body').innerText(),messages:await page.evaluate(()=>window.__p0Messages),frames:page.frames().map(f=>f.url())},null,2))}catch{}
 await fs.writeFile(output+'/browser-proposal-recovery.json',JSON.stringify({checks,failure,network},null,2));await browser.close();
}
console.log(JSON.stringify({failure,checks:checks.map(c=>({caseId:c.caseId,result:c.result,kind:c.kind}))}));
