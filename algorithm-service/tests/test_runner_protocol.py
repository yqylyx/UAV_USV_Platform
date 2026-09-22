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

    def send_raw(self, value):
        self.process.stdin.write(value + "\n")
        self.process.stdin.flush()

    def command(self, command_id, sequence, state_version, action, **overrides):
        value = {
            "protocolVersion": "algorithm.command.v1",
            "runtimeRef": self.runtime_ref,
            "runtimeGeneration": self.generation,
            "kind": "COMMAND",
            "commandId": command_id,
            "commandSequence": sequence,
            "expectedStateVersion": state_version,
            "action": action,
            "parameters": {},
        }
        value.update(overrides)
        return value

    def status_query(self, command_id, **overrides):
        value = {
            "protocolVersion": "algorithm.command.v1",
            "runtimeRef": self.runtime_ref,
            "runtimeGeneration": self.generation,
            "kind": "STATUS_QUERY",
            "queryId": str(uuid.uuid4()),
            "commandId": command_id,
        }
        value.update(overrides)
        return value

    def read_protocol_event(self, kind, **matches):
        return self.read_event(
            lambda event: event.get("kind") == kind
            and all(event.get(key) == value for key, value in matches.items())
        )

    def test_known_status_reply_embeds_protocol_version(self):
        self.read_event(lambda event: event.get("kind") == "RUNTIME_READY")
        frame = self.read_event(lambda event: event.get("event") == "frame")
        self.assertTrue(frame["payload"]["agents"])

        command_id = str(uuid.uuid4())
        self.send(self.command(command_id, 1, 0, "START"))
        self.read_protocol_event("COMMAND_RESULT", commandId=command_id, status="SUCCEEDED")

        query = self.status_query(command_id)
        self.send(query)
        reply = self.read_protocol_event("STATUS_REPLY", queryId=query["queryId"])
        self.assertTrue(reply["known"])
        self.assertEqual("algorithm.command.v1", reply["protocolVersion"])
        self.assertIsNotNone(reply["result"])
        self.assertEqual("algorithm.command.v1", reply["result"]["protocolVersion"])

    def test_malformed_json_returns_protocol_error_without_killing_runner(self):
        self.read_protocol_event("RUNTIME_READY")
        self.send_raw('{"kind":"COMMAND"')
        error = self.read_protocol_event("PROTOCOL_ERROR")
        self.assertEqual("MALFORMED_MESSAGE", error["errorCode"])

        command_id = str(uuid.uuid4())
        self.send(self.command(command_id, 1, 0, "START"))
        self.read_protocol_event("COMMAND_RESULT", commandId=command_id, status="SUCCEEDED")

    def test_wrong_identity_status_query_is_rejected_and_does_not_mutate_state(self):
        self.read_protocol_event("RUNTIME_READY")
        unknown_id = str(uuid.uuid4())
        self.send(self.status_query(unknown_id, runtimeGeneration=str(uuid.uuid4())))
        error = self.read_protocol_event("PROTOCOL_ERROR")
        self.assertEqual("IDENTITY_MISMATCH", error["errorCode"])
        self.assertEqual(unknown_id, error["relatedCommandId"])

        command_id = str(uuid.uuid4())
        self.send(self.command(command_id, 1, 0, "START"))
        succeeded = self.read_protocol_event(
            "COMMAND_RESULT", commandId=command_id, status="SUCCEEDED"
        )
        self.assertEqual(1, succeeded["stateVersion"])

    def test_invalid_numeric_field_returns_error_without_consuming_sequence(self):
        self.read_protocol_event("RUNTIME_READY")
        invalid_id = str(uuid.uuid4())
        self.send(self.command(invalid_id, "1", 0, "START"))
        error = self.read_protocol_event("PROTOCOL_ERROR")
        self.assertEqual("MALFORMED_MESSAGE", error["errorCode"])

        valid_id = str(uuid.uuid4())
        self.send(self.command(valid_id, 1, 0, "START"))
        self.read_protocol_event("COMMAND_RESULT", commandId=valid_id, status="SUCCEEDED")

    def test_wrong_protocol_version_is_rejected(self):
        self.read_protocol_event("RUNTIME_READY")
        command_id = str(uuid.uuid4())
        self.send(self.command(command_id, 1, 0, "START", protocolVersion="legacy"))
        error = self.read_protocol_event("PROTOCOL_ERROR")
        self.assertEqual("MALFORMED_MESSAGE", error["errorCode"])

    def test_duplicate_replay_is_stable_and_changed_body_conflicts(self):
        self.read_protocol_event("RUNTIME_READY")
        command_id = str(uuid.uuid4())
        command = self.command(command_id, 1, 0, "START")
        self.send(command)
        accepted = self.read_protocol_event(
            "COMMAND_RESULT", commandId=command_id, status="ACCEPTED"
        )
        succeeded = self.read_protocol_event(
            "COMMAND_RESULT", commandId=command_id, status="SUCCEEDED"
        )

        self.send(command)
        replayed_accepted = self.read_protocol_event(
            "COMMAND_RESULT", commandId=command_id, status="ACCEPTED"
        )
        replayed_succeeded = self.read_protocol_event(
            "COMMAND_RESULT", commandId=command_id, status="SUCCEEDED"
        )
        self.assertEqual(accepted, replayed_accepted)
        self.assertEqual(succeeded, replayed_succeeded)

        self.send({**command, "action": "STOP"})
        conflict = self.read_protocol_event("PROTOCOL_ERROR")
        self.assertEqual("COMMAND_ID_CONFLICT", conflict["errorCode"])

    def test_sequence_and_state_version_rejections_preserve_contract(self):
        self.read_protocol_event("RUNTIME_READY")
        skipped_id = str(uuid.uuid4())
        self.send(self.command(skipped_id, 2, 0, "START"))
        sequence_error = self.read_protocol_event("PROTOCOL_ERROR")
        self.assertEqual("SEQUENCE_MISMATCH", sequence_error["errorCode"])

        stale_id = str(uuid.uuid4())
        self.send(self.command(stale_id, 1, 9, "START"))
        rejected = self.read_protocol_event(
            "COMMAND_RESULT", commandId=stale_id, status="REJECTED"
        )
        self.assertEqual("STATE_VERSION_MISMATCH", rejected["errorCode"])

        valid_id = str(uuid.uuid4())
        self.send(self.command(valid_id, 2, 0, "START"))
        self.read_protocol_event("COMMAND_RESULT", commandId=valid_id, status="SUCCEEDED")


if __name__ == "__main__":
    unittest.main()
