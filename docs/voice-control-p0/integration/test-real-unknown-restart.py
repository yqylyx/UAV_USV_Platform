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
 trace=str(out/'runner-trace.jsonl')
 prep=call('/api/algorithm-runs/'+str(run)+'/prepare',{'algorithmCode':'GB_SFLA_CS','config':{'standaloneVirtualSimulation':True,'seed':42,'faultMode':'delay_success','faultTrace':trace}})
 ref=prep['runtimeRef'];gen=prep['runtimeGeneration'];report.update(runtimeRef=ref,runtimeGeneration=gen,runId=run)
 call('/api/algorithm-runs/'+str(run)+'/start',{})
 pending=wait(lambda:next((e for e in executions() if e['state']=='ACCEPTED'),None),10)
 snapshot('before-restart')
 check('real_command_accepted_success_withheld',executionId=pending['executionId'],commandId=pending['commandId'])
 env={**os.environ,'P0_WORKSPACE':str(pathlib.Path.cwd()).replace('\\','/'),'P0_ISOLATED_LOCAL_DIR':str(pathlib.Path(a.credentials).parent).replace('\\','/'),'P0_GAP_EVIDENCE_DIR':str(out)}
 subprocess.run([a.powershell,'-NoProfile','-File',a.restart_script],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=60,check=True)
 def available():
  try:return requests.get(base+'/api/auth/csrf',timeout=2).status_code==200
  except requests.RequestException:return False
 wait(available,60);login()
 current=call('/api/voice/executions/'+pending['executionId'])
 assert current['state']=='TIMED_OUT' and current['outcome']=='UNKNOWN',current
 assert ctx()['state']=='LOST'
 time.sleep(3);snapshot('after-restart')
 events=[json.loads(line) for line in pathlib.Path(trace).read_text(encoding='utf-8').splitlines()]
 commands=[e for e in events if e['direction']=='java_to_runner' and e['event'].get('kind')=='COMMAND']
 assert len(commands)==1,commands
 check('real_backend_restart_unknown_no_replay',execution=current,commandCount=len(commands))
except Exception as exc:
 report['failure']=str(exc);raise
finally:
 sql("UPDATE app_user SET role='"+original['role']+"',enabled="+str(int(original['enabled']))+" WHERE "+where,False)
 (out/'http-restart.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
