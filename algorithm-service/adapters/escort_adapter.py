"""Adapter for the legacy escort guard simulator."""

from __future__ import annotations

import importlib.util
import math
import sys
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

from .models import (
    AlgorithmEvent,
    AlgorithmRequest,
    AlgorithmResult,
    Assignment,
    Position,
    VehicleState,
)


ROLE_MAP = {
    "core": "DEFEND",
    "wing": "INTERCEPT",
    "escort": "ESCORT",
}


def _algorithm_service_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _escort_legacy_path() -> Path:
    legacy_dir = _algorithm_service_dir() / "legacy"
    matches = [path for path in legacy_dir.glob("*.py") if path.name != "717_GBSFLACS.py"]
    if len(matches) != 1:
        raise FileNotFoundError("Expected one escort legacy Python file in algorithm-service/legacy")
    return matches[0]


@lru_cache(maxsize=1)
def load_escort_module():
    module_path = _escort_legacy_path()
    spec = importlib.util.spec_from_file_location("legacy_escort_guard", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load escort legacy module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _finite(value: float, fallback: float = 0.0) -> float:
    number = float(value)
    return number if math.isfinite(number) else fallback


def _xy(position: Position | None, fallback: np.ndarray) -> np.ndarray:
    if position is None:
        return fallback.copy()
    return np.array([_finite(position.x), _finite(position.y)], dtype=float)


def _scene_from_parameters(parameters: Dict[str, object]) -> str:
    raw = str(parameters.get("threatDirection") or parameters.get("scene") or "front").strip().lower()
    normalized = raw.replace("-", "_")
    mapping = {
        "front": "front",
        "front_right": "front_right",
        "right": "right",
        "back_right": "back_right",
        "back": "back",
        "back_left": "back_left",
        "left": "left",
        "front_left": "front_left",
        "forward": "front",
        "ahead": "front",
        "rear": "back",
        "behind": "back",
    }
    return mapping.get(normalized, "front")


def _numeric_parameter(parameters: Dict[str, object], name: str, fallback: float) -> float:
    try:
        value = float(parameters.get(name, fallback))
    except (TypeError, ValueError):
        return fallback
    return value if math.isfinite(value) and value > 0.0 else fallback


def _assign_platform_inputs(simulator, request: AlgorithmRequest) -> List[Tuple[object, VehicleState]]:
    by_kind: Dict[str, List[VehicleState]] = {
        "UAV": list(request.uavs),
        "USV": list(request.usvs),
    }
    mapped: List[Tuple[object, VehicleState]] = []
    for platform in simulator.platforms:
        vehicles = by_kind.get(platform.kind, [])
        if not vehicles:
            raise ValueError(f"No input vehicle available for legacy platform kind {platform.kind}")
        vehicle = vehicles.pop(0)
        platform.position = np.array([_finite(vehicle.x), _finite(vehicle.y)], dtype=float)
        platform.goal = platform.position.copy()
        mapped.append((platform, vehicle))
    return mapped


def _assignment_from_platform(platform, vehicle: VehicleState) -> Assignment:
    coordinate = platform.goal if platform.goal is not None else platform.position
    coordinate_source = "Platform.goal" if platform.goal is not None else "Platform.position"
    legacy_role = str(platform.role)
    return Assignment(
        vehicleId=vehicle.vehicleId,
        vehicleCode=vehicle.vehicleCode or vehicle.vehicleId,
        role=ROLE_MAP.get(legacy_role, "STANDBY"),
        x=float(coordinate[0]),
        y=float(coordinate[1]),
        z=_finite(vehicle.z),
        heading=_finite(vehicle.heading),
        detail={
            "legacyPlatformId": platform.identifier,
            "legacyKind": platform.kind,
            "legacyRole": legacy_role,
            "coordinateSource": coordinate_source,
            "zSource": "inputVehicle",
            "headingSource": "inputVehicle",
        },
    )


def run_escort_once(request: AlgorithmRequest) -> AlgorithmResult:
    module = load_escort_module()
    scene = _scene_from_parameters(request.parameters)
    ring_radius = _numeric_parameter(request.parameters, "escortRadius", 6.0)
    total_forward_guards = int(min(5, max(1, len(request.uavs) + len(request.usvs))))

    simulator = module.EscortGuardSimulator(
        scene=scene,
        threat_active=False,
        num_uav=len(request.uavs),
        num_usv=len(request.usvs),
        total_forward_guards=total_forward_guards,
        ring_radius=ring_radius,
    )
    if request.targetPosition is not None:
        simulator.own_position = _xy(request.targetPosition, simulator.own_position)
        simulator.own_goal = simulator.own_position.copy()

    mapped = _assign_platform_inputs(simulator, request)

    if request.threatPosition is not None:
        simulator.activate_threat_at(_xy(request.threatPosition, simulator.enemy_position))
    else:
        simulator.activate_threat(scene)

    simulator.step()
    status = simulator.status()

    assignments = [_assignment_from_platform(platform, vehicle) for platform, vehicle in mapped]
    events = [
        AlgorithmEvent(
            level="INFO",
            stage=str(status.get("phase", "")),
            message="EscortGuardSimulator executed one step.",
            detail={
                "frame": status.get("frame"),
                "coreGuard": status.get("core_guard"),
                "threatLabel": status.get("threat_label"),
            },
        )
    ]
    metrics = {
        "frame": status.get("frame"),
        "phase": status.get("phase"),
        "enemyPosition": np.asarray(status.get("enemy_position"), dtype=float).tolist(),
        "ownPosition": np.asarray(simulator.own_position, dtype=float).tolist(),
        "platformRoles": {
            vehicle.vehicleId: str(platform.role) for platform, vehicle in mapped
        },
        "blockingError": status.get("blocking_error"),
        "strictBlocking": status.get("strict_blocking"),
    }
    return AlgorithmResult(
        commandId=request.commandId,
        algorithmType=request.algorithmType,
        status="RUNNING",
        stage=str(status.get("phase", "one-step")),
        targetId=request.targetId,
        assignments=assignments,
        events=events,
        metrics=metrics,
    )
