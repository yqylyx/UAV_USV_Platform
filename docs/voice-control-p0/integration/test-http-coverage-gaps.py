"""Negative HTTP acceptance on a dedicated local MySQL service. Never fabricates positive Unity reports.
Requires a dedicated disposable ADMIN test account; its role/enabled flags are restored in finally.
The supplied restart script must restart only this isolated backend and preserve its stdout/stderr.
"""
import argparse, datetime, json, os, pathlib, subprocess, time, uuid
import requests
p=argparse.ArgumentParser()
p.add_argument('--credentials',required=True);p.add_argument('--peer',required=True)
p.add_argument('--mysql',required=True);p.add_argument('--output',required=True)
p.add_argument('--restart-script',required=True);p.add_argument('--powershell',default='pwsh')
a=p.parse_args()
out=pathlib.Path(a.output);out.mkdir(parents=True,exist_ok=True)
secret=json.loads(pathlib.Path(a.credentials).read_text(encoding='utf-8-sig'))
peer=json.loads(pathlib.Path(a.peer).read_text(encoding='utf-8-sig'))
assert peer['username'].startswith('p0_peer_'), 'Only dedicated test account is permitted'
assert all(c.isalnum() or c=='_' for c in peer['username'])
base='http://127.0.0.1:18081';s=requests.Session();headers={};ref=None;run=None
report={'scope':'real HTTP + local MySQL + real backend process restart; negative presentation inputs only','checks':[],'requests':[]}
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sql(statement,jsonlines=True):
 r=subprocess.run([a.mysql,'--host=127.0.0.1','--user=p0_integration','--database=uav_usv_p0_integration','--batch','--raw','--skip-column-names','--default-character-set=utf8mb4'],input=statement,env={**os.environ,'MYSQL_PWD':secret['dbPassword']},capture_output=True,text=True,encoding='utf-8',timeout=20)
 if r.returncode:raise RuntimeError('Local SQL failed')
 return [json.loads(x) for x in r.stdout.splitlines() if x.strip()] if jsonlines else r.stdout
where="username='"+peer['username']+"'"
original=sql("SELECT JSON_OBJECT('role',role,'enabled',enabled) FROM app_user WHERE "+where)[0]
def call(path,body=None,expected=200,key=None,record=True):
 h={**headers}
 if body is not None:h['Idempotency-Key']=key or str(uuid.uuid4())
 response=s.request('GET' if body is None else 'POST',base+path,json=body,headers=h,timeout=90)
 value=response.json()
 if record:report['requests'].append({'at':stamp(),'path':path,'method':'GET' if body is None else 'POST','request':body,'key':h.get('Idempotency-Key'),'status':response.status_code,'response':value})
 assert response.status_code==expected,(path,response.status_code,value)
 return value.get('data') if expected<300 else value

def login():
 s.cookies.clear();headers.clear()
 c=call('/api/auth/csrf',record=False);headers[c['headerName']]=c['token']
 call('/api/auth/login',peer,record=False)
 c=call('/api/auth/csrf',record=False);headers[c['headerName']]=c['token']
def wait(fn,seconds=30):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  v=fn()
  if v:return v
  time.sleep(.3)
 raise AssertionError('Acceptance wait timed out')
