"""Real runner with a controlled 0.5s process teardown window after main returns."""
import os,runpy,sys,time
from pathlib import Path
path=Path(os.environ['P0_REAL_RUNNER']);sys.path.insert(0,str(path.parent))
namespace=runpy.run_path(str(path));code=namespace['main']();time.sleep(.5);raise SystemExit(code)
