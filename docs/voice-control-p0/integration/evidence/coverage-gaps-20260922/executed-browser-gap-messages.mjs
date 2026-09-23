import {chromium} from 'playwright';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const output=process.env.P0_GAP_OUTPUT;if(!output)throw Error('P0_GAP_OUTPUT required');await fs.mkdir(output,{recursive:true});
const secret=JSON.parse((await fs.readFile(new URL('../p0-integration/credentials.json',import.meta.url),'utf8')).replace(/^\uFEFF/,''));
const browser=await chromium.launch({channel:'msedge',headless:true,args:['--enable-unsafe-swiftshader','--use-angle=swiftshader']});
const page=await browser.newPage({viewport:{width:1600,height:1000}});const network=[],checks=[];
page.on('response',async r=>{if(/\/api\/(voice|algorithm-runs)/.test(r.url()))try{network.push({at:new Date().toISOString(),url:r.url(),status:r.status(),method:r.request().method(),request:r.request().postDataJSON(),body:await r.json()});}catch{}});
await page.addInitScript(()=>{
 window.__held=[];window.__holdReports=false;
 window.addEventListener('message',e=>{let data=e.data;try{if(typeof data==='string')data=JSON.parse(data)}catch{return}
  const m=data?.source==='unity-webgl'?data.message:data;
  if(m?.type==='PRESENTATION_REPORT'&&window.__holdReports&&!e.__p0Injected){window.__held.push({data,origin:e.origin});e.stopImmediatePropagation();}
 },true);
});
async function click(name){await page.getByRole('button',{name,exact:true}).click({timeout:25000});}
let failure=null;
try {
 await page.goto('http://127.0.0.1:15174/?workspace=simulation');await page.getByPlaceholder('请输入用户名').fill('p0_admin');await page.getByPlaceholder('请输入密码').fill(secret.adminPassword);await click('进入控制台');await click('语音控制');
 await page.waitForResponse(r=>r.url().endsWith('/presentation/reports')&&r.status()===200&&r.request().postDataJSON()?.kind==='SCENE_READY',{timeout:90000});
 await page.evaluate(()=>window.__holdReports=true);
 await page.waitForFunction(()=>window.__held.length>0,null,{timeout:25000});
 const held=await page.evaluate(()=>window.__held.at(-1));
 const message=held.data.source==='unity-webgl'?held.data.message:held.data;
 const reportId=message.requestId??message.payload.requestId;assert(reportId);
 const start=network.length;
 for(const mode of ['wrong-origin','wrong-source','old-generation','old-binding']){
  await page.evaluate(({held,mode})=>{
   const data=structuredClone(held.data);const m=data.source==='unity-webgl'?data.message:data;
   if(mode==='old-generation')m.payload.runtimeGeneration=crypto.randomUUID();
   if(mode==='old-binding')m.payload.bindingId=crypto.randomUUID();
   const frame=[...document.querySelectorAll('iframe')].find(f=>f.src.includes('unity-virtual-fleet'));
   if(!frame)throw Error('Real Unity iframe missing');
   const event=new MessageEvent('message',{data,origin:mode==='wrong-origin'?'http://untrusted.invalid':location.origin,source:mode==='wrong-source'?window:frame.contentWindow});
   Object.defineProperty(event,'__p0Injected',{value:true});window.dispatchEvent(event);
  },{held,mode});
  await page.waitForTimeout(250);
  const reports=network.slice(start).filter(e=>e.url.endsWith('/presentation/reports')&&e.request?.requestId===reportId);
  assert.equal(reports.length,0,mode+' emitted an HTTP presentation report');
  checks.push({caseId:'X06',mode,result:'PASS',requestId:reportId,matchingHttpReports:0,at:new Date().toISOString()});
 }
 await click('重新接管展示');
 const bindingResponse=await page.waitForResponse(r=>r.url().endsWith('/presentation/bindings')&&r.status()===200,{timeout:15000}).catch(()=>null);
 await page.waitForTimeout(400);
 await page.evaluate(held=>{
  const frame=[...document.querySelectorAll('iframe')].find(f=>f.src.includes('unity-virtual-fleet'));
  const e=new MessageEvent('message',{data:held.data,origin:location.origin,source:frame.contentWindow});Object.defineProperty(e,'__p0Injected',{value:true});window.dispatchEvent(e);
 },held);
 await page.waitForTimeout(400);
 assert.equal(network.slice(start).filter(e=>e.url.endsWith('/presentation/reports')&&e.request?.requestId===reportId).length,0);
 checks.push({caseId:'X07/C05',mode:'replay-real-old-report-after-rebinding',result:'PASS',requestId:reportId,matchingHttpReports:0});
 await page.evaluate(()=>window.__holdReports=false);
 await page.waitForResponse(r=>r.url().endsWith('/presentation/reports')&&r.status()===200,{timeout:30000});
 await page.screenshot({path:output+'/browser-negative-messages.png',timeout:20000});
 console.log('Browser negative message checks PASS',checks.length);
} catch(e){failure=String(e);console.error(e);process.exitCode=1;}
finally {
 try {
  await page.evaluate(()=>window.__holdReports=false);
  const prep=network.find(e=>e.url.endsWith('/prepare')&&e.status===200)?.body?.data;
  if(prep){const cleanup=await page.evaluate(async run=>{const c=await(await fetch('/api/auth/csrf')).json();const r=await fetch('/api/algorithm-runs/'+run+'/stop',{method:'POST',headers:{'Content-Type':'application/json',[c.data.headerName]:c.data.token},body:'{}'});return {status:r.status,body:await r.json()}},prep.runId??prep.algorithmRunId??network.find(e=>e.url.endsWith('/prepare')).url.match(/algorithm-runs\/(\d+)/)[1]);checks.push({cleanup});}
 }catch(e){checks.push({cleanupError:String(e)})}
 await fs.writeFile(output+'/browser-injection.json',JSON.stringify({checks,failure,network},null,2));await browser.close();
}
