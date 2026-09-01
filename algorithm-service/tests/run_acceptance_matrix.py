"""Repeatable 3..30 fleet acceptance matrix for both virtual algorithms.

This is intentionally a script rather than a default unit test because a full
matrix is several thousand simulation frames.  CI can invoke it explicitly.
"""

from __future__ import annotations

import contextlib
import io
import json
import math
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.adapters.adaptive_capture import AdaptiveCaptureAdapter
from app.adapters.adaptive_escort import AdaptiveEscortAdapter
from app.scenario import derive_scenario_plan


CONFIGURATIONS = [
    (3, 3), (4, 5), (5, 4), (5, 5), (6, 8),
    (8, 6), (8, 8), (10, 10), (10, 12), (12, 10),
    (12, 15), (15, 12), (15, 15), (18, 20), (20, 18),
    (20, 20), (20, 25), (25, 20), (25, 25), (30, 30),
]

STAGE_RANK = {
    "PREVIEW": 0, "ESCAPE": 1, "ESCAPE_PURSUIT": 1,
    "PURSUIT": 2, "INTERCEPT": 3, "INTERCEPTING": 3,
    "ENCIRCLEMENT": 4, "ACTIVE_CAPTURE": 4,
    # Stable hold and gap maintenance are substates of one final-containment
    # macro phase. Moving among them is repair work, not a mission regression.
    "GAP_REPAIR": 5, "STABLE_CONTAINMENT": 5,
    "CONTAINMENT": 5, "CAPTURING": 5,
    "COMPLETED": 6, "CAPTURED": 6,
}


