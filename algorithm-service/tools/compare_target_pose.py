from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ORIGIN = {"eastM": -75.0, "northM": -310.0, "upM": 0.0}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare Unity scenario TARGET-001 with the first escort "
            "algorithm frame and report movement."
        )
    )
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument(
        "--base-url",
        default="http://localhost:8081/api/algorithm-runs",
        help="Backend algorithm-runs base URL.",
    )
    parser.add_argument(
        "--cookie",
        default="",
        help="Browser Cookie header, for example: JSESSIONID=...; XSRF-TOKEN=...",
    )
    parser.add_argument(
        "--scenario-file",
        type=Path,
        help="Saved Unity scenarioReady JSON file.",
    )
    parser.add_argument(
        "--frames",
        type=int,
        default=3,
        help="Number of algorithm frames to collect.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="Maximum seconds to wait for the requested frames.",
    )
    parser.add_argument(
        "--poll",
        type=float,
        default=0.25,
        help="Polling interval in seconds.",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=0.01,
        help="Position comparison tolerance in metres.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "test-results" / "target-pose-comparison.json",
        help="Output JSON report path.",
    )
    return parser.parse_args()


def number(value: Any, fallback: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return fallback
    return result if result == result else fallback


def pose_from_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "eastM": number(item.get("eastM", item.get("x"))),
        "northM": number(item.get("northM", item.get("y"))),
        "upM": number(item.get("upM", item.get("z"))),
        "headingDeg": number(item.get("headingDeg", item.get("heading"))),
    }


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise SystemExit(f"scenario file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON in {path}: {exc}") from exc


def scenario_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and isinstance(value.get("payload"), dict):
        return value["payload"]
    if isinstance(value, dict):
        return value
    raise SystemExit("scenario JSON must be an object or a Unity response object")


def find_scenario_target(payload: dict[str, Any]) -> dict[str, Any] | None:
    poses = payload.get("initialPoses")
    if not isinstance(poses, list):
        return None
    for item in poses:
        if not isinstance(item, dict):
            continue
        code = str(item.get("deviceCode", item.get("code", ""))).upper()
        if code == "TARGET-001":
            return pose_from_item(item)
    return None


def origin_from_payload(payload: dict[str, Any]) -> dict[str, float]:
    raw = payload.get("fleetOrigin")
    if not isinstance(raw, dict):
        return dict(DEFAULT_ORIGIN)
    return {
        "eastM": number(raw.get("eastM"), DEFAULT_ORIGIN["eastM"]),
        "northM": number(raw.get("northM"), DEFAULT_ORIGIN["northM"]),
        "upM": number(raw.get("upM"), DEFAULT_ORIGIN["upM"]),
    }


def to_algorithm_frame(
    pose: dict[str, Any],
    scenario_coordinate_frame: str,
    algorithm_coordinate_frame: str,
    origin: dict[str, float],
) -> dict[str, Any]:
    east = pose["eastM"]
    north = pose["northM"]
    up = pose["upM"]
    if scenario_coordinate_frame == "GLOBAL_ENU" and algorithm_coordinate_frame != "GLOBAL_ENU":
        east -= origin["eastM"]
        north -= origin["northM"]
        up -= origin["upM"]
    elif scenario_coordinate_frame != "GLOBAL_ENU" and algorithm_coordinate_frame == "GLOBAL_ENU":
        east += origin["eastM"]
        north += origin["northM"]
        up += origin["upM"]
    return {
        "x": east,
        "y": north,
        "z": up,
        "headingDeg": pose["headingDeg"],
    }


def get_json(url: str, cookie: str = "") -> Any:
    headers = {"Accept": "application/json"}
    if cookie.strip():
        headers["Cookie"] = cookie.strip()
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body[:300]}") from exc
    except URLError as exc:
        raise RuntimeError(f"cannot reach {url}: {exc.reason}") from exc


def unwrap_api_response(value: Any) -> Any:
    if isinstance(value, dict) and "data" in value:
        return value["data"]
    return value


def fetch_frames(
    base_url: str,
    run_id: int,
    wanted: int,
    timeout: float,
    poll: float,
    cookie: str,
) -> list[dict[str, Any]]:
    url = f"{base_url.rstrip('/')}/{run_id}/frames?afterSequence=0"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = unwrap_api_response(get_json(url, cookie))
        if isinstance(data, list):
            frames = [
                item for item in data
                if isinstance(item, dict) and isinstance(item.get("targets"), list)
            ]
            if len(frames) >= wanted:
                return sorted(frames, key=lambda item: number(item.get("sequence")))[:wanted]
        time.sleep(max(0.05, poll))
    raise RuntimeError(
        f"timed out waiting for {wanted} frames; inspect "
        f"{base_url.rstrip('/')}/{run_id}/status"
    )


