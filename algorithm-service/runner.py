from __future__ import annotations

import argparse
import base64
import json
import queue
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app.adapters import AdaptiveCaptureAdapter, AdaptiveEscortAdapter, CaptureAdapter, EscortAdapter


def command_reader(commands: queue.Queue, input_closed: threading.Event) -> None:
    try:
        for line in sys.stdin:
            try:
                commands.put(json.loads(line))
            except json.JSONDecodeError:
                continue
    finally:
        # The Java backend owns stdin.  EOF means its owning runtime no longer
        # exists, so the child must not remain as an orphaned preview process.
        input_closed.set()


def emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def emit_v1(payload: dict) -> None:
    """Write one protocol event to stdout; diagnostics never share stdout."""
    emit({"protocolVersion": "algorithm.command.v1", **payload})


def _normalize_frame_device_codes(frame: dict) -> dict:
    """Add the contract device identifier without removing the legacy code."""
    agents = frame.get("agents", [])
    if not isinstance(agents, list):
        return frame
    for agent in agents:
        if not isinstance(agent, dict):
            continue
        code = str(agent.get("code", "")).strip()
        device_code = str(agent.get("deviceCode", "")).strip()
        if code and not device_code:
            agent["deviceCode"] = code
    return frame


def _device_codes(frame: dict) -> list[str]:
    agents = frame.get("agents", [])
    if not isinstance(agents, list):
        return []
    return sorted({str(a.get("deviceCode", "")).strip() for a in agents
                   if isinstance(a, dict) and str(a.get("deviceCode", "")).strip()})


