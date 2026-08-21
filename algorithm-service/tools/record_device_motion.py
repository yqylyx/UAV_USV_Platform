from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CODES = (
    "UAV-001",
    "UAV-050",
    "UAV-100",
    "USV-001",
    "USV-050",
    "USV-100",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record selected device motion from the algorithm runner."
    )
    parser.add_argument(
        "--algorithm",
        choices=("GB_SFLA_CS", "ESCORT_GUARD"),
        required=True,
    )
    parser.add_argument("--uav-count", type=int, default=100)
    parser.add_argument("--usv-count", type=int, default=100)
    parser.add_argument("--target-count", type=int, default=1)
    parser.add_argument("--frames", type=int, default=30)
    parser.add_argument("--fps", type=float, default=6.0)
    parser.add_argument("--run-id", type=int, default=None)
    parser.add_argument("--seed", type=int, default=20260814)
    parser.add_argument("--threat-frame", type=int, default=70)
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "test-results" / "device-motion"),
    )
    parser.add_argument(
        "--codes",
        nargs="*",
        default=list(DEFAULT_CODES),
        help="Device codes to record.",
    )
    return parser.parse_args()


def run_id_or_default(value: int | None) -> int:
    return value if value is not None else int(time.time() * 1000)


def build_config(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "uavCount": max(1, min(128, args.uav_count)),
        "usvCount": max(1, min(128, args.usv_count)),
        "targetCount": max(1, min(1, args.target_count)),
        "seed": args.seed,
        "threatFrame": max(1, args.threat_frame),
        "targetBehavior": "MOVING",
    }


def distance(previous: dict[str, Any] | None, current: dict[str, Any]) -> float:
    if previous is None:
        return 0.0
    return math.sqrt(
        sum(
            (float(current[key]) - float(previous[key])) ** 2
            for key in ("x", "y", "z")
        )
    )


def heading_delta(previous: float | None, current: float) -> float:
    if previous is None:
        return 0.0
    return abs((current - previous + 180.0) % 360.0 - 180.0)


def read_frames(
    process: subprocess.Popen[str],
    frame_limit: int,
) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    while len(frames) < frame_limit:
        line = process.stdout.readline() if process.stdout else ""
        if not line:
            break
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("event") == "frame" and isinstance(event.get("payload"), dict):
            frames.append(event["payload"])
    return frames


def stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if process.stdin:
        process.stdin.write('{"action":"CANCEL"}\n')
        process.stdin.flush()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def collect_rows(
    frames: list[dict[str, Any]],
    selected_codes: set[str],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    previous: dict[str, dict[str, Any]] = {}
    summary: dict[str, dict[str, Any]] = {}

    for frame in frames:
        timestamp = int(frame.get("timestamp", 0))
        sequence = int(frame.get("sequence", 0))
        devices = [
            *frame.get("agents", []),
            *frame.get("targets", []),
        ]
        for item in devices:
            code = str(item.get("code", ""))
            if code not in selected_codes:
                continue
            current = {
                "x": float(item.get("x", 0.0)),
                "y": float(item.get("y", 0.0)),
                "z": float(item.get("z", 0.0)),
                "heading": float(item.get("heading", 0.0)),
            }
            previous_item = previous.get(code)
            step_distance = distance(previous_item, current)
            elapsed = (
                (timestamp - int(previous_item["timestamp"])) / 1000.0
                if previous_item
                else 0.0
            )
            rows.append(
                {
                    "sequence": sequence,
                    "timestamp": timestamp,
                    "code": code,
                    "type": item.get("type", ""),
                    "x": current["x"],
                    "y": current["y"],
                    "z": current["z"],
                    "headingDeg": current["heading"],
                    "stepDistance": step_distance,
                    "stepSpeed": step_distance / elapsed if elapsed > 0 else 0.0,
                    "phase": frame.get("phase", ""),
                }
            )
            previous[code] = {**current, "timestamp": timestamp}
            item_summary = summary.setdefault(
                code,
                {
                    "code": code,
                    "samples": 0,
                    "movedSamples": 0,
                    "totalDistance": 0.0,
                    "maxStepDistance": 0.0,
                    "first": None,
                    "last": None,
                },
            )
            item_summary["samples"] += 1
            item_summary["movedSamples"] += int(step_distance > 1e-6)
            item_summary["totalDistance"] += step_distance
            item_summary["maxStepDistance"] = max(
                item_summary["maxStepDistance"],
                step_distance,
            )
            if item_summary["first"] is None:
                item_summary["first"] = {
                    "sequence": sequence,
                    **current,
                }
            item_summary["last"] = {
                "sequence": sequence,
                **current,
            }

    return rows, summary


def main() -> int:
    args = parse_args()
    if args.frames <= 0:
        raise SystemExit("--frames must be greater than zero")

    run_id = run_id_or_default(args.run_id)
    config_text = json.dumps(build_config(args), ensure_ascii=False)
    command = [
        sys.executable,
        str(ROOT / "runner.py"),
        "--algorithm",
        args.algorithm,
        "--run-id",
        str(run_id),
        "--config",
        config_text,
        "--fps",
        str(max(1.0, args.fps)),
        "--autostart",
    ]
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
    )
    try:
        frames = read_frames(process, args.frames)
    finally:
        stop_process(process)

    selected_codes = {code.upper() for code in args.codes}
    rows, summary = collect_rows(frames, selected_codes)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{args.algorithm.lower()}-{run_id}"
    csv_path = output_dir / f"{stem}.csv"
    json_path = output_dir / f"{stem}.json"

    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        fieldnames = list(rows[0].keys()) if rows else [
            "sequence",
            "timestamp",
            "code",
            "type",
            "x",
            "y",
            "z",
            "headingDeg",
            "stepDistance",
            "stepSpeed",
            "phase",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    result = {
        "algorithmCode": args.algorithm,
        "runId": run_id,
        "config": build_config(args),
        "framesRead": len(frames),
        "selectedCodes": sorted(selected_codes),
        "summary": summary,
        "missingSelectedCodes": sorted(selected_codes - set(summary)),
        "files": {
            "csv": str(csv_path),
            "json": str(json_path),
        },
    }
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if frames else 1


if __name__ == "__main__":
    raise SystemExit(main())
