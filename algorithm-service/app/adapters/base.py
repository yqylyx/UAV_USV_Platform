from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Dict, Sequence

from app.schemas import RuntimeFrame


class AlgorithmAdapter(ABC):
    code: str
    version = "1.0.0"

    def __init__(self, run_id: int, config: Dict[str, object] | None = None) -> None:
        self.run_id = int(run_id)
        self.config = config or {}
        self.sequence = 0
        self._stable_headings: Dict[str, float] = {}

    def stabilize_heading(
        self,
        code: str,
        previous: Sequence[float] | None,
        current: Sequence[float],
        fallback: float,
        max_turn_degrees: float,
    ) -> float:
        """Return a turn-rate-limited heading derived from actual motion.

        Vendor algorithms may change their desired waypoint sharply, while the
        final safety layer changes the executed displacement again.  Driving a
        Unity model with the vendor's instantaneous heading therefore makes it
        shake even when its real path is smooth.
        """
        old_heading = self._stable_headings.get(code, float(fallback) % 360.0)
        target_heading = old_heading
        if previous is not None:
            dx = float(current[0]) - float(previous[0])
            dy = float(current[1]) - float(previous[1])
            if math.hypot(dx, dy) >= 0.025:
                target_heading = math.degrees(math.atan2(dy, dx)) % 360.0
        delta = (target_heading - old_heading + 180.0) % 360.0 - 180.0
        limited = max(-max_turn_degrees, min(max_turn_degrees, delta))
        heading = (old_heading + limited) % 360.0
        self._stable_headings[code] = heading
        return heading

    @abstractmethod
    def step(self) -> RuntimeFrame:
        raise NotImplementedError

    def place_threat(self, x: float, y: float) -> None:
        raise ValueError(f"{self.code} does not support interactive threat placement")
