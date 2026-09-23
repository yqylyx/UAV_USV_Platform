"""Observe actual adapter calls; no mocked action, heartbeat or result."""
import os,runpy,sys,json
from pathlib import Path
path=Path(os.environ['P0_REAL_RUNNER']);sys.path.insert(0,str(path.parent))
config=json.loads(Path(sys.argv[sys.argv.index('--config-file')+1]).read_text(encoding='utf-8-sig'))
trace=Path(config['faultTrace']+'.apply.jsonl')
namespace=runpy.run_path(str(path));adapter=namespace['CaptureAdapter'];original=adapter.set_mission_active
def counted(self,active):
    with trace.open('a',encoding='utf-8') as f:f.write(json.dumps({'active':active})+'\n')
    return original(self,active)
adapter.set_mission_active=counted
raise SystemExit(namespace['main']())
