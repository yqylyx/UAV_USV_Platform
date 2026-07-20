"""Shared input and output models for legacy algorithm adapters."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class Position:
    x: float
    y: float
    z: float = 0.0
    heading: float = 0.0


@dataclass(frozen=True)
class VehicleState:
    vehicleId: str
    x: float
    y: float
    z: float = 0.0
    heading: float = 0.0
    vehicleCode: Optional[str] = None


@dataclass(frozen=True)
class AlgorithmRequest:
    commandId: str
    algorithmType: str
    targetId: Optional[str] = None
    targetPosition: Optional[Position] = None
    threatTargetId: Optional[str] = None
    threatPosition: Optional[Position] = None
    uavs: List[VehicleState] = field(default_factory=list)
    usvs: List[VehicleState] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Assignment:
    vehicleId: str
    vehicleCode: str
    role: str
    x: float
    y: float
    z: float
    heading: float
    detail: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AlgorithmEvent:
    level: str
    stage: str
    message: str
    detail: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AlgorithmResult:
    commandId: str
    algorithmType: str
    status: str
    stage: str
    targetId: Optional[str]
    assignments: List[Assignment] = field(default_factory=list)
    events: List[AlgorithmEvent] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