def v1_main(args: argparse.Namespace, adapter, config: dict) -> int:
    """Run the production command protocol around the existing adapter.

    The adapter remains authoritative for motion.  This layer owns only the
    process identity, command ordering, deduplication, heartbeats and results.
    """
    runtime_ref = args.runtime_ref
    generation = args.runtime_generation
    commands: queue.Queue = queue.Queue()
    input_closed = threading.Event()
    threading.Thread(target=command_reader, args=(commands, input_closed), daemon=True).start()
    state = "PREVIEW" if bool(config.get("previewEnabled", False)) else "PREPARED"
    state_version = 0
    command_sequence = 0
    heartbeat_sequence = 0
    event_sequences: dict[str, int] = {}
    result_cache: dict[str, list[dict]] = {}
    command_bodies: dict[str, str] = {}
    last_frame_sequence = 0
    frame = _normalize_frame_device_codes(adapter.step().to_dict())
    last_frame_sequence = int(frame.get("sequence", 0))
    adapter.set_mission_active(False)
    emit_v1({"runtimeRef": runtime_ref, "runtimeGeneration": generation,
             "kind": "RUNTIME_READY", "adapterId": adapter.code,
             "capabilities": ["START", "PAUSE", "RESUME", "STOP"],
             "state": state, "stateVersion": state_version})
    emit({"event": "frame", "payload": frame})
    frame_interval = 1.0 / max(1.0, args.fps)
    next_heartbeat = time.monotonic()

    def result(command: dict, status: str, error: str | None = None) -> dict:
        nonlocal state_version
        cid = str(command.get("commandId", ""))
        event_sequences[cid] = event_sequences.get(cid, 0) + 1
        if status == "SUCCEEDED":
            state_version += 1
        payload = {"protocolVersion": "algorithm.command.v1",
                   "runtimeRef": runtime_ref, "runtimeGeneration": generation,
                   "kind": "COMMAND_RESULT", "commandId": cid,
                   "eventSequence": event_sequences[cid], "status": status,
                   "runtimeState": state, "stateVersion": state_version,
                   "lastFrameSequence": last_frame_sequence,
                   "errorCode": error,
                   "affectedDeviceCodes": _device_codes(frame) if status == "SUCCEEDED" else []}
        result_cache.setdefault(cid, []).append(payload)
        emit_v1(payload)
        return payload

    while state not in {"STOPPED", "CANCELLED"}:
        started = time.monotonic()
        try:
            command = commands.get_nowait()
        except queue.Empty:
            command = None
        if command is not None:
            if isinstance(command, dict) and command.get("kind") == "STATUS_QUERY":
                cid = str(command.get("commandId", ""))
                cached = result_cache.get(cid)
                emit_v1({"runtimeRef": runtime_ref, "runtimeGeneration": generation,
                         "kind": "STATUS_REPLY", "queryId": command.get("queryId"),
                         "commandId": cid, "known": bool(cached),
                         "result": cached[-1] if cached else None})
            elif not isinstance(command, dict) or command.get("kind") != "COMMAND":
                emit_v1({"runtimeRef": runtime_ref, "runtimeGeneration": generation,
                         "kind": "PROTOCOL_ERROR", "relatedCommandId": None,
                         "errorCode": "MALFORMED_MESSAGE", "detail": "COMMAND object required"})
            else:
                cid = str(command.get("commandId", ""))
                if cid in result_cache:
                    body = json.dumps(command, sort_keys=True, separators=(",", ":"))
                    if command_bodies.get(cid) != body:
                        emit_v1({"runtimeRef": runtime_ref, "runtimeGeneration": generation,
                                 "kind": "PROTOCOL_ERROR", "relatedCommandId": cid,
                                 "errorCode": "COMMAND_ID_CONFLICT", "detail": "command body differs"})
                    else:
                        for cached in result_cache[cid]:
                            emit_v1(cached)
                elif command.get("runtimeRef") != runtime_ref or command.get("runtimeGeneration") != generation:
                    emit_v1({"runtimeRef": runtime_ref, "runtimeGeneration": generation,
                             "kind": "PROTOCOL_ERROR", "relatedCommandId": cid,
                             "errorCode": "IDENTITY_MISMATCH", "detail": "runtime identity mismatch"})
                elif int(command.get("commandSequence", -1)) != command_sequence + 1:
                    emit_v1({"runtimeRef": runtime_ref, "runtimeGeneration": generation,
                             "kind": "PROTOCOL_ERROR", "relatedCommandId": cid,
                             "errorCode": "SEQUENCE_MISMATCH", "detail": "command sequence is not contiguous"})
                elif command.get("action") not in {"START", "PAUSE", "RESUME", "STOP"}:
                    emit_v1({"runtimeRef": runtime_ref, "runtimeGeneration": generation,
                             "kind": "PROTOCOL_ERROR", "relatedCommandId": cid,
                             "errorCode": "MALFORMED_MESSAGE", "detail": "unsupported action"})
                else:
                    command_bodies[cid] = json.dumps(command, sort_keys=True, separators=(",", ":"))
                    command_sequence += 1
                    action = command["action"]
                    allowed = {"START": {"PREPARED", "PREVIEW"}, "PAUSE": {"RUNNING"},
                               "RESUME": {"PAUSED"}, "STOP": {"PREPARED", "PREVIEW", "RUNNING", "PAUSED"}}[action]
                    if state not in allowed:
                        result(command, "REJECTED", "INVALID_STATE")
                    elif int(command.get("expectedStateVersion", -1)) != state_version:
                        result(command, "REJECTED", "STATE_VERSION_MISMATCH")
                    else:
                        result(command, "ACCEPTED")
                        if action in {"START", "RESUME"}:
                            adapter.set_mission_active(True)
                            state = "RUNNING"
                        elif action == "PAUSE":
                            adapter.set_mission_active(False)
                            state = "PAUSED"
                        else:
                            state = "STOPPED"
                        result(command, "SUCCEEDED")
        if input_closed.is_set() and commands.empty():
            return 0
        if state == "RUNNING":
            frame = _normalize_frame_device_codes(adapter.step().to_dict())
            last_frame_sequence = int(frame.get("sequence", last_frame_sequence))
            emit({"event": "frame", "payload": frame})
        now = time.monotonic()
        if now >= next_heartbeat:
            heartbeat_sequence += 1
            emit_v1({"runtimeRef": runtime_ref, "runtimeGeneration": generation,
                     "kind": "HEARTBEAT", "heartbeatSequence": heartbeat_sequence,
                     "runtimeState": state, "stateVersion": state_version,
                     "lastFrameSequence": last_frame_sequence})
            next_heartbeat = now + 1.0
        time.sleep(max(0.01, frame_interval - (time.monotonic() - started)))
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--algorithm", choices=("GB_SFLA_CS", "ESCORT_GUARD"), required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--config", default="{}")
    parser.add_argument("--config-base64", default="")
    parser.add_argument("--config-file", default="")
    parser.add_argument("--fps", type=float, default=6.0)
    parser.add_argument("--autostart", action="store_true")
    parser.add_argument("--command-protocol", choices=("legacy", "v1"), default="legacy")
    parser.add_argument("--runtime-ref", default="")
    parser.add_argument("--runtime-generation", default="")
    args = parser.parse_args()
    if args.config_file:
        config_text = Path(args.config_file).read_text(encoding="utf-8")
    else:
        config_text = base64.b64decode(args.config_base64).decode("utf-8") if args.config_base64 else args.config
    config = json.loads(config_text)
    if args.algorithm == "GB_SFLA_CS":
        adapter = (
            AdaptiveCaptureAdapter(args.run_id, config)
            if int(config.get("targetCount", 1)) > 1
            else CaptureAdapter(args.run_id, config)
        )
    elif bool(config.get("adaptiveMultiTarget", False)):
        adapter = AdaptiveEscortAdapter(args.run_id, config)
    else:
        adapter = EscortAdapter(args.run_id, config)
    if args.command_protocol == "v1":
        if not args.runtime_ref or not args.runtime_generation:
            parser.error("--runtime-ref and --runtime-generation are required with --command-protocol v1")
        return v1_main(args, adapter, config)
    commands: queue.Queue = queue.Queue()
    input_closed = threading.Event()
    threading.Thread(
        target=command_reader,
        args=(commands, input_closed),
        daemon=True,
    ).start()
    preview_enabled = bool(config.get("previewEnabled", False)) and not args.autostart
    state = "RUNNING" if args.autostart else "PREVIEW" if preview_enabled else "PREPARED"
    adapter.set_mission_active(state != "PREVIEW")
    emit({"event": "runtimeReady", "runId": args.run_id, "algorithmCode": args.algorithm, "state": state})
    # Publish the authoritative initial pose while the run is still prepared.
    # The UI uses this frame to align Unity's generated scene before START;
    # advancing only after START caused the target and fleet to jump on the
    # first visible mission frame.
    initial_frame = _normalize_frame_device_codes(adapter.step().to_dict())
    emit({"event": "frame", "payload": initial_frame})
    frame_interval = 1.0 / max(1.0, args.fps)

    while state not in {"CANCELLED", "STOPPED"}:
        started = time.perf_counter()
        while True:
            try:
                command = commands.get_nowait()
            except queue.Empty:
                break
            action = str(command.get("action", "")).upper()
            if action in {"START", "RESUME"}:
                adapter.set_mission_active(True)
                state = "RUNNING"
            elif action == "PAUSE":
                state = "PAUSED"
            elif action == "CANCEL":
                state = "CANCELLED"
            elif action == "STOP":
                state = "STOPPED"
            elif action == "PLACE_THREAT":
                adapter.place_threat(float(command["x"]), float(command["y"]))
            elif action == "ACTIVE_CAPTURE":
                selected = adapter.activate_capture(command.get("threatCode"))
                emit({
                    "event": "commandResult",
                    "runId": args.run_id,
                    "action": action,
                    "success": True,
                    "selectedThreatCode": selected,
                })
            emit({"event": "stateChanged", "runId": args.run_id, "state": state})
        if input_closed.is_set() and commands.empty():
            # Avoid writing a final protocol event to a pipe whose reader has
            # already disappeared.  Returning also releases vendor resources.
            return 0
        if state in {"RUNNING", "PREVIEW"}:
            frame = _normalize_frame_device_codes(adapter.step().to_dict())
            emit({"event": "frame", "payload": frame})
            if state == "RUNNING" and frame.get("terminalStatus"):
                state = str(frame["terminalStatus"])
                emit({"event": "stateChanged", "runId": args.run_id, "state": state})
        elapsed = time.perf_counter() - started
        time.sleep(max(0.01, frame_interval - elapsed))
    emit({"event": "runtimeStopped", "runId": args.run_id, "state": state})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
