from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Mapping, Sequence

import numpy as np
from scipy.optimize import linear_sum_assignment


@dataclass(frozen=True)
class DecisionAgent:
    code: str
    kind: str
    x: float
    y: float
    speed_mps: float
    heading_deg: float
    maximum_speed_mps: float
    current_target: str | None = None
    role: str = "INTERCEPTOR"
    stalled_frames: int = 0


@dataclass(frozen=True)
class DecisionTarget:
    code: str
    x: float
    y: float
    vx: float
    vy: float
    urgency: float = 0.5
    gap_bearing_deg: float | None = None
    gap_deg: float = 360.0
    locked: bool = False


@dataclass(frozen=True)
class AssignmentChange:
    agent_code: str
    kind: str
    previous_target: str | None
    target: str
    reason: str
    previous_eta_sec: float | None
    intercept_eta_sec: float


@dataclass
class AssignmentResult:
    assignments: dict[str, str]
    changes: list[AssignmentChange] = field(default_factory=list)
    evaluated: bool = False
    accepted: bool = False
    reason: str = "UNCHANGED"
    current_cost: float = 0.0
    proposed_cost: float = 0.0
    improvement_ratio: float = 0.0


class DynamicTaskAllocator:
    """Capacity-constrained predictive allocator with anti-churn hysteresis.

    It deliberately runs slower than motion control.  A target/role decision
    should remain legible long enough to be executed, while urgent trajectory
    changes can still trigger an immediate evaluation.
    """

    def __init__(
        self,
        *,
        evaluation_interval_frames: int = 10,
        minimum_improvement_ratio: float = 0.12,
        confirmation_cycles: int = 2,
        cooldown_frames: int = 30,
        switch_penalty_seconds: float = 2.4,
        stalled_override_frames: int = 20,
    ) -> None:
        self.evaluation_interval_frames = max(1, evaluation_interval_frames)
        self.minimum_improvement_ratio = max(0.0, minimum_improvement_ratio)
        self.confirmation_cycles = max(1, confirmation_cycles)
        self.cooldown_frames = max(0, cooldown_frames)
        self.switch_penalty_seconds = max(0.0, switch_penalty_seconds)
        self.stalled_override_frames = max(1, stalled_override_frames)
        self.last_evaluation_frame = -10_000
        self._candidate_signature: tuple[tuple[str, str], ...] | None = None
        self._candidate_cycles = 0
        self._last_switch_frame: dict[str, int] = {}
        self.assignment_revision = 0
        self.reassignment_count = 0

    @staticmethod
    def _angle_error_deg(left: float, right: float) -> float:
        return abs((left - right + 180.0) % 360.0 - 180.0)

    def _base_cost(self, agent: DecisionAgent, target: DecisionTarget) -> tuple[float, float]:
        target_speed = math.hypot(target.vx, target.vy)
        closing_speed = max(0.35, agent.maximum_speed_mps + target_speed * 0.25)
        direct_distance = math.hypot(target.x - agent.x, target.y - agent.y)
        first_eta = direct_distance / closing_speed
        horizon = min(8.0, max(2.0, first_eta))
        predicted_x = target.x + target.vx * horizon
        predicted_y = target.y + target.vy * horizon
        dx, dy = predicted_x - agent.x, predicted_y - agent.y
        distance = math.hypot(dx, dy)
        eta = distance / closing_speed
        bearing = math.degrees(math.atan2(dy, dx)) % 360.0
        turn_cost = self._angle_error_deg(agent.heading_deg, bearing) / 180.0 * 1.4

        # When a real opening exists, craft already aligned with its bearing
        # are more useful to that incident.  The term is bounded so it cannot
        # override the exact per-target capacities supplied by the caller.
        gap_cost = 0.0
        if target.gap_bearing_deg is not None and target.gap_deg < 300.0:
            gap_cost = self._angle_error_deg(bearing, target.gap_bearing_deg) / 180.0
            gap_cost *= min(1.5, max(0.2, target.gap_deg / 90.0))

        urgency_credit = min(1.8, max(0.0, target.urgency) * 1.8)
        stalled_cost = (
            2.5
            if agent.current_target == target.code
            and agent.stalled_frames >= self.stalled_override_frames
            else 0.0
        )
        return max(0.01, eta + turn_cost + gap_cost + stalled_cost - urgency_credit), eta

    def _effective_cost(
        self,
        agent: DecisionAgent,
        target: DecisionTarget,
        frame: int,
    ) -> tuple[float, float]:
        cost, eta = self._base_cost(agent, target)
        if agent.current_target and agent.current_target != target.code:
            last_switch = self._last_switch_frame.get(agent.code, -10_000)
            if frame - last_switch < self.cooldown_frames:
                cost += 10_000.0
            else:
                cost += self.switch_penalty_seconds
        return cost, eta

    @staticmethod
    def _normalise_capacities(
        agents: Sequence[DecisionAgent],
        targets: Sequence[DecisionTarget],
        capacities: Mapping[str, Mapping[str, int]],
    ) -> dict[str, dict[str, int]]:
        result = {
            target.code: {
                kind: max(0, int(value))
                for kind, value in capacities.get(target.code, {}).items()
            }
            for target in targets
        }
        for kind in {agent.kind for agent in agents}:
            required = sum(item.get(kind, 0) for item in result.values())
            available = sum(agent.kind == kind for agent in agents)
            if required != available:
                raise ValueError(
                    f"capacity mismatch for {kind}: required={required}, available={available}"
                )
        return result

    def evaluate(
        self,
        agents: Sequence[DecisionAgent],
        targets: Sequence[DecisionTarget],
        capacities: Mapping[str, Mapping[str, int]],
        *,
        frame: int,
        force: bool = False,
    ) -> AssignmentResult:
        current = {
            agent.code: agent.current_target
            for agent in agents
            if agent.current_target is not None
        }
        if not targets or not agents:
            return AssignmentResult(dict(current), reason="NO_ACTIVE_DECISIONS")
        if not force and frame - self.last_evaluation_frame < self.evaluation_interval_frames:
            return AssignmentResult(dict(current), reason="EVALUATION_INTERVAL")
        self.last_evaluation_frame = frame
        normalised = self._normalise_capacities(agents, targets, capacities)
        target_by_code = {target.code: target for target in targets}
        proposed: dict[str, str] = {}
        eta_by_pair: dict[tuple[str, str], float] = {}

        for kind in sorted({agent.kind for agent in agents}):
            kind_agents = sorted(
                (agent for agent in agents if agent.kind == kind),
                key=lambda item: item.code,
            )
            slots: list[str] = []
            for target in sorted(targets, key=lambda item: item.code):
                slots.extend([target.code] * normalised[target.code].get(kind, 0))
            if len(slots) != len(kind_agents):
                raise ValueError(f"incomplete {kind} target slots")

            matrix = np.zeros((len(kind_agents), len(slots)), dtype=float)
            for row, agent in enumerate(kind_agents):
                for column, target_code in enumerate(slots):
                    target = target_by_code[target_code]
                    if target.locked and agent.current_target != target_code:
                        matrix[row, column] = 100_000.0
                        continue
                    cost, eta = self._effective_cost(agent, target, frame)
                    matrix[row, column] = cost + column * 1e-8 + row * 1e-10
                    eta_by_pair[(agent.code, target_code)] = eta
            rows, columns = linear_sum_assignment(matrix)
            for row, column in zip(rows, columns):
                proposed[kind_agents[int(row)].code] = slots[int(column)]

        if any(value is None for value in current.values()) or len(current) != len(agents):
            current = dict(proposed)
        signature = tuple(sorted(proposed.items()))
        if proposed == current:
            self._candidate_signature = None
            self._candidate_cycles = 0
            return AssignmentResult(
                dict(current), evaluated=True, reason="CURRENT_ASSIGNMENT_OPTIMAL",
            )

        agent_by_code = {agent.code: agent for agent in agents}
        current_cost = 0.0
        proposed_cost = 0.0
        emergency = False
        for agent in agents:
            proposed_target = target_by_code[proposed[agent.code]]
            proposed_cost += self._base_cost(agent, proposed_target)[0]
            current_target_code = current.get(agent.code)
            if current_target_code in target_by_code:
                current_cost += self._base_cost(agent, target_by_code[current_target_code])[0]
            else:
                current_cost += 100_000.0
            emergency = emergency or (
                proposed[agent.code] != current_target_code
                and agent.stalled_frames >= self.stalled_override_frames
            )
        improvement = max(0.0, (current_cost - proposed_cost) / max(1e-6, current_cost))
        worthwhile = improvement >= self.minimum_improvement_ratio or emergency
        if not worthwhile:
            self._candidate_signature = None
            self._candidate_cycles = 0
            return AssignmentResult(
                dict(current), evaluated=True, reason="INSUFFICIENT_IMPROVEMENT",
                current_cost=current_cost, proposed_cost=proposed_cost,
                improvement_ratio=improvement,
            )

        if signature == self._candidate_signature:
            self._candidate_cycles += 1
        else:
            self._candidate_signature = signature
            self._candidate_cycles = 1
        if not emergency and self._candidate_cycles < self.confirmation_cycles:
            return AssignmentResult(
                dict(current), evaluated=True, reason="AWAITING_CONFIRMATION",
                current_cost=current_cost, proposed_cost=proposed_cost,
                improvement_ratio=improvement,
            )

        changes: list[AssignmentChange] = []
        for code, target_code in proposed.items():
            previous = current.get(code)
            if previous == target_code:
                continue
            agent = agent_by_code[code]
            previous_eta = (
                None
                if previous not in target_by_code
                else self._base_cost(agent, target_by_code[previous])[1]
            )
            changes.append(AssignmentChange(
                agent_code=code,
                kind=agent.kind,
                previous_target=previous,
                target=target_code,
                reason="STALLED_RELIEF" if agent.stalled_frames >= self.stalled_override_frames else "PREDICTED_ETA_GAIN",
                previous_eta_sec=previous_eta,
                intercept_eta_sec=eta_by_pair[(code, target_code)],
            ))
            self._last_switch_frame[code] = frame

        self.assignment_revision += 1
        self.reassignment_count += len(changes)
        self._candidate_signature = None
        self._candidate_cycles = 0
        return AssignmentResult(
            assignments=proposed,
            changes=changes,
            evaluated=True,
            accepted=True,
            reason="STALLED_RELIEF" if emergency else "PREDICTED_ETA_GAIN",
            current_cost=current_cost,
            proposed_cost=proposed_cost,
            improvement_ratio=improvement,
        )
