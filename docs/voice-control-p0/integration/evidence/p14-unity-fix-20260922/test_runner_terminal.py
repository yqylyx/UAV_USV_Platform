"""P14 deterministic adapter terminal injection into production v1 loop."""
import argparse
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import runner

class RunnerTerminalTest(unittest.TestCase):
    def test_terminal_frame_updates_state_and_resume_never_reactivates(self):
        for terminal in ("COMPLETED", "FAILED"):
            with self.subTest(terminal=terminal):
                ref="00000000-0000-0000-0000-000000000001"
                gen="00000000-0000-0000-0000-000000000002"
                def command(n, action, version):
                    return dict(protocolVersion=runner.PROTOCOL_VERSION,runtimeRef=ref,runtimeGeneration=gen,kind="COMMAND",commandId=f"10000000-0000-0000-0000-{n:012d}",commandSequence=n,expectedStateVersion=version,action=action,parameters={})
                def thread_factory(*, target, args, **kwargs):
                    def feed():
                        for item in (command(1,"START",0),command(2,"RESUME",2)):
                            args[0].put(item)
                        args[1].set()
                    return Mock(start=feed)
                adapter=Mock(code="terminal-fixture")
                initial=Mock(); initial.to_dict.return_value={"sequence":1,"agents":[]}
                final=Mock(); final.to_dict.return_value={"sequence":2,"agents":[],"terminalStatus":terminal}
                adapter.step.side_effect=[initial,final]
                events=[]
                with patch.object(runner.threading,"Thread",side_effect=thread_factory),patch.object(runner.time,"sleep"),patch.object(runner,"emit",side_effect=events.append):
                    runner.v1_main(argparse.Namespace(runtime_ref=ref,runtime_generation=gen,fps=20),adapter,{})
                rejected=[e for e in events if e.get("kind")=="COMMAND_RESULT" and e.get("status")=="REJECTED"]
                self.assertEqual(1,len(rejected))
                self.assertEqual("INVALID_STATE",rejected[0]["errorCode"])
                self.assertEqual(terminal,rejected[0]["runtimeState"])
                self.assertEqual(2,rejected[0]["stateVersion"])
                heartbeats=[e for e in events if e.get("kind")=="HEARTBEAT"]
                self.assertTrue(any(e["runtimeState"]==terminal and e["stateVersion"]==2 for e in heartbeats))
                self.assertEqual(2,adapter.step.call_count)
                started=[e for e in events if e.get("status")=="SUCCEEDED"]
                self.assertEqual(1,len(started))
                self.assertEqual("RUNNING",started[0]["runtimeState"])
                self.assertEqual(1,started[0]["stateVersion"])
                self.assertEqual([((False,),{}),((True,),{})],[(c.args,c.kwargs) for c in adapter.set_mission_active.call_args_list])
