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


def command_reader(commands: queue.Queue) -> None:
    for line in sys.stdin:
        try:
            commands.put(json.loads(line))
        except json.JSONDecodeError:
            continue


def emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


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
    commands: queue.Queue = queue.Queue()
    threading.Thread(target=command_reader, args=(commands,), daemon=True).start()
    preview_enabled = bool(config.get("previewEnabled", False)) and not args.autostart
    state = "RUNNING" if args.autostart else "PREVIEW" if preview_enabled else "PREPARED"
    adapter.set_mission_active(state != "PREVIEW")
    emit({"event": "runtimeReady", "runId": args.run_id, "algorithmCode": args.algorithm, "state": state})
    # Publish the authoritative initial pose while the run is still prepared.
    # The UI uses this frame to align Unity's generated scene before START;
    # advancing only after START caused the target and fleet to jump on the
    # first visible mission frame.
    initial_frame = adapter.step().to_dict()
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
        if state in {"RUNNING", "PREVIEW"}:
            frame = adapter.step().to_dict()
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
