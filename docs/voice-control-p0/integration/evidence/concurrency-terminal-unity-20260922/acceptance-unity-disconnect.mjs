import {chromium} from 'playwright';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const output=process.env.P0_GAP_OUTPUT;await fs.mkdir(output,{recursive:true});
const secret=JSON.parse((await fs.readFile(new URL('../p0-integration/credentials.json',import.meta.url),'utf8')).replace(/^\uFEFF/,''));
const browser=await chromium.launch({channel:'msedge',headless:true,args:['--enable-unsafe-swiftshader','--use-angle=swiftshader']});
const page=await browser.newPage({viewport:{width:1600,height:1000}});const network=[],checks=[];let disconnected=false,failure=null;
page.on('response',async r=>{if(/\/api\/(voice|algorithm-runs)/.test(r.url()))try{network.push({at:new Date().toISOString(),url:r.url(),status:r.status(),method:r.request().method(),request:r.request().postDataJSON(),body:await r.json()});}catch{}});
await page.route('**/api/voice/commands/*/confirm',async route=>{
 const response=await route.fetch();
 if(!disconnected&&response.status()===202){
  const info=await page.evaluate(()=>{const f=[...document.querySelectorAll('iframe')].find(f=>f.src.includes('unity-virtual-fleet'));if(!f)throw Error('Real Unity iframe absent');const src=f.src;f.remove();return {src,remaining:document.querySelectorAll('iframe').length}});
  checks.push({at:new Date().toISOString(),kind:'real-iframe-removed',...info});disconnected=true;
 }
 await route.fulfill({response});
});
const click=async name=>page.getByRole('button',{name,exact:true}).click({timeout:25000});
try {
 await page.goto('http://127.0.0.1:15174/?workspace=simulation');await page.getByPlaceholder('请输入用户名').fill('p0_admin');await page.getByPlaceholder('请输入密码').fill(secret.adminPassword);await click('进入控制台');await click('语音控制');
 await page.waitForResponse(r=>r.url().endsWith('/presentation/reports')&&r.status()===200&&r.request().postDataJSON()?.kind==='SCENE_READY',{timeout:90000});
 await click('开始任务 创建并核对指令提案');await click('确认执行');
 await page.waitForFunction(()=>document.body.innerText.includes('算法结果：SUCCESS')&&document.body.innerText.includes('Unity 展示已过期'),null,{timeout:60000});
 const body=await page.locator('body').innerText();
 assert(disconnected);assert(body.includes('算法结果：SUCCESS'));assert(body.includes('Unity 展示已过期'));
 const observed=network.map(n=>n.body?.data?.execution??n.body?.data).filter(n=>n?.executionId&&n?.state==='SUCCEEDED');
 assert(observed.some(n=>n.presentationStatus==='PENDING'));assert(observed.some(n=>n.presentationStatus==='STALE'));
 checks.push({caseId:'X19/C04',result:'PASS',at:new Date().toISOString(),execution:observed.at(-1),body});
 await page.screenshot({path:output+'/unity-disconnected.png',timeout:20000});
} catch(e){failure=String(e);process.exitCode=1;console.error(e);await page.screenshot({path:output+'/failure.png',timeout:15000}).catch(()=>{});}
finally {
 try {const prep=network.find(n=>n.url.endsWith('/prepare')&&n.status===200);if(prep){const run=prep.url.match(/algorithm-runs\/(\d+)/)[1];const cleanup=await page.evaluate(async run=>{const c=await(await fetch('/api/auth/csrf')).json();const r=await fetch('/api/algorithm-runs/'+run+'/stop',{method:'POST',headers:{'Content-Type':'application/json',[c.data.headerName]:c.data.token},body:'{}'});return {status:r.status,body:await r.json()}},run);checks.push({cleanup});}}catch(e){checks.push({cleanupError:String(e)})}
 await fs.writeFile(output+'/browser-disconnect.json',JSON.stringify({checks,failure,network},null,2));await browser.close();
}
console.log(JSON.stringify({failure,checks:checks.map(c=>({caseId:c.caseId,result:c.result,kind:c.kind}))}));