def ctx():return call('/api/voice/contexts/'+ref)
def executions():return sql("SELECT data_json FROM voice_execution WHERE runtime_ref='"+ref+"'")
def check(name,**details):report['checks'].append({'name':name,'result':'PASS','at':stamp(),**details});print(name,'PASS',flush=True)
def snapshot(name):
 data={}
 for table in ['voice_runtime_context','voice_proposal','voice_execution']:
  data[table]=sql("SELECT data_json FROM "+table+" WHERE "+("id" if table=="voice_runtime_context" else "runtime_ref")+"='"+ref+"'")
 ids=[x['executionId'] for x in data['voice_execution']]
 if ids:
  clause=','.join("'"+x+"'" for x in ids)
  data['voice_command_event']=sql('SELECT data_json FROM voice_command_event WHERE execution_id IN ('+clause+') ORDER BY event_sequence')
 (out/(name+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
 return data
try:
 sql("UPDATE app_user SET role='ADMIN',enabled=true WHERE "+where,False)
 login();run=int(time.time()*1000)
 prep=call('/api/algorithm-runs/'+str(run)+'/prepare',{'algorithmCode':'GB_SFLA_CS','config':{'standaloneVirtualSimulation':True,'seed':42}})
 ref=prep['runtimeRef'];gen=prep['runtimeGeneration'];report.update(runtimeRef=ref,runtimeGeneration=gen,runId=run)
 call('/api/algorithm-runs/'+str(run)+'/start',{})
 execution=wait(lambda:next((e for e in executions() if e['action']=='START' and e['state']=='SUCCEEDED'),None))
 assert ctx()['state']=='RUNNING'
 check('real_runner_running',executionId=execution['executionId'],commandId=execution['commandId'])
 proposalBody={'runtimeRef':ref,'runtimeGeneration':gen,'expectedContextVersion':ctx()['contextVersion'],'intent':'MISSION_PAUSE'}
 key=str(uuid.uuid4());proposal=call('/api/voice/commands/proposals',proposalBody,201,key)
 confirmBody={'expectedPlanVersion':proposal['planVersion'],'expectedPlanHash':proposal['planHash']}
 for role in ['VIEWER','OPERATOR']:
  sql("UPDATE app_user SET role='"+role+"' WHERE "+where,False)
  for path,body,replay in [('/api/voice/commands/proposals',proposalBody,key),('/api/voice/commands/'+proposal['proposalId']+'/confirm',confirmBody,None),('/api/voice/commands/'+proposal['proposalId']+'/cancel',confirmBody,None)]:
   assert call(path,body,403,replay)['code']=='FORBIDDEN'
  assert len(executions())==1 and ctx()['state']=='RUNNING'
  check('running_role_revoked_'+role,executionCount=1,sessionReused=True)
 sql("UPDATE app_user SET enabled=false WHERE "+where,False)
 assert call('/api/voice/contexts/'+ref,expected=403)['code']=='FORBIDDEN'
 assert call('/api/voice/commands/proposals',proposalBody,403,key)['code']=='FORBIDDEN'
 check('running_account_disabled_same_session')
 sql("UPDATE app_user SET role='ADMIN',enabled=true WHERE "+where,False)
 # Create a real server challenge but do not send a positive scene report.
 prefix='/api/voice/contexts/'+ref+'/presentation/'
 old=call(prefix+'bindings',{'runtimeGeneration':gen,'expectedBindingId':None})
 challengeBody={'runtimeGeneration':gen,'bindingId':old['bindingId'],'kind':'SCENE_READY','executionId':None}
 challenge=call(prefix+'challenges',challengeBody)
 newer=call(prefix+'bindings',{'runtimeGeneration':gen,'expectedBindingId':old['bindingId']})
 invalid={**challengeBody,'requestId':challenge['requestId'],'sequence':challenge['sequence'],'frameSequence':1,'applied':True}
 assert call(prefix+'reports',invalid,409)['code']=='CONTEXT_CHANGED'
 check('old_binding_report_rejected',oldBindingId=old['bindingId'],newBindingId=newer['bindingId'])
 invalid.update(bindingId=newer['bindingId'],runtimeGeneration=str(uuid.uuid4()))
 assert call(prefix+'reports',invalid,409)['code']=='GENERATION_MISMATCH'
 assert not ctx()['sceneReady'] and len(executions())==1
 check('foreign_generation_report_rejected_without_scene_or_algorithm_change')
 # Fresh unconfirmed proposal remains available when the process is stopped.
 pending=call('/api/voice/commands/proposals',{**proposalBody,'expectedContextVersion':ctx()['contextVersion']},201)
 before=snapshot('db-before-restart');deadline=before['voice_execution'][0]['_presentationDeadlineAt']
 subprocess.run([a.powershell,'-NoProfile','-ExecutionPolicy','Bypass','-File',a.restart_script],check=True,timeout=60,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 def available():
  try:return requests.get(base+'/api/auth/csrf',timeout=2).status_code==200
  except requests.RequestException:return False
 wait(available,60);login()
 assert ctx()['state']=='LOST'
 assert call('/api/voice/commands/'+pending['proposalId'])['status']=='INVALIDATED'
 after=snapshot('db-after-restart')
 assert len(after['voice_execution'])==1
 assert after['voice_execution'][0]['state']=='SUCCEEDED'
 assert after['voice_execution'][0]['commandId']==execution['commandId']
 assert after['voice_execution'][0]['_presentationDeadlineAt']==deadline
 check('real_backend_restart_invalidates_pending_preserves_success_and_deadline',proposalId=pending['proposalId'],deadline=deadline)
 wait(lambda:call('/api/voice/executions/'+execution['executionId'])['presentationStatus']=='STALE',40)
 final=snapshot('db-final')
 assert len(final['voice_execution'])==1
 assert len(final['voice_command_event'])==len(before['voice_command_event'])
 check('restart_does_not_replay_and_presentation_deadline_expires',executionCount=1)
 report['result']='PASS'
except Exception as e:
 report['result']='FAIL';report['error']=str(e);raise
finally:
 if ref:
  try:
   sql("UPDATE app_user SET role='ADMIN',enabled=true WHERE "+where,False)
   login()
   if ctx()['state'] in ['PREPARED','PREVIEW','RUNNING','PAUSED']:call('/api/algorithm-runs/'+str(run)+'/stop',{})
  except Exception as e:report['cleanupNote']=type(e).__name__
 sql("UPDATE app_user SET role='"+original['role']+"',enabled="+('true' if original['enabled'] else 'false')+' WHERE '+where,False)
 report['accountRestored']=True
 (out/'http-gaps.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')