def find_threat_target(frame: dict[str, Any]) -> dict[str, Any] | None:
    targets = frame.get("targets")
    if not isinstance(targets, list):
        return None
    for item in targets:
        if not isinstance(item, dict):
            continue
        target_type = str(item.get("type", "")).upper()
        code = str(item.get("code", "")).upper()
        if target_type == "THREAT_TARGET" or code in {"TARGET", "TARGET-001"}:
            return {
                "x": number(item.get("x")),
                "y": number(item.get("y")),
                "z": number(item.get("z")),
                "headingDeg": number(item.get("heading", item.get("headingDeg"))),
            }
    return None


def distance(left: dict[str, Any], right: dict[str, Any]) -> float:
    return sum(
        (number(left[key]) - number(right[key])) ** 2
        for key in ("x", "y", "z")
    ) ** 0.5


def main() -> int:
    args = parse_args()
    if args.frames < 1:
        raise SystemExit("--frames must be at least 1")

    scenario_pose = None
    scenario_frame = "GLOBAL_ENU"
    origin = dict(DEFAULT_ORIGIN)
    if args.scenario_file:
        payload = scenario_payload(read_json(args.scenario_file))
        scenario_run_id = int(number(payload.get("runId"), 0))
        if scenario_run_id and scenario_run_id != args.run_id:
            raise SystemExit(
                f"scenario runId mismatch: file={scenario_run_id}, "
                f"requested={args.run_id}"
            )
        scenario_pose = find_scenario_target(payload)
        scenario_frame = str(
            payload.get("initialPosesCoordinateFrame", "GLOBAL_ENU")
        ).upper()
        origin = origin_from_payload(payload)
        if scenario_pose is None:
            raise SystemExit("TARGET-001 was not found in scenario initialPoses")

    try:
        frames = fetch_frames(
            args.base_url,
            args.run_id,
            args.frames,
            args.timeout,
            args.poll,
            args.cookie,
        )
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    first_frame = frames[0]
    algorithm_frame = str(first_frame.get("coordinateFrame", "FLEET_LOCAL_ENU")).upper()
    first_sequence = int(number(first_frame.get("sequence")))
    algorithm_targets = []
    for frame in frames:
        target = find_threat_target(frame)
        algorithm_targets.append(
            {
                "sequence": int(number(frame.get("sequence"))),
                "timestamp": int(number(frame.get("timestamp"))),
                "pose": target,
                "phase": frame.get("phase", ""),
            }
        )

    expected = (
        to_algorithm_frame(scenario_pose, scenario_frame, algorithm_frame, origin)
        if scenario_pose is not None
        else None
    )
    first_algorithm = algorithm_targets[0]["pose"]
    comparison = None
    comparison_available = first_sequence == 1
    if expected is not None and first_algorithm is not None and comparison_available:
        comparison = {
            "positionErrorM": distance(expected, first_algorithm),
            "headingErrorDeg": abs(
                expected["headingDeg"] - first_algorithm["headingDeg"]
            ),
            "withinTolerance": (
                distance(expected, first_algorithm) <= args.tolerance
                and abs(expected["headingDeg"] - first_algorithm["headingDeg"]) <= 0.1
            ),
        }

    moved_after_first = False
    if first_algorithm is not None:
        moved_after_first = any(
            item["pose"] is not None
            and distance(first_algorithm, item["pose"]) > args.tolerance
            for item in algorithm_targets[1:]
        )

    report = {
        "runId": args.run_id,
        "algorithmCoordinateFrame": algorithm_frame,
        "scenarioCoordinateFrame": scenario_frame if scenario_pose else None,
        "fleetOrigin": origin if scenario_pose else None,
        "scenarioTargetPose": scenario_pose,
        "expectedAlgorithmPose": expected,
        "algorithmFrames": algorithm_targets,
        "firstFrameSequence": first_sequence,
        "initialFrameAvailable": comparison_available,
        "comparison": comparison,
        "movedAfterFirstFrame": moved_after_first,
        "success": (
            first_algorithm is not None
            and comparison_available
            and comparison is not None
            and comparison["withinTolerance"]
            and moved_after_first
        ),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n报告已保存：{args.output}")
    return 0 if report["success"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
