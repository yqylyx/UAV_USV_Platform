"""P17: exercise the real v1 loop at its production 10,000-command limit.

Only the adapter, input thread and clock sleep are replaced for a fast,
deterministic test; this is not the external evidence-pack subprocess test.
"""
import argparse
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import runner


class RunnerCapacityTest(unittest.TestCase):
    def test_capacity_preserves_replay_queries_order_and_state(self):
        ref = "00000000-0000-0000-0000-000000000001"
        generation = "00000000-0000-0000-0000-000000000002"

        def command(number, sequence, action="PAUSE", **overrides):
            return dict(protocolVersion=runner.PROTOCOL_VERSION, runtimeRef=ref,
                        runtimeGeneration=generation, kind="COMMAND",
                        commandId=f"10000000-0000-0000-0000-{number:012d}",
                        commandSequence=sequence, expectedStateVersion=0,
                        action=action, parameters={}, **overrides)

        # PAUSE in PREPARED is a cached business rejection, not a protocol error.
        inputs = [command(i, i) for i in range(1, 10001)]
        first = inputs[0].copy()
        overflow = command(10001, 10001, "START")
        inputs += [overflow, overflow.copy(), first,
                   {**first, "action": "STOP"},
                   command(10002, 10002, "START"),
                   {**overflow, "runtimeGeneration": ref},
                   {**overflow, "parameters": {"invalid": True}}]
        for item in (first, command(10000, 10000), overflow):
            inputs.append(dict(protocolVersion=runner.PROTOCOL_VERSION,
                               runtimeRef=ref, runtimeGeneration=generation,
                               kind="STATUS_QUERY", queryId=ref,
                               commandId=item["commandId"]))

        def feed(commands, closed):
            for item in inputs:
                commands.put(item)
            closed.set()

        def thread_factory(*, target, args, **kwargs):
            return Mock(start=lambda: feed(*args))

        adapter = Mock(code="test-adapter")
        adapter.step.return_value.to_dict.return_value = {"sequence": 0, "agents": []}
        events = []
        args = argparse.Namespace(runtime_ref=ref, runtime_generation=generation, fps=20)
        with patch.object(runner.threading, "Thread", side_effect=thread_factory), \
                patch.object(runner.time, "sleep"), \
                patch.object(runner, "emit", side_effect=events.append):
            self.assertEqual(0, runner.v1_main(args, adapter, {}))

        self.assertEqual(10000, runner.COMMAND_CACHE_LIMIT)
        results = [e for e in events if e.get("kind") == "COMMAND_RESULT"]
        self.assertEqual(10001, len(results))  # 10,000 originals + one replay
        self.assertEqual(results[0], results[-1])
        self.assertTrue(all(e["status"] == "REJECTED" and
                            e["errorCode"] == "INVALID_STATE" and
                            e["stateVersion"] == 0 and
                            e["runtimeState"] == "PREPARED" for e in results))
        errors = [e["errorCode"] for e in events if e.get("kind") == "PROTOCOL_ERROR"]
        self.assertEqual(["CAPACITY_EXCEEDED", "CAPACITY_EXCEEDED",
                          "COMMAND_ID_CONFLICT", "SEQUENCE_MISMATCH",
                          "IDENTITY_MISMATCH", "MALFORMED_MESSAGE"], errors)
        replies = [e for e in events if e.get("kind") == "STATUS_REPLY"]
        self.assertEqual([True, True, False], [e["known"] for e in replies])
        self.assertEqual(results[0], replies[0]["result"])
        self.assertEqual(results[9999], replies[1]["result"])
        self.assertIsNone(replies[2]["result"])
        adapter.set_mission_active.assert_called_once_with(False)
        adapter.step.assert_called_once()


if __name__ == "__main__":
    unittest.main()
