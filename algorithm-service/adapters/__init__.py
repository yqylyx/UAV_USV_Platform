"""Pure Python adapters for legacy UAV/USV algorithms."""

from .capture_adapter import probe_capture_core_step, run_capture_once
from .escort_adapter import run_escort_once
from .models import (
    AlgorithmEvent,
    AlgorithmRequest,
    AlgorithmResult,
    Assignment,
    Position,
    VehicleState,
)

__all__ = [
    "AlgorithmEvent",
    "AlgorithmRequest",
    "AlgorithmResult",
    "Assignment",
    "Position",
    "VehicleState",
    "probe_capture_core_step",
    "run_capture_once",
    "run_escort_once",
]
