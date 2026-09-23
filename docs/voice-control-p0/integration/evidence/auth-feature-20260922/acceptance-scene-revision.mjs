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
 const old=await page.evaluate(()=>window.__p0Messages.filter(m=>m.type==='PRESENTATION_REPORT').at(-1));assert(old);
 const oldPayload=old.payload??old;const start=network.length;
 const readyAgain=page.waitForResponse(r=>r.url().endsWith('/presentation/reports')&&r.status()===200&&r.request().postDataJSON()?.kind==='SCENE_READY'&&r.request().postDataJSON()?.bindingId!==oldPayload.bindingId,{timeout:90000});
 await click('生成场景');
 await readyAgain;
 const fresh=await page.evaluate(()=>window.__p0Messages.filter(m=>m.type==='PRESENTATION_REPORT').at(-1));const freshPayload=fresh.payload??fresh;
 assert.equal(oldPayload.unityInstanceId,freshPayload.unityInstanceId);assert(freshPayload.sceneRevision>oldPayload.sceneRevision);assert.notEqual(oldPayload.bindingId,freshPayload.bindingId);assert(freshPayload.sceneRevision>=1);
 const injectionStart=network.length;
 await page.evaluate(old=>{const frame=document.querySelector('iframe[src*="unity-virtual-fleet"]');window.dispatchEvent(new MessageEvent('message',{source:frame.contentWindow,origin:location.origin,data:{source:'unity-webgl',message:old}}));},old);
 await page.waitForTimeout(1200);
 assert.equal(network.slice(injectionStart).filter(n=>n.url.endsWith('/presentation/reports')&&n.request?.requestId===oldPayload.requestId).length,0);
 assert.equal(network.slice(start).filter(n=>n.url.endsWith('/prepare')&&n.status===200).length,1);
 checks.push({caseId:'X07',result:'PASS',old:oldPayload,fresh:freshPayload,oldReportHttpCount:0,explicitRegeneratePrepareCount:1});
 await page.screenshot({path:output+'/scene-revision.png',timeout:20000});
} catch(e){failure=String(e);process.exitCode=1;console.error(e);await page.screenshot({path:output+'/failure.png',timeout:15000}).catch(()=>{});}
finally {
 try {const prep=network.find(n=>n.url.endsWith('/prepare')&&n.status===200);if(prep){const run=prep.url.match(/algorithm-runs\/(\d+)/)[1];const cleanup=await page.evaluate(async run=>{const c=await(await fetch('/api/auth/csrf')).json();const r=await fetch('/api/algorithm-runs/'+run+'/stop',{method:'POST',headers:{'Content-Type':'application/json',[c.data.headerName]:c.data.token},body:'{}'});return {status:r.status,body:await r.json()}},run);checks.push({cleanup});}}catch(e){checks.push({cleanupError:String(e)})}
 try{await fs.writeFile(output+'/diagnostics.json',JSON.stringify({diagnostics,text:await page.locator('body').innerText(),messages:await page.evaluate(()=>window.__p0Messages),frames:page.frames().map(f=>f.url())},null,2))}catch{}
 await fs.writeFile(output+'/browser-scene-revision.json',JSON.stringify({checks,failure,network},null,2));await browser.close();
}
console.log(JSON.stringify({failure,checks:checks.map(c=>({caseId:c.caseId,result:c.result,kind:c.kind}))}));
