import json
import subprocess
import sys
import unittest
import uuid
from pathlib import Path


class RunnerProtocolTest(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        runtime_ref = str(uuid.uuid4())
        generation = str(uuid.uuid4())
        config = json.dumps({"uavCount": 1, "usvCount": 1, "targetCount": 1, "seed": 42})
        self.process = subprocess.Popen(
            [
                sys.executable,
                str(root / "runner.py"),
                "--algorithm", "GB_SFLA_CS",
                "--run-id", "990026",
                "--config", config,
                "--fps", "20",
                "--command-protocol", "v1",
                "--runtime-ref", runtime_ref,
                "--runtime-generation", generation,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self.runtime_ref = runtime_ref
        self.generation = generation

    def tearDown(self):
        if self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=5)
        self.process.stdin.close()
        self.process.stdout.close()

    def read_event(self, predicate):
        while True:
            line = self.process.stdout.readline()
            if not line:
                self.fail("Runner exited before emitting the expected event")
            event = json.loads(line)
            if predicate(event):
                return event

    def send(self, command):
        self.process.stdin.write(json.dumps(command) + "\n")
        self.process.stdin.flush()

    def test_known_status_reply_embeds_protocol_version(self):
        self.read_event(lambda event: event.get("kind") == "RUNTIME_READY")
        frame = self.read_event(lambda event: event.get("event") == "frame")
        self.assertTrue(frame["payload"]["agents"])

        command_id = str(uuid.uuid4())
        self.send({
            "protocolVersion": "algorithm.command.v1",
            "runtimeRef": self.runtime_ref,
            "runtimeGeneration": self.generation,
            "kind": "COMMAND",
            "commandId": command_id,
            "commandSequence": 1,
            "expectedStateVersion": 0,
            "action": "START",
        })
        self.read_event(
            lambda event: event.get("kind") == "COMMAND_RESULT"
            and event.get("commandId") == command_id
            and event.get("status") == "SUCCEEDED"
        )

        query_id = str(uuid.uuid4())
        self.send({
            "protocolVersion": "algorithm.command.v1",
            "runtimeRef": self.runtime_ref,
            "runtimeGeneration": self.generation,
            "kind": "STATUS_QUERY",
            "queryId": query_id,
            "commandId": command_id,
        })
        reply = self.read_event(
            lambda event: event.get("kind") == "STATUS_REPLY"
            and event.get("queryId") == query_id
        )
        self.assertTrue(reply["known"])
        self.assertEqual("algorithm.command.v1", reply["protocolVersion"])
        self.assertIsNotNone(reply["result"])
        self.assertEqual("algorithm.command.v1", reply["result"]["protocolVersion"])


if __name__ == "__main__":
    unittest.main()
