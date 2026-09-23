"""Test-only pipe fault proxy. Runs the unmodified real Runner; never fabricates success."""
import json,os,pathlib,subprocess,sys,threading
args=sys.argv[1:]
config=json.loads(pathlib.Path(args[args.index('--config-file')+1]).read_text(encoding='utf-8-sig'))
mode=config['faultMode']; trace=pathlib.Path(config['faultTrace']); lock=threading.Lock()
entrypoint=str(pathlib.Path(__file__).with_name('blocked_worker_runner.py')) if mode=='worker_deadlock' else os.environ['P0_REAL_RUNNER']
if mode=='apply_count':entrypoint=str(pathlib.Path(__file__).with_name('counting_worker_runner.py'))
child=subprocess.Popen([sys.executable,entrypoint,*args],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=sys.stderr,text=True,encoding='utf-8',bufsize=1)
def record(direction,event):
 with lock:
  with trace.open('a',encoding='utf-8') as f:f.write(json.dumps({'direction':direction,'event':event})+'\n')
def forward():
 try:
  for line in sys.stdin:
   event=json.loads(line);record('java_to_runner',event)
   if mode=='stop_eof_before_ack' and event.get('action')=='STOP':
    record('fault',{'kind':'STOP_EOF_BEFORE_ACK'});child.kill();return
   child.stdin.write(line);child.stdin.flush()
 finally:
  if child.poll() is None:child.terminate()
threading.Thread(target=forward,daemon=True).start()
held=[]; beats=0
try:
 for line in child.stdout:
  try:event=json.loads(line)
  except ValueError:continue
  record('runner_to_java',event)
  kind=event.get('kind')
  if kind=='HEARTBEAT':
   beats+=1
   if mode=='silence_heartbeat' and beats>1:continue
  if kind=='COMMAND_RESULT' and event.get('status')=='SUCCEEDED' and mode=='delay_success':
   held.append(line);continue
  if mode=='stop_eof_before_result' and kind=='COMMAND_RESULT' and event.get('runtimeState')=='STOPPED' and event.get('status')=='SUCCEEDED':
   record('fault',{'kind':'STOP_SUCCESS_DROPPED','commandId':event.get('commandId')});break
  print(line,end='',flush=True)
  if kind=='HEARTBEAT' and beats==2 and mode in ['oversized_lines','wrong_identity_lines','ordinary_logs']:
   for number in range(3):
    if mode=='oversized_lines': payload='x'*(256*1024+1)
    elif mode=='ordinary_logs': payload='ordinary algorithm diagnostic '+str(number)
    else:
     bad=dict(event);bad['runtimeRef']='00000000-0000-0000-0000-000000000000';payload=json.dumps(bad)
    print(payload,flush=True)
   record('fault',{'kind':mode,'injectedLines':3})
  if kind=='COMMAND_RESULT' and event.get('status')=='ACCEPTED' and mode=='crash_after_accept':
   child.kill();break
finally:
 if child.poll() is None:child.terminate()
 child.wait(timeout=10)
sys.exit(17 if mode in ['crash_after_accept','stop_eof_before_ack','stop_eof_before_result'] else child.returncode)

