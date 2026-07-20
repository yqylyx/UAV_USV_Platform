"""HTTP request models for the first-stage algorithm service."""

from __future__ import annotations

import math
import uuid
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from adapters.models import AlgorithmRequest, Position, VehicleState


class ApiPosition(BaseModel):
    x: float
    y: float
    z: float
    heading: float = 0.0

    @field_validator("x", "y", "z", "heading")
    @classmethod
    def finite_number(cls, value: float) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("coordinate values must be finite numbers")
        return number


class ApiVehicle(BaseModel):
    vehicleId: str
    position: ApiPosition
    vehicleCode: Optional[str] = None

    @field_validator("vehicleId")
    @classmethod
    def non_empty_vehicle_id(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("vehicleId must not be empty")
        return value


class RunOnceRequest(BaseModel):
    commandId: str = Field(default_factory=lambda: f"http-{uuid.uuid4().hex}")
    algorithmType: Literal["CAPTURE", "ESCORT_DEFENSE"]
    targetId: Optional[str] = None
    targetPosition: Optional[ApiPosition] = None
    threatTargetId: Optional[str] = None
    threatPosition: Optional[ApiPosition] = None
    uavs: List[ApiVehicle] = Field(default_factory=list)
    usvs: List[ApiVehicle] = Field(default_factory=list)
    parameters: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("commandId")
    @classmethod
    def non_empty_command_id(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("commandId must not be empty")
        return value

    @model_validator(mode="after")
    def validate_required_algorithm_inputs(self) -> "RunOnceRequest":
        if not self.targetId or not self.targetId.strip():
            raise ValueError("targetId is required")
        if self.targetPosition is None:
            raise ValueError("targetPosition is required")
        if not self.uavs:
            raise ValueError("at least one UAV is required")
        if not self.usvs:
            raise ValueError("at least one USV is required")
        return self

    def to_adapter_request(self) -> AlgorithmRequest:
        return AlgorithmRequest(
            commandId=self.commandId,
            algorithmType=self.algorithmType,
            targetId=self.targetId,
            targetPosition=_to_position(self.targetPosition),
            threatTargetId=self.threatTargetId,
            threatPosition=_to_position(self.threatPosition),
            uavs=[_to_vehicle(vehicle) for vehicle in self.uavs],
            usvs=[_to_vehicle(vehicle) for vehicle in self.usvs],
            parameters=dict(self.parameters),
        )


def _to_position(position: Optional[ApiPosition]) -> Optional[Position]:
    if position is None:
        return None
    return Position(
        x=position.x,
        y=position.y,
        z=position.z,
        heading=position.heading,
    )


def _to_vehicle(vehicle: ApiVehicle) -> VehicleState:
    return VehicleState(
        vehicleId=vehicle.vehicleId,
        x=vehicle.position.x,
        y=vehicle.position.y,
        z=vehicle.position.z,
        heading=vehicle.position.heading,
        vehicleCode=vehicle.vehicleCode,
    )
