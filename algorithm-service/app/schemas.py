from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


@dataclass
class AgentFrame:
    code: str
    type: str
    x: float
    y: float
    z: float
    heading: float
    role: str
    status: str = "ACTIVE"


@dataclass
class TargetFrame:
    code: str
    type: str
    x: float
    y: float
    z: float
    heading: float = 0.0
    visible: bool = True


@dataclass
class RuntimeFrame:
    runId: int
    algorithmCode: str
    sequence: int
    timestamp: int
    phase: str
    agents: List[AgentFrame]
    targets: List[TargetFrame]
    metrics: Dict[str, object] = field(default_factory=dict)
    route: List[List[float]] = field(default_factory=list)
    obstacles: List[Dict[str, object]] = field(default_factory=list)
    terminalStatus: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)