def run_one(mode: str, uav: int, usv: int, seed: int) -> dict[str, object]:
    plan = derive_scenario_plan(uav, usv)
    config = {
        "uavCount": uav, "usvCount": usv, "seed": seed,
        "uavSpeedMps": 5.0, "usvSpeedMps": 3.0,
    }
    if mode == "capture":
        config["targetCount"] = plan.threat_count
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            adapter = AdaptiveCaptureAdapter(seed, config)
        frame_limit = 1800
    else:
        adapter = AdaptiveEscortAdapter(seed, config)
        # This is only a bounded test watchdog, never a mission deadline.
        # Dense asymmetric fleets can legitimately spend longer resolving a
        # final collision-free slot and inward bow orientation.
        frame_limit = 9000 + max(0, plan.threat_count - 1) * 1500
    adapter.set_mission_active(True)
    previous_positions: dict[str, tuple[float, float]] = {}
    stationary_frames: dict[str, int] = {}
    maximum_stationary = 0
    maximum_stationary_code = ""
    maximum_stationary_role = ""
    macro_regressions = 0
    previous_rank = 0
    high_water_rank = 0
    minimum_pair_distance = math.inf
    started = time.perf_counter()
    frame = None
    for _ in range(frame_limit):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            frame = adapter.step()
        stage = str(frame.metrics.get("missionStage", frame.phase))
        rank = STAGE_RANK.get(stage, previous_rank)
        # Count a regression once at the transition edge. The former high-water
        # comparison counted every frame spent in the repaired stage.
        if rank < high_water_rank and rank != previous_rank:
            macro_regressions += 1
        previous_rank = rank
        high_water_rank = max(high_water_rank, rank)
        current_positions = {item.code: (item.x, item.y) for item in frame.agents}
        for code, current in current_positions.items():
            previous = previous_positions.get(code)
            moved = math.inf if previous is None else math.hypot(
                current[0] - previous[0], current[1] - previous[1]
            )
            role = next(item.role for item in frame.agents if item.code == code)
            # These roles intentionally hold a tactical station. A stationary
            # patrol/interceptor is a defect; a blocker, observer or final-ring
            # member remaining on its assigned point is expected behaviour.
            allowed_hold = role in {
                "CAPTURE", "CONTAINMENT", "RING_MEMBER", "CLOSE_GUARD",
                "BLOCKER", "GAP_BLOCKER", "CONFRONT",
                "CAPTURE_RESERVE", "OUTER_INTERCEPT", "CONVOY_SUPPORT",
                "LOCAL_OVERWATCH",
            }
            stationary_frames[code] = (
                stationary_frames.get(code, 0) + 1
                if moved < 0.002 and not allowed_hold
                else 0
            )
            if stationary_frames[code] > maximum_stationary:
                maximum_stationary = stationary_frames[code]
                maximum_stationary_code = code
                maximum_stationary_role = role
        previous_positions = current_positions
        if frame.sequence % 10 == 0:
            for index, left in enumerate(frame.agents):
                for right in frame.agents[index + 1:]:
                    minimum_pair_distance = min(
                        minimum_pair_distance,
                        math.hypot(left.x - right.x, left.y - right.y),
                    )
        if frame.terminalStatus is not None:
            break
    assert frame is not None
    groups = frame.metrics.get("captureGroups", [])
    max_gap = max(
        (float(group.get(
            "postGlobalMaxGapDeg",
            group.get("maxAngularGapDeg", group.get("maxGapDeg", 360.0)),
        )) for group in groups),
        default=360.0,
    )
    strict_contracts = [
        group.get("canonicalContainmentContract", group.get("containmentContract", {}))
        for group in groups
    ]
    blockers = [str(contract.get("blocker", "")) for contract in strict_contracts]
    group_states = [str(group.get("state", "")) for group in groups]
    group_arrivals = [float(group.get("arrivalRatio", 0.0)) for group in groups]
    group_max_gaps = [
        float(contract.get("maxGapDeg", group.get("postGlobalMaxGapDeg", 360.0)))
        for group, contract in zip(groups, strict_contracts)
    ]
    group_allowed_gaps = [
        float(contract.get("maxAllowedGapDeg", group.get("postGlobalMaxAllowedGapDeg", 0.0)))
        for group, contract in zip(groups, strict_contracts)
    ]
    group_slot_errors = [
        float(contract.get(
            "maximumSlotErrorM",
            group.get("maximumSlotErrorM", group.get("postGlobalMaxSlotErrorM", math.inf)),
        ))
        for group, contract in zip(groups, strict_contracts)
    ]
    group_usv_heading_errors = [
        float(contract.get(
            "maximumUsvHeadingErrorDeg",
            group.get("maximumUsvHeadingErrorDeg", 180.0),
        ))
        for group, contract in zip(groups, strict_contracts)
    ]
    strict_group_ready = [
        bool(contract.get("ready", group.get("postGlobalContainmentReady", False)))
        and gap <= allowed + 1e-6
        and error <= 3.5 + 1e-6
        for group, contract, gap, allowed, error in zip(
            groups, strict_contracts, group_max_gaps, group_allowed_gaps, group_slot_errors
        )
    ]
    worst_diagnostic: dict[str, object] = {}
    not_arrived: list[list[dict[str, object]]] = []
    if mode == "escort":
        for threat_index, threat in enumerate(adapter.threats):
            members = adapter._capture_members(threat_index)
            slots = adapter._capture_slots(members, threat) if members else []
            center = adapter._capture_center(threat, members)
            tolerance = (12.0, 7.0, 3.5)[min(2, threat.capture_stage)]
            missed = []
            for member, slot in zip(members, slots):
                expected = slot.point((center[0], center[1], 0.0))
                error = math.hypot(member.x - expected[0], member.y - expected[1])
                if error > tolerance:
                    fixed_targets = [*adapter.protected, *adapter.threats]
                    nearest_fixed = min(
                        fixed_targets,
                        key=lambda item: math.hypot(member.x - item.x, member.y - item.y),
                    )
                    missed.append({
                        "code": member.code,
                        "errorM": round(error, 2),
                        "current": [round(member.x, 2), round(member.y, 2)],
                        "expected": [round(expected[0], 2), round(expected[1], 2)],
                        "nearestFixed": nearest_fixed.code,
                        "nearestFixedDistanceM": round(
                            math.hypot(member.x - nearest_fixed.x, member.y - nearest_fixed.y), 2,
                        ),
                    })
            not_arrived.append(missed)
    if mode == "escort" and maximum_stationary_code:
        vehicle = next(
            (item for item in adapter.vehicles if item.code == maximum_stationary_code),
            None,
        )
        if vehicle is not None:
            desired = adapter._desired_position(vehicle)
            worst_diagnostic = {
                "assignedThreat": vehicle.assigned_threat,
                "current": [round(vehicle.x, 2), round(vehicle.y, 2)],
                "desired": [round(desired[0], 2), round(desired[1], 2)],
                "distanceToDesiredM": round(math.hypot(desired[0] - vehicle.x, desired[1] - vehicle.y), 2),
            }
    return {
        "mode": mode,
        "uav": uav,
        "usv": usv,
        "targets": plan.threat_count,
        "frames": frame.sequence,
        "terminal": frame.terminalStatus,
        "stage": frame.metrics.get("missionStage", frame.phase),
        "progress": frame.metrics.get("progress"),
        "captured": frame.metrics.get("capturedTargetCount", frame.metrics.get("capturedThreatCount")),
        "macroRegressions": macro_regressions,
        "maxUnexpectedStationaryFrames": maximum_stationary,
        "maxUnexpectedStationaryCode": maximum_stationary_code,
        "maxUnexpectedStationaryRole": maximum_stationary_role,
        "minimumPairDistanceM": round(minimum_pair_distance, 3),
        "maximumFinalGapDeg": round(max_gap, 2),
        "finalBlockers": blockers,
        "captureGroupStates": group_states,
        "captureGroupArrivalRatios": group_arrivals,
        "captureGroupMaximumGapsDeg": group_max_gaps,
        "captureGroupAllowedGapsDeg": group_allowed_gaps,
        "captureGroupMaximumSlotErrorsM": group_slot_errors,
        "captureGroupMaximumUsvHeadingErrorsDeg": group_usv_heading_errors,
        "captureGroupStrictReady": strict_group_ready,
        "worstStationaryDiagnostic": worst_diagnostic,
        "notArrivedMembers": not_arrived,
        "protectedTargets": [
            {
                "code": item.code,
                "position": [round(item.x, 2), round(item.y, 2)],
                "destination": [round(item.destination_x, 2), round(item.destination_y, 2)],
                "routeProgress": round(max(
                    0.0,
                    min(1.0, (item.x - adapter.protected_start_x[item.code]) / max(
                        1.0, item.destination_x - adapter.protected_start_x[item.code]
                    )),
                ), 3),
                "state": item.state,
            }
            for item in getattr(adapter, "protected", [])
        ],
        "threatAssignments": [
            {
                "code": threat.code,
                "state": threat.state,
                "forced": threat.forced,
                "uav": sum(
                    item.kind == "UAV" and item.assigned_threat == index
                    for item in adapter.vehicles
                ),
                "usv": sum(
                    item.kind == "USV" and item.assigned_threat == index
                    for item in adapter.vehicles
                ),
            }
            for index, threat in enumerate(getattr(adapter, "threats", []))
        ],
        "elapsedSeconds": round(time.perf_counter() - started, 3),
        "passed": (
            frame.terminalStatus == "COMPLETED"
            and macro_regressions == 0
            and maximum_stationary <= 30
            and minimum_pair_distance >= 7.0
            and bool(groups)
            and all(strict_group_ready)
            and all(value >= 1.0 for value in group_arrivals)
            and all(value in {"CAPTURED", "SECURED"} for value in group_states)
        ),
    }


def main() -> int:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 20260814
    configurations = (
        [(int(sys.argv[2]), int(sys.argv[3]))]
        if len(sys.argv) >= 4
        else CONFIGURATIONS
    )
    modes = (
        (sys.argv[2],)
        if len(sys.argv) >= 3 and sys.argv[2] in {"capture", "escort"}
        else (sys.argv[4],)
        if len(sys.argv) >= 5
        else ("capture", "escort")
    )
    results = []
    for uav, usv in configurations:
        for mode in modes:
            result = run_one(mode, uav, usv, seed + uav * 101 + usv * 17)
            results.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
    failed = [item for item in results if not item["passed"]]
    print(json.dumps({
        "runs": len(results), "passed": len(results) - len(failed),
        "failed": len(failed), "failures": failed,
    }, ensure_ascii=False), flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
