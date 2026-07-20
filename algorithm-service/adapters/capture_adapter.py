"""Adapter and capability probe for the legacy GB-SFLA-CS capture algorithm."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import math
import os
import sys
import threading
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from .models import AlgorithmEvent, AlgorithmRequest, AlgorithmResult, Assignment, VehicleState


_LEGACY_GLOBAL_LOCK = threading.Lock()


def _algorithm_service_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _capture_legacy_path() -> Path:
    path = _algorithm_service_dir() / "legacy" / "717_GBSFLACS.py"
    if not path.exists():
        raise FileNotFoundError(path)
    return path


@contextlib.contextmanager
def _headless_matplotlib_import():
    os.environ.setdefault("MPLBACKEND", "Agg")
    import matplotlib

    original_use = matplotlib.use

    def use_agg(_backend: str, *args: Any, **kwargs: Any) -> None:
        original_use("Agg", force=True)

    matplotlib.use = use_agg
    try:
        yield
    finally:
        matplotlib.use = original_use


@lru_cache(maxsize=1)
def load_capture_module():
    module_path = _capture_legacy_path()
    spec = importlib.util.spec_from_file_location("legacy_gbsflacs_capture", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load capture legacy module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with _headless_matplotlib_import(), contextlib.redirect_stdout(io.StringIO()):
        spec.loader.exec_module(module)
    return module


def _legacy_fixed_configuration(module) -> Dict[str, int]:
    return {
        "uavCount": int(getattr(module, "UAV_COUNT")),
        "usvCount": int(getattr(module, "USV_COUNT")),
        "targetCount": int(getattr(module, "TARGET_COUNT")),
        "minimumCaptureAgents": int(getattr(module, "MIN_CAPTURE_AGENTS")),
    }


def probe_capture_core_step() -> Dict[str, Any]:
    module = load_capture_module()
    with contextlib.redirect_stdout(io.StringIO()):
        env = module.SwarmEnv3D()
        assignments = env.algorithm.step()

    metrics = dict(getattr(env.algorithm, "metrics", {}))
    desired_waypoints = getattr(env.algorithm, "desired_waypoints", {}) or {}
    last_assignments = getattr(env.algorithm, "last_assignments", {}) or assignments
    return {
        "status": "RUNNING",
        "stage": "legacy-default-core-step",
        "fixedConfiguration": _legacy_fixed_configuration(module),
        "agentCount": int(len(env.agents)),
        "targetCount": int(len(env.targets)),
        "assignmentCount": int(len(last_assignments)),
        "waypointCount": int(len(desired_waypoints)),
        "metrics": metrics,
    }


def _requested_target_count(request: AlgorithmRequest) -> int:
    value = request.parameters.get("targetCount")
    if value is not None:
        try:
            number = int(value)
            return number if number >= 0 else 0
        except (TypeError, ValueError):
            pass
    return 1 if request.targetPosition is not None or request.targetId is not None else 0


def _unsupported_reason(fixed: Dict[str, int], request: AlgorithmRequest) -> str:
    requested = {
        "uavCount": len(request.uavs),
        "usvCount": len(request.usvs),
        "targetCount": _requested_target_count(request),
    }
    return (
        "Legacy SwarmEnv3D.reset constructs fixed arrays from global constants "
        f"UAV_COUNT={fixed['uavCount']}, USV_COUNT={fixed['usvCount']}, "
        f"TARGET_COUNT={fixed['targetCount']} and GBSFLACSAlgorithm indexes "
        "env.agents/env.targets by those internal IDs. The requested external "
        f"configuration is {requested}. Safe 3+3+1 state injection is not "
        "available without changing the legacy algorithm, so no assignments are returned."
    )


def _event(level: str, stage: str, message: str, detail: Dict[str, Any] | None = None) -> AlgorithmEvent:
    return AlgorithmEvent(level=level, stage=stage, message=message, detail=detail or {})


def _configuration_result(
    request: AlgorithmRequest,
    status: str,
    stage: str,
    message: str,
    fixed: Dict[str, int],
) -> AlgorithmResult:
    return AlgorithmResult(
        commandId=request.commandId,
        algorithmType=request.algorithmType,
        status=status,
        stage=stage,
        targetId=request.targetId,
        assignments=[],
        events=[_event("ERROR" if status == "INVALID_REQUEST" else "WARN", stage, message)],
        metrics={
            "fixedConfiguration": fixed,
            "requestedConfiguration": {
                "uavCount": len(request.uavs),
                "usvCount": len(request.usvs),
                "targetCount": _requested_target_count(request),
            },
        },
    )


def _finite_number(value: float) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _validate_vehicle_coordinates(vehicles: Iterable[VehicleState]) -> str | None:
    for vehicle in vehicles:
        if not all(
            _finite_number(value)
            for value in (vehicle.x, vehicle.y, vehicle.z, vehicle.heading)
        ):
            return f"Vehicle {vehicle.vehicleId} contains non-finite coordinates or heading."
    return None


def _validate_request(request: AlgorithmRequest, minimum_agents: int) -> str | None:
    if request.targetPosition is None:
        return "targetPosition is required for capture external state adaptation."
    if not request.uavs:
        return "At least one UAV is required for capture external state adaptation."
    if not request.usvs:
        return "At least one USV is required for capture external state adaptation."
    if _requested_target_count(request) != 1:
        return "Only exactly one target is supported in this capture adapter stage."
    total = len(request.uavs) + len(request.usvs)
    if not 1 <= minimum_agents <= total:
        return f"minimumAgents must satisfy 1 <= minimumAgents <= total platform count ({total})."
    if not all(
        _finite_number(value)
        for value in (
            request.targetPosition.x,
            request.targetPosition.y,
            request.targetPosition.z,
            request.targetPosition.heading,
        )
    ):
        return "targetPosition contains non-finite coordinates or heading."
    return _validate_vehicle_coordinates([*request.uavs, *request.usvs])


def _minimum_agents(request: AlgorithmRequest) -> int:
    total = len(request.uavs) + len(request.usvs)
    value = request.parameters.get("minimumAgents")
    if value is not None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
    return max(1, min(total, total // max(1, _requested_target_count(request))))


def _temporary_legacy_counts(module, uav_count: int, usv_count: int, target_count: int, minimum_agents: int):
    names = ("UAV_COUNT", "USV_COUNT", "TARGET_COUNT", "MIN_CAPTURE_AGENTS")
    original = {name: getattr(module, name) for name in names}
    module.UAV_COUNT = int(uav_count)
    module.USV_COUNT = int(usv_count)
    module.TARGET_COUNT = int(target_count)
    module.MIN_CAPTURE_AGENTS = int(minimum_agents)
    return original


def _restore_legacy_counts(module, original: Dict[str, Any]) -> None:
    for name, value in original.items():
        setattr(module, name, value)


def _inject_vehicle_state(env, vehicles: List[VehicleState], start_row: int) -> Dict[int, Tuple[VehicleState, int]]:
    mapping: Dict[int, Tuple[VehicleState, int]] = {}
    for offset, vehicle in enumerate(vehicles):
        row = start_row + offset
        env.agents[row, 0] = float(vehicle.x)
        env.agents[row, 1] = float(vehicle.y)
        env.agents[row, 2] = float(vehicle.z)
        env.agents[row, 4] = float(vehicle.heading)
        internal_agent_id = int(env.agents[row, 7])
        mapping[internal_agent_id] = (vehicle, row)
    return mapping


def _inject_target_state(env, request: AlgorithmRequest) -> Dict[int, str | None]:
    assert request.targetPosition is not None
    env.targets[0, 0] = float(request.targetPosition.x)
    env.targets[0, 1] = float(request.targetPosition.y)
    env.targets[0, 2] = float(request.targetPosition.z)
    return {0: request.targetId}


def _heading_to_waypoint(vehicle: VehicleState, waypoint) -> float:
    heading = math.atan2(float(waypoint[1]) - float(vehicle.y), float(waypoint[0]) - float(vehicle.x))
    if not math.isfinite(heading):
        raise ValueError(f"Computed non-finite heading for {vehicle.vehicleId}")
    return heading


def _assignment_for_vehicle(
    vehicle: VehicleState,
    internal_agent_id: int,
    internal_target_index: int,
    waypoint,
    role: str,
) -> Assignment:
    x = float(waypoint[0])
    y = float(waypoint[1])
    z = float(waypoint[2])
    heading = _heading_to_waypoint(vehicle, waypoint)
    if not all(math.isfinite(value) for value in (x, y, z, heading)):
        raise ValueError(f"GBSFLACSAlgorithm produced non-finite waypoint for {internal_agent_id}")
    return Assignment(
        vehicleId=vehicle.vehicleId,
        vehicleCode=vehicle.vehicleCode or vehicle.vehicleId,
        role=role,
        x=x,
        y=y,
        z=z,
        heading=heading,
        detail={
            "internalAgentId": internal_agent_id,
            "internalTargetIndex": internal_target_index,
            "inputPosition": {
                "x": float(vehicle.x),
                "y": float(vehicle.y),
                "z": float(vehicle.z),
                "heading": float(vehicle.heading),
            },
            "coordinateSource": "GBSFLACSAlgorithm.desired_waypoints",
            "assignmentSource": "GBSFLACSAlgorithm.step",
            "roleSource": "adapter platform-type mapping, not a native legacy role field",
        },
    )


def run_capture_once(request: AlgorithmRequest) -> AlgorithmResult:
    module = load_capture_module()
    fixed = _legacy_fixed_configuration(module)
    minimum_agents = _minimum_agents(request)
    validation_error = _validate_request(request, minimum_agents)
    if validation_error is not None:
        status = "UNSUPPORTED_CONFIGURATION" if "Only exactly one target" in validation_error else "INVALID_REQUEST"
        return _configuration_result(request, status, status.lower().replace("_", "-"), validation_error, fixed)

    original_counts: Dict[str, Any] | None = None
    start = time.perf_counter()
    with _LEGACY_GLOBAL_LOCK:
        try:
            original_counts = _temporary_legacy_counts(
                module,
                len(request.uavs),
                len(request.usvs),
                1,
                minimum_agents,
            )
            with contextlib.redirect_stdout(io.StringIO()):
                env = module.SwarmEnv3D()
                internal_mapping = {}
                internal_mapping.update(_inject_vehicle_state(env, request.uavs, 0))
                internal_mapping.update(_inject_vehicle_state(env, request.usvs, len(request.uavs)))
                _inject_target_state(env, request)
                legacy_assignments = env.algorithm.step()

            desired_waypoints = getattr(env.algorithm, "desired_waypoints", {}) or {}
            output_assignments: List[Assignment] = []
            missing_waypoints = []
            for internal_agent_id, (vehicle, row) in internal_mapping.items():
                internal_target_index = int(legacy_assignments.get(internal_agent_id, 0))
                waypoint = desired_waypoints.get(internal_agent_id)
                if waypoint is None:
                    missing_waypoints.append(internal_agent_id)
                    continue
                role = "TRACK" if row < len(request.uavs) else "ENCIRCLE"
                output_assignments.append(
                    _assignment_for_vehicle(
                        vehicle,
                        internal_agent_id,
                        internal_target_index,
                        waypoint,
                        role,
                    )
                )

            elapsed_ms = (time.perf_counter() - start) * 1000.0
            legacy_metrics = dict(getattr(env.algorithm, "metrics", {}))
            metrics = {
                **legacy_metrics,
                "inputScale": {
                    "uavCount": len(request.uavs),
                    "usvCount": len(request.usvs),
                    "targetCount": 1,
                    "minimumAgents": minimum_agents,
                },
                "elapsedMs": elapsed_ms,
                "legacyInternalAgentIds": sorted(internal_mapping),
                "legacyAssignments": {int(key): int(value) for key, value in legacy_assignments.items()},
            }
            if missing_waypoints:
                return AlgorithmResult(
                    commandId=request.commandId,
                    algorithmType=request.algorithmType,
                    status="FAILED",
                    stage="capture-assignment-waypoint-missing",
                    targetId=request.targetId,
                    assignments=[],
                    events=[
                        _event(
                            "ERROR",
                            "capture-assignment-waypoint-missing",
                            f"GBSFLACSAlgorithm.desired_waypoints missing internalAgentId(s): {missing_waypoints}",
                            {"missingInternalAgentIds": missing_waypoints},
                        )
                    ],
                    metrics=metrics,
                )

            return AlgorithmResult(
                commandId=request.commandId,
                algorithmType=request.algorithmType,
                status="RUNNING",
                stage="capture-assignments-generated",
                targetId=request.targetId,
                assignments=output_assignments,
                events=[
                    _event(
                        "INFO",
                        "capture-assignments-generated",
                        "Generated capture assignments from one real GBSFLACSAlgorithm core step.",
                        {
                            "coordinateSource": "GBSFLACSAlgorithm.desired_waypoints",
                            "assignmentSource": "GBSFLACSAlgorithm.step",
                        },
                    )
                ],
                metrics=metrics,
            )
        except Exception as exc:
            return AlgorithmResult(
                commandId=request.commandId,
                algorithmType=request.algorithmType,
                status="FAILED",
                stage="capture-adapter-failed",
                targetId=request.targetId,
                assignments=[],
                events=[_event("ERROR", "capture-adapter-failed", str(exc))],
                metrics={
                    "inputScale": {
                        "uavCount": len(request.uavs),
                        "usvCount": len(request.usvs),
                        "targetCount": 1,
                        "minimumAgents": minimum_agents,
                    },
                    "elapsedMs": (time.perf_counter() - start) * 1000.0,
                },
            )
        finally:
            if original_counts is not None:
                _restore_legacy_counts(module, original_counts)
