"""Test-only real adapter entrypoint block; no fake heartbeats or results."""
import os,runpy,sys,threading
from pathlib import Path
path=Path(os.environ['P0_REAL_RUNNER']);sys.path.insert(0,str(path.parent))
namespace=runpy.run_path(str(path))
adapter=namespace['CaptureAdapter'];original=adapter.set_mission_active
def blocked(self,active):
    if active:threading.Event().wait()
    return original(self,active)
adapter.set_mission_active=blocked
raise SystemExit(namespace['main']())
