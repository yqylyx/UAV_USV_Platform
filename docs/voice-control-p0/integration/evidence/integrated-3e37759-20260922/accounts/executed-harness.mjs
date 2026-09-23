import {chromium} from 'playwright';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const dir=new URL('./acceptance-accounts2-3e37759/',import.meta.url);await fs.mkdir(dir,{recursive:true});
const browser=await chromium.launch({channel:'msedge',headless:true,args:['--enable-unsafe-swiftshader','--use-angle=swiftshader']});
const context=await browser.newContext({viewport:{width:1600,height:1000}});const page=await context.newPage();
let events=[],errors=[],markers=[];let blockFrames=false,dropConfirm=false;
await page.route('**/api/voice/**',async route=>{
 const req=route.request();let body;try{body=req.postDataJSON()}catch{}
 if(blockFrames && req.url().endsWith('/presentation/reports') && body?.kind==='FRAME_APPLIED'){
   markers.push({at:new Date().toISOString(),type:'blocked-frame-report',url:req.url(),body});await route.abort('failed');return;
 }
 if(dropConfirm && req.url().endsWith('/confirm') && req.method()==='POST'){
   dropConfirm=false;const response=await route.fetch();markers.push({at:new Date().toISOString(),type:'dropped-confirm-response',request:body,idempotencyKey:req.headers()['idempotency-key']??null,response:await response.json()});await route.abort('failed');return;
 }
 await route.continue();
});
page.on('pageerror',e=>errors.push(String(e)));
page.on('response',async r=>{if(/\/api\/(voice|algorithm-runs)/.test(r.url()))try{events.push({at:new Date().toISOString(),url:r.url(),status:r.status(),method:r.request().method(),request:r.request().postDataJSON(),idempotencyKey:r.request().headers()['idempotency-key']??null,body:await r.json()});}catch{}});
async function save(){await fs.writeFile(new URL('markers.json',dir),JSON.stringify(markers,null,2));await fs.writeFile(new URL('network.json',dir),JSON.stringify(events,null,2));await fs.writeFile(new URL('errors.json',dir),JSON.stringify(errors,null,2));}
const steps=[];
async function record(name){steps.push({name,at:new Date().toISOString(),text:(await page.locator('body').innerText()).slice(-2500)});await fs.writeFile(new URL('steps.json',dir),JSON.stringify(steps,null,2));await save();const snap=spawnSync('D:/soteware/anaconda/python.exe',[process.env.TEMP+'/export-p0-dual.py',name],{env:{...process.env,P0_EVIDENCE_DIR:fileURLToPath(dir)},encoding:'utf8'});if(snap.status!==0)throw Error('DB snapshot failed: '+snap.stderr);console.log(name);}
async function click(name){await page.getByRole('button',{name,exact:true}).click({timeout:20000})}
async function panel(){await click('语音控制');await page.getByText('VOICE / LLM · P0',{exact:true}).waitFor();}
async function action(name){if(['开始任务','继续任务'].includes(name)){await page.waitForResponse(r=>r.url().endsWith('/presentation/reports')&&r.status()===200&&r.request().postDataJSON()?.kind==='SCENE_READY',{timeout:45000});}await click(name+' 创建并核对指令提案');await click('确认执行');}
async function textWait(text){await page.waitForFunction(s=>document.body.innerText.includes(s),text,{timeout:60000});}
try {
 const s=JSON.parse((await fs.readFile(new URL('../p0-integration/credentials.json',import.meta.url),'utf8')).replace(/^\uFEFF/,''));
 await page.goto('http://127.0.0.1:15174/?workspace=simulation');await page.getByPlaceholder('请输入用户名').fill('p0_admin');await page.getByPlaceholder('请输入密码').fill(s.adminPassword);await click('进入控制台');await panel();
 await page.getByRole('button',{name:'开始任务 创建并核对指令提案',exact:true}).waitFor({timeout:90000});await record('ready');
 await action('停止任务');await textWait('停止任务\n算法结果：SUCCESS');await record('owner-stopped');
 const aRecord=events.map(x=>x.body?.data).find(x=>x?.action==='STOP'&&x?.executionId);
 assert(aRecord,'A STOP identity missing');const aRef=aRecord.runtimeRef;const aExec=aRecord.executionId;const aProposal=aRecord.proposalId;
 const aContext=events.map(x=>x.body?.data).find(x=>x?.runtimeRef===aRef&&x?.algorithmRunId);const aRun=aContext.algorithmRunId;
 const isolation=[];
 async function saveIsolation(){await fs.writeFile(new URL('dual-account-checks.json',dir),JSON.stringify(isolation,null,2));}
 async function logoutCheck(user){
   await page.getByRole('button',{name:'退出登录',exact:true}).first().click();await page.getByPlaceholder('请输入用户名').waitFor();
   const remaining=await page.evaluate(u=>({local:Object.keys(localStorage).filter(k=>k.includes(u)&&k.startsWith('voice-p0')),session:Object.keys(sessionStorage).filter(k=>k.includes(u)&&k.startsWith('virtual-fleet'))}),user);
   assert.equal(remaining.local.length,0);assert.equal(remaining.session.length,0);isolation.push({check:'logout-clears-storage',user,...remaining,at:new Date().toISOString()});
 }
 async function signIn(user,password){await page.getByPlaceholder('请输入用户名').fill(user);await page.getByPlaceholder('请输入密码').fill(password);await click('进入控制台');await page.getByRole('link',{name:'算法仿真',exact:true}).click();await panel();await page.getByRole('button',{name:'停止任务 创建并核对指令提案',exact:true}).waitFor({timeout:90000});}
 async function getApi(path){return await page.evaluate(async p=>{const r=await fetch(p);return {path:p,status:r.status,body:await r.json()}},path);}
 async function rejectOther(owner,ref,exec,proposal){
   const list=await getApi('/api/voice/contexts');assert.equal(list.status,200);assert(!list.body.data.some(c=>c.runtimeRef===ref));isolation.push({check:'foreign-context-not-listed',owner,ref,status:list.status});
   for(const path of ['/api/voice/contexts/'+ref,'/api/voice/executions/'+exec,'/api/voice/commands/'+proposal]){const r=await getApi(path);assert.equal(r.status,404);assert.equal(r.body.code,'RESOURCE_NOT_FOUND');isolation.push({check:'foreign-resource-denied',owner,...r});}
 }
 await logoutCheck('p0_admin');
 const peer=JSON.parse(await fs.readFile(new URL('./peer-account.json',import.meta.url),'utf8'));
 await signIn(peer.username,peer.password);await page.waitForTimeout(3000);
 assert(!(await page.locator('body').innerText()).includes(aRun),'A runtime leaked into B UI');
 await rejectOther('p0_admin',aRef,aExec,aProposal);await saveIsolation();await record('peer-isolated');
 await action('停止任务');await textWait('停止任务\n算法结果：SUCCESS');await record('peer-stopped');
 const bRecord=events.map(x=>x.body?.data).filter(x=>x?.action==='STOP'&&x?.executionId&&x.runtimeRef!==aRef).at(-1);assert(bRecord);
 await logoutCheck(peer.username);await signIn('p0_admin',s.adminPassword);await page.waitForTimeout(3000);
 await rejectOther(peer.username,bRecord.runtimeRef,bRecord.executionId,bRecord.proposalId);
 const own=await getApi('/api/voice/executions/'+aExec);assert.equal(own.status,200);assert.equal(own.body.data.executionId,aExec);isolation.push({check:'owner-can-read-own-historical-execution',status:own.status,executionId:aExec});
 await saveIsolation();await record('owner-restored-without-peer-data');
 await action('停止任务');await textWait('停止任务\n算法结果：SUCCESS');await record('owner-new-scene-stopped');
 await logoutCheck('p0_admin');
 const anon=await getApi('/api/voice/contexts');assert.equal(anon.status,401);isolation.push({check:'anonymous-denied',...anon});
 await fs.writeFile(new URL('dual-account-checks.json',dir),JSON.stringify(isolation,null,2));await record('dual-account-complete');

} catch(e){await fs.writeFile(new URL('failure.txt',dir),String(e));console.error(e);await record('failed');process.exitCode=1;}
finally {await save();await browser.close();}



