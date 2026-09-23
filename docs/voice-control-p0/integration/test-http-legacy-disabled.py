"""Local isolated HTTP legacy compatibility; feature must already be disabled."""
import argparse,json,pathlib,time,uuid,requests,subprocess,os
p=argparse.ArgumentParser();p.add_argument('--credentials',required=True);p.add_argument('--output',required=True);p.add_argument('--mysql',required=True);a=p.parse_args()
secret=json.loads(pathlib.Path(a.credentials).read_text(encoding='utf-8-sig'));session=requests.Session();base='http://127.0.0.1:15174';headers={};run=int(time.time()*1000);report={'runId':run,'checks':[]};prepared=False

def call(path,body=None):
 r=session.request('GET' if body is None else 'POST',base+path,json=body,headers=headers,timeout=130);return r.status_code,r.json()
def ok(path,body=None):
 status,data=call(path,body);assert status==200,(path,status,data);return data['data']
def csrf():
 c=ok('/api/auth/csrf');headers[c['headerName']]=c['token']
def wait_state(expected):
 end=time.monotonic()+15
 while time.monotonic()<end:
  data=ok('/api/algorithm-runs/'+str(run)+'/status')
  if data['state']==expected:return data
  time.sleep(.2)
 raise AssertionError('Legacy state did not reach '+expected)
try:
 csrf();ok('/api/auth/login',{'username':'p0_admin','password':secret['adminPassword']});csrf();headers['Idempotency-Key']=str(uuid.uuid4())
 status,data=call('/api/voice/commands/proposals',{'runtimeRef':str(uuid.uuid4()),'runtimeGeneration':str(uuid.uuid4()),'expectedContextVersion':1,'intent':'MISSION_START'})
 assert status==503 and data['code']=='VOICE_CONTROL_DISABLED';report['disabledVoice']={'status':status,'body':data}
 result=ok('/api/algorithm-runs/'+str(run)+'/prepare',{'algorithmCode':'GB_SFLA_CS','config':{'standaloneVirtualSimulation':True,'seed':42}});prepared=True
 assert result['runtimeRef'] is None and result['runtimeGeneration'] is None and result['protocolVersion'] is None and result['capabilities']==[];report['prepare']=result
 for action,target in [('START','RUNNING'),('PAUSE','PAUSED'),('RESUME','RUNNING'),('STOP','STOPPED')]:
  response=ok('/api/algorithm-runs/'+str(run)+'/'+action.lower(),{});state=wait_state(target)
  if action=='START':time.sleep(.4)
  report['checks'].append({'action':action,'result':'PASS','responseState':response['state'],'observedState':state['state'],'latestSequence':state['latestSequence']})
 sql="SELECT COUNT(*) FROM voice_execution WHERE runtime_ref IN (SELECT id FROM voice_runtime_context WHERE algorithm_run_id='"+str(run)+"')"
 q=subprocess.run([a.mysql,'--host=127.0.0.1','--user=p0_integration','--database=uav_usv_p0_integration','--batch','--skip-column-names','--execute',sql],env={**os.environ,'MYSQL_PWD':secret['dbPassword']},capture_output=True,text=True,timeout=15);assert q.returncode==0;assert int(q.stdout.strip())==0
 report['voiceExecutionCount']=0;report['result']='PASS';print('legacy disabled HTTP four actions PASS')
except Exception as e:report['result']='FAIL';report['error']=str(e);raise
finally:
 if prepared:
  try:call('/api/algorithm-runs/'+str(run)+'/stop',{})
  except Exception:pass
 pathlib.Path(a.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
