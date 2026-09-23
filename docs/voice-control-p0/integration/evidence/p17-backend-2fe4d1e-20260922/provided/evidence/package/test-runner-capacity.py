"""P17 acceptance probe against the unmodified real Runner; exits nonzero on contract failure."""
import argparse, hashlib, json, pathlib, queue, subprocess, sys, threading, time, uuid
p=argparse.ArgumentParser();p.add_argument('--runner',required=True);p.add_argument('--output',required=True);a=p.parse_args()
ref=str(uuid.uuid4());gen=str(uuid.uuid4());events=queue.Queue();report={'caseId':'P17','runtimeRef':ref,'runtimeGeneration':gen,'runnerSha256':hashlib.sha256(pathlib.Path(a.runner).read_bytes()).hexdigest()}
child=subprocess.Popen([sys.executable,a.runner,'--algorithm','GB_SFLA_CS','--run-id',str(int(time.time()*1000)),'--config',json.dumps({'uavCount':1,'usvCount':1,'targetCount':1,'seed':42}),'--fps','200','--command-protocol','v1','--runtime-ref',ref,'--runtime-generation',gen],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8')
def reader():
 for line in child.stdout:
  try:events.put(json.loads(line))
  except ValueError:pass
threading.Thread(target=reader,daemon=True).start()
def receive(predicate):
 deadline=time.monotonic()+20
 while time.monotonic()<deadline:
  e=events.get(timeout=max(.01,deadline-time.monotonic()))
  if predicate(e):return e
 raise AssertionError('Runner response timeout')
def send(body):child.stdin.write(json.dumps(body)+'\n');child.stdin.flush()
def command(n):return {'protocolVersion':'algorithm.command.v1','runtimeRef':ref,'runtimeGeneration':gen,'kind':'COMMAND','commandId':str(uuid.uuid4()),'commandSequence':n,'expectedStateVersion':0,'action':'PAUSE','parameters':{}}
try:
 receive(lambda e:e.get('kind')=='RUNTIME_READY')
 digest=hashlib.sha256();first=None;first_result=None
 for n in range(1,10001):
  c=command(n);send(c);e=receive(lambda e:e.get('commandId')==c['commandId'])
  assert e['status']=='REJECTED' and e['errorCode']=='INVALID_STATE' and e['stateVersion']==0
  digest.update((json.dumps(c,sort_keys=True)+json.dumps(e,sort_keys=True)).encode())
  if n==1:first=c;first_result=e
  if n%2000==0:print('Cached rejected commands',n,flush=True)
 report.update(cachedCommands=10000,commandsAndResponsesSha256=digest.hexdigest(),firstCommand=first,firstResult=first_result)
 extra=command(10001);send(extra)
 overflow=receive(lambda e:e.get('commandId')==extra['commandId'] or e.get('relatedCommandId')==extra['commandId'])
 report['overflow']=overflow
 send(first);replayed=receive(lambda e:e.get('commandId')==first['commandId']);report['oldReplayStable']=replayed==first_result
 report['result']='PASS' if overflow.get('errorCode')=='CAPACITY_EXCEEDED' and report['oldReplayStable'] else 'FAIL'
 report['expected']='New command rejected with CAPACITY_EXCEEDED; old cached command remains replayable'
 print('P17',report['result'],overflow.get('errorCode'),flush=True)
finally:
 if child.poll() is None:child.terminate()
 child.wait(timeout=10)
 pathlib.Path(a.output).write_text(json.dumps(report,indent=2),encoding='utf-8')
sys.exit(0 if report.get('result')=='PASS' else 1)
