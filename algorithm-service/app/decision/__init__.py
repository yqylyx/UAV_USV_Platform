"""Explainable tactical decision primitives shared by realtime adapters."""

from .dynamic_assignment import (
    AssignmentChange,
    AssignmentResult,
    DecisionAgent,
    DecisionTarget,
    DynamicTaskAllocator,
)

__all__ = [
    "AssignmentChange",
    "AssignmentResult",
    "DecisionAgent",
    "DecisionTarget",
    "DynamicTaskAllocator",
]
