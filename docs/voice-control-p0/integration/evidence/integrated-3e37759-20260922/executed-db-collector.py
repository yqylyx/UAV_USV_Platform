import os,json,pathlib,re,subprocess,datetime,sys
base=pathlib.Path('C:/Users/hp-pc/Desktop/Project4/Project/UAV_USV_Platform/.local-tools')
d=pathlib.Path(os.environ['P0_EVIDENCE_DIR']);stage=sys.argv[1]
assert re.fullmatch('[a-z0-9-]+',stage)
s=json.loads((base/'p0-integration/credentials.json').read_text(encoding='utf-8-sig'))
e=json.loads((d/'network.json').read_text(encoding='utf8'))
runs=sorted(set(re.search(r'/algorithm-runs/(\d+)/prepare',n['url']).group(1) for n in e if re.search(r'/algorithm-runs/(\d+)/prepare',n['url']) and n['method']=='POST'))
if not runs:raise SystemExit('No prepared runtime to export')
runlist=','.join("'"+r+"'" for r in runs); refs=f'SELECT id FROM voice_runtime_context WHERE algorithm_run_id IN ({runlist})';exs=f'SELECT id FROM voice_execution WHERE runtime_ref IN ({refs})'
queries=[f"SELECT JSON_OBJECT('table','context','data',CAST(data_json AS JSON)) FROM voice_runtime_context WHERE algorithm_run_id IN ({runlist})",f"SELECT JSON_OBJECT('table','proposal','data',CAST(data_json AS JSON)) FROM voice_proposal WHERE runtime_ref IN ({refs})",f"SELECT JSON_OBJECT('table','execution','data',CAST(data_json AS JSON)) FROM voice_execution WHERE runtime_ref IN ({refs})",f"SELECT JSON_OBJECT('table','event','receivedAt',received_at,'data',CAST(data_json AS JSON)) FROM voice_command_event WHERE execution_id IN ({exs}) ORDER BY received_at",f"SELECT JSON_OBJECT('table','audit','kind',kind,'detail',detail,'createdAt',created_at,'runtimeRef',runtime_ref) FROM voice_audit WHERE runtime_ref IN ({refs})",f"SELECT JSON_OBJECT('table','outbox','executionId',execution_id,'status',status,'claimedAt',claimed_at) FROM voice_outbox WHERE execution_id IN ({exs})",f"SELECT JSON_OBJECT('table','idempotency','userId',user_id,'operationKey',operation_key,'idempotencyKey',idempotency_key,'resourceId',resource_id,'bodyHash',body_hash) FROM voice_idempotency WHERE resource_id IN ({exs}) OR resource_id IN (SELECT id FROM voice_proposal WHERE runtime_ref IN ({refs}))"]
q='START TRANSACTION READ ONLY;\n'+';\n'.join(queries)+';\nCOMMIT;';env=os.environ.copy();env['MYSQL_PWD']=s['dbPassword']
r=subprocess.run(['D:/soteware/mysql-8.0.31-winx64/bin/mysql.exe','-h127.0.0.1','-up0_integration','-Duav_usv_p0_integration','--batch','--raw','--skip-column-names','--default-character-set=utf8mb4'],input=q,env=env,capture_output=True,encoding='utf8',check=True)
result={'capturedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'stage':stage,'runs':runs,'records':[json.loads(x) for x in r.stdout.splitlines() if x.strip()]}
(d/f'db-{stage}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');(d/'readonly-export.sql').write_text(q,encoding='utf8')
print('snapshot '+stage+' records='+str(len(result['records'])))
