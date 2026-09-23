import {spawnSync} from 'node:child_process';
import {chromium} from 'playwright';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const output=process.env.P0_GAP_OUTPUT;await fs.mkdir(output,{recursive:true});
const secret=JSON.parse((await fs.readFile(new URL('../p0-integration/credentials.json',import.meta.url),'utf8')).replace(/^\uFEFF/,''));
const peer=JSON.parse((await fs.readFile(new URL('./peer-account.json',import.meta.url),'utf8')).replace(/^\uFEFF/,''));assert(/^p0_peer_[a-zA-Z0-9_]+$/.test(peer.username));
const sql=statement=>{const r=spawnSync('D:/soteware/mysql-8.0.31-winx64/bin/mysql.exe',['--host=127.0.0.1','--user=p0_integration','--database=uav_usv_p0_integration','--batch','--raw','--skip-column-names'],{input:statement,encoding:'utf8',env:{...process.env,MYSQL_PWD:secret.dbPassword},timeout:20000});if(r.status!==0)throw Error('Isolated SQL failed');return r.stdout.trim()};
const originalAccount=JSON.parse(sql("SELECT JSON_OBJECT('role',role,'enabled',enabled) FROM app_user WHERE username='"+peer.username+"'"));
const role=(r,e)=>sql("UPDATE app_user SET role='"+r+"',enabled="+(e?'true':'false')+" WHERE username='"+peer.username+"'");role('ADMIN',true);
const browser=await chromium.launch({channel:'msedge',headless:true,args:['--enable-unsafe-swiftshader','--use-angle=swiftshader']});
const page=await browser.newPage({viewport:{width:1600,height:1000}});const network=[],checks=[];let disconnected=false,failure=null;
page.on('response',async r=>{if(/\/api\/(voice|algorithm-runs)/.test(r.url()))try{network.push({at:new Date().toISOString(),url:r.url(),status:r.status(),method:r.request().method(),request:r.request().postDataJSON(),body:await r.json()});}catch{}});
const diagnostics=[];
page.on('console',m=>{if(diagnostics.length<150)diagnostics.push({type:m.type(),text:m.text().slice(0,500)})});
page.on('pageerror',e=>diagnostics.push({error:String(e)}));
await page.addInitScript(()=>{window.__p0Messages=[];window.addEventListener('message',e=>{try{let d=typeof e.data==='string'?JSON.parse(e.data):e.data;let m=d?.message??d;if(m?.type&&window.__p0Messages.length<300)window.__p0Messages.push(m)}catch{}})});
const click=async name=>page.getByRole('button',{name,exact:true}).click({timeout:25000});
try {
 await page.goto('http://127.0.0.1:15174/?workspace=simulation');await page.getByPlaceholder('请输入用户名').fill(peer.username);await page.getByPlaceholder('请输入密码').fill(peer.password);await click('进入控制台');await click('语音控制');
 await page.waitForResponse(r=>r.url().endsWith('/presentation/reports')&&r.status()===200&&r.request().postDataJSON()?.kind==='SCENE_READY',{timeout:90000});
 await click('开始任务 创建并核对指令提案');await click('确认执行');await page.waitForFunction(()=>document.body.innerText.includes('Unity 已应用'),null,{timeout:45000});
 await click('暂停任务 创建并核对指令提案');
 const proposal=network.filter(n=>n.url.endsWith('/commands/proposals')&&n.status===201).at(-1).body.data;
 const ref=proposal.plan.runtimeRef;assert(/^[a-f0-9-]{36}$/.test(ref));
 const before=Number(sql("SELECT COUNT(*) FROM voice_execution WHERE runtime_ref='"+ref+"'"));
 role('VIEWER',true);await page.reload();await page.waitForTimeout(3000);
 const response=await page.evaluate(async p=>{const c=(await(await fetch('/api/auth/csrf')).json()).data;const r=await fetch('/api/voice/commands/'+p.proposalId+'/confirm',{method:'POST',headers:{'Content-Type':'application/json',[c.headerName]:c.token,'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify({expectedPlanVersion:p.planVersion,expectedPlanHash:p.planHash})});return {status:r.status,body:await r.json()}},proposal);
 assert.equal(response.status,403);assert.equal(response.body.code,'FORBIDDEN');
 const after=Number(sql("SELECT COUNT(*) FROM voice_execution WHERE runtime_ref='"+ref+"'"));assert.equal(before,after);
 checks.push({caseId:'X17',result:'PASS',roleAfterReload:'VIEWER',before,after,response,proposalId:proposal.proposalId});
 await page.screenshot({path:output+'/role-revoked-refresh.png',timeout:20000});
} catch(e){failure=String(e);process.exitCode=1;console.error(e);await page.screenshot({path:output+'/failure.png',timeout:15000}).catch(()=>{});}
finally {
 role('ADMIN',true);
 try {const prep=network.find(n=>n.url.endsWith('/prepare')&&n.status===200);if(prep){const run=prep.url.match(/algorithm-runs\/(\d+)/)[1];const cleanup=await page.evaluate(async run=>{const c=await(await fetch('/api/auth/csrf')).json();const r=await fetch('/api/algorithm-runs/'+run+'/stop',{method:'POST',headers:{'Content-Type':'application/json',[c.data.headerName]:c.data.token},body:'{}'});return {status:r.status,body:await r.json()}},run);checks.push({cleanup});}}catch(e){checks.push({cleanupError:String(e)})}
 try{await fs.writeFile(output+'/diagnostics.json',JSON.stringify({diagnostics,text:await page.locator('body').innerText(),messages:await page.evaluate(()=>window.__p0Messages),frames:page.frames().map(f=>f.url())},null,2))}catch{}
 await fs.writeFile(output+'/browser-role-revoked.json',JSON.stringify({checks,failure,network},null,2));await browser.close();role(originalAccount.role,Boolean(originalAccount.enabled));
}
console.log(JSON.stringify({failure,checks:checks.map(c=>({caseId:c.caseId,result:c.result,kind:c.kind}))}));
