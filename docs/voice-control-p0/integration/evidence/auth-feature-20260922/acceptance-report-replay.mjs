import {chromium} from 'playwright';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const output=process.env.P0_GAP_OUTPUT;await fs.mkdir(output,{recursive:true});
const secret=JSON.parse((await fs.readFile(new URL('../p0-integration/credentials.json',import.meta.url),'utf8')).replace(/^\uFEFF/,''));
const browser=await chromium.launch({channel:'msedge',headless:true,args:['--enable-unsafe-swiftshader','--use-angle=swiftshader']});
const page=await browser.newPage({viewport:{width:1600,height:1000}});const network=[],checks=[];let disconnected=false,failure=null;
page.on('response',async r=>{if(/\/api\/(voice|algorithm-runs)/.test(r.url()))try{network.push({at:new Date().toISOString(),url:r.url(),status:r.status(),method:r.request().method(),request:r.request().postDataJSON(),body:await r.json()});}catch{}});
const diagnostics=[];
page.on('console',m=>{if(diagnostics.length<150)diagnostics.push({type:m.type(),text:m.text().slice(0,500)})});
page.on('pageerror',e=>diagnostics.push({error:String(e)}));
await page.addInitScript(()=>{window.__p0Messages=[];window.addEventListener('message',e=>{try{let d=typeof e.data==='string'?JSON.parse(e.data):e.data;let m=d?.message??d;if(m?.type&&window.__p0Messages.length<300)window.__p0Messages.push(m)}catch{}})});
const click=async name=>page.getByRole('button',{name,exact:true}).click({timeout:25000});
try {
 await page.goto('http://127.0.0.1:15174/?workspace=simulation');await page.getByPlaceholder('请输入用户名').fill('p0_admin');await page.getByPlaceholder('请输入密码').fill(secret.adminPassword);await click('进入控制台');await click('语音控制');
 await page.waitForResponse(r=>r.url().endsWith('/presentation/reports')&&r.status()===200&&r.request().postDataJSON()?.kind==='SCENE_READY',{timeout:90000});
 const report=network.filter(n=>n.url.endsWith('/presentation/reports')&&n.status===200&&n.request?.kind==='SCENE_READY').at(-1);
 const response=await page.waitForResponse(r=>r.url().endsWith('/presentation/reports')&&r.status()===200&&r.request().postDataJSON()?.kind==='SCENE_READY',{timeout:15000});
 const original={url:response.url(),body:response.request().postDataJSON(),key:response.request().headers()['idempotency-key']};
 await page.route('**/api/voice/contexts/*/presentation/reports',async route=>{if(route.request().headers()['x-p0-replay']==='1')await route.continue();else await route.abort('failed');});
 await page.waitForTimeout(12000);
 const result=await page.evaluate(async original=>{const c=(await(await fetch('/api/auth/csrf')).json()).data;const send=async key=>{const r=await fetch(original.url,{method:'POST',headers:{'Content-Type':'application/json',[c.headerName]:c.token,'Idempotency-Key':key,'X-P0-Replay':'1'},body:JSON.stringify(original.body)});return {status:r.status,body:await r.json()}};const same=await send(original.key);const changed=await send(crypto.randomUUID());const context=(await(await fetch(original.url.replace('/presentation/reports',''))).json()).data;return {same,changed,context}},original);
 assert.equal(result.same.status,200);assert.equal(result.changed.status,409);assert.equal(result.context.sceneReady,false);
 checks.push({caseId:'X09',result:'PASS',original,...result});
 await page.screenshot({path:output+'/report-replay.png',timeout:20000});
} catch(e){failure=String(e);process.exitCode=1;console.error(e);await page.screenshot({path:output+'/failure.png',timeout:15000}).catch(()=>{});}
finally {
 try {const prep=network.find(n=>n.url.endsWith('/prepare')&&n.status===200);if(prep){const run=prep.url.match(/algorithm-runs\/(\d+)/)[1];const cleanup=await page.evaluate(async run=>{const c=await(await fetch('/api/auth/csrf')).json();const r=await fetch('/api/algorithm-runs/'+run+'/stop',{method:'POST',headers:{'Content-Type':'application/json',[c.data.headerName]:c.data.token},body:'{}'});return {status:r.status,body:await r.json()}},run);checks.push({cleanup});}}catch(e){checks.push({cleanupError:String(e)})}
 try{await fs.writeFile(output+'/diagnostics.json',JSON.stringify({diagnostics,text:await page.locator('body').innerText(),messages:await page.evaluate(()=>window.__p0Messages),frames:page.frames().map(f=>f.url())},null,2))}catch{}
 await fs.writeFile(output+'/browser-report-replay.json',JSON.stringify({checks,failure,network},null,2));await browser.close();
}
console.log(JSON.stringify({failure,checks:checks.map(c=>({caseId:c.caseId,result:c.result,kind:c.kind}))}));
