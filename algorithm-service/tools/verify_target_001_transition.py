from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from compare_target_pose import (
    DEFAULT_ORIGIN,
    distance,
    fetch_frames,
    find_scenario_target,
    find_threat_target,
    number,
    origin_from_payload,
    read_json,
    scenario_payload,
    to_algorithm_frame,
)


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify TARGET-001 continuity between Unity scenarioReady, "
            "algorithm sequence 1, and the first frame after START."
        )
    )
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument(
        "--scenario-file",
        type=Path,
        required=True,
        help="JSON file containing the Unity scenarioReady receipt.",
    )
    parser.add_argument(
        "--cookie",
        default="",
        help="Browser Cookie header used to access the local backend.",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8081/api/algorithm-runs",
    )
    parser.add_argument(
        "--initial-tolerance",
        type=float,
        default=0.01,
        help="Maximum allowed scenario-to-sequence-1 position error in metres.",
    )
    parser.add_argument(
        "--max-start-step",
        type=float,
        default=3.0,
        help="Maximum allowed TARGET-001 movement from sequence 1 to sequence 2.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "test-results" / "target-001-transition.json",
    )
    return parser.parse_args()


def as_global_pose(
    pose: dict[str, Any],
    coordinate_frame: str,
    origin: dict[str, float],
) -> dict[str, float]:
    if coordinate_frame == "GLOBAL_ENU":
        return {
            "eastM": number(pose.get("x", pose.get("eastM"))),
            "northM": number(pose.get("y", pose.get("northM"))),
            "upM": number(pose.get("z", pose.get("upM"))),
            "headingDeg": number(pose.get("headingDeg")),
        }
    return {
        "eastM": number(pose.get("x")) + origin["eastM"],
        "northM": number(pose.get("y")) + origin["northM"],
        "upM": number(pose.get("z")) + origin["upM"],
        "headingDeg": number(pose.get("headingDeg")),
    }


def position_error(left: dict[str, Any], right: dict[str, Any]) -> float:
    return distance(
        {"x": left["eastM"], "y": left["northM"], "z": left["upM"]},
        {"x": right["eastM"], "y": right["northM"], "z": right["upM"]},
    )


def main() -> int:
    args = parse_args()
    scenario = scenario_payload(read_json(args.scenario_file))
    scenario_run_id = int(number(scenario.get("runId"), 0))
    if scenario_run_id and scenario_run_id != args.run_id:
        raise SystemExit(
            f"runId mismatch: scenario file={scenario_run_id}, requested={args.run_id}"
        )

    scenario_target = find_scenario_target(scenario)
    if scenario_target is None:
        raise SystemExit("TARGET-001 was not found in scenarioReady.initialPoses")

    scenario_frame = str(
        scenario.get("initialPosesCoordinateFrame", "GLOBAL_ENU")
    ).upper()
    origin = origin_from_payload(scenario) or dict(DEFAULT_ORIGIN)
    frames = fetch_frames(
        args.base_url,
        args.run_id,
        wanted=2,
        timeout=20.0,
        poll=0.25,
        cookie=args.cookie,
    )
    frame_by_sequence = {
        int(number(frame.get("sequence"))): frame
        for frame in frames
    }
    first_frame = frame_by_sequence.get(1)
    if first_frame is None:
        raise SystemExit("sequence=1 was not returned by the algorithm runtime")

    post_start_frame = frame_by_sequence.get(2)
    if post_start_frame is None:
        raise SystemExit(
            "sequence=2 is not available yet. Click Start, wait briefly, then rerun."
        )

    algorithm_frame = str(
        first_frame.get("coordinateFrame", "FLEET_LOCAL_ENU")
    ).upper()
    expected_local = to_algorithm_frame(
        scenario_target,
        scenario_frame,
        algorithm_frame,
        origin,
    )
    first_target = find_threat_target(first_frame)
    second_target = find_threat_target(post_start_frame)
    if first_target is None or second_target is None:
        raise SystemExit("TARGET-001 / threat target was missing from algorithm frames")

    before_start = {
        "source": "Unity scenarioReady.initialPoses",
        **scenario_target,
    }
    sequence_one = {
        "source": "algorithm sequence=1",
        "sequence": 1,
        **as_global_pose(first_target, algorithm_frame, origin),
    }
    after_start = {
        "source": "algorithm sequence=2",
        "sequence": 2,
        **as_global_pose(second_target, algorithm_frame, origin),
    }
    initial_error = position_error(before_start, sequence_one)
    start_step = position_error(sequence_one, after_start)
    report = {
        "runId": args.run_id,
        "algorithmCoordinateFrame": algorithm_frame,
        "fleetOrigin": origin,
        "beforeStart": before_start,
        "expectedSequenceOneLocal": expected_local,
        "sequenceOne": sequence_one,
        "afterStart": after_start,
        "scenarioToSequenceOneErrorM": initial_error,
        "sequenceOneToTwoDistanceM": start_step,
        "initialPoseMatched": initial_error <= args.initial_tolerance,
        "startTransitionContinuous": start_step <= args.max_start_step,
        "success": (
            initial_error <= args.initial_tolerance
            and start_step <= args.max_start_step
        ),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nReport saved: {args.output}")
    return 0 if report["success"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
