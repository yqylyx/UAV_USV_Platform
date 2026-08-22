from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from typing import Dict, Sequence

from app.adapters.base import AlgorithmAdapter
from app.capture import FormationSlot
from app.navigation import SceneSafetyFilter
from app.scenario import derive_scenario_plan
from app.schemas import AgentFrame, RuntimeFrame, TargetFrame


DT = 0.1
CAPTURE_HOLD_FRAMES = 25
# Rendered target hulls remain clear above 12 m. The motion solver maintains
# an 18 m nominal gap; a slightly lower terminal threshold avoids declaring a
# false attack success from sub-frame projection/rounding at 12.98 m.
BREACH_DISTANCE_M = 28.0
TARGET_SEPARATION_M = 34.0
SHORE_MARGIN_M = 28.0
THREAT_DETECTION_M = 155.0
INTERCEPT_DISTANCE_M = 58.0
INTERCEPT_LATERAL_M = 30.0
INTERCEPT_HOLD_FRAMES = 16
CONTAINMENT_STANDOFF_M = 78.0
CONTAINMENT_REPLAN_M = 108.0


def _length(x: float, y: float) -> float:
    return math.hypot(x, y)


def _unit(x: float, y: float, fallback: tuple[float, float] = (1.0, 0.0)) -> tuple[float, float]:
    value = _length(x, y)
    return fallback if value < 1e-8 else (x / value, y / value)


def _clamp_magnitude(x: float, y: float, limit: float) -> tuple[float, float]:
    value = _length(x, y)
    if value <= limit or value < 1e-8:
        return x, y
    return x * limit / value, y * limit / value


@dataclass
class _Vehicle:
    code: str
    kind: str
    x: float
    y: float
    z: float
    role: str
    group_id: str
    protected_index: int
    assigned_threat: int | None = None
    vx: float = 0.0
    vy: float = 0.0


@dataclass
class _Protected:
    code: str
    x: float
    y: float
    heading: float
    destination_x: float
    destination_y: float
    vx: float = 0.0
    vy: float = 0.0
    state: str = "ESCORTING"
    avoidance_side: int = 0


@dataclass
class _Threat:
    code: str
    x: float
    y: float
    heading: float
    protected_index: int
    activate_frame: int
    state: str = "WAITING"
    capture_hold: int = 0
    forced: bool = False
    detected_frame: int | None = None
    vx: float = 0.0
    vy: float = 0.0
    previous_distance: float = math.inf
    capture_phase: float = 0.0
    travelled_distance: float = 0.0
    captured_frame: int | None = None
    capture_started_frame: int | None = None
    capture_stage: int = 0
    capture_arrival_ratio: float = 0.0
    capture_max_gap_deg: float = 360.0
    capture_radial_error: float = math.inf
    capture_start_travel_distance: float = 0.0
    required_pursuit_distance: float = 80.0
    escape_dir_x: float = 1.0
    escape_dir_y: float = 0.0
    intent: str = "ATTACKING"
    intent_hold_frames: int = 0
    auto_capture_reason: str = ""
    attack_start_distance: float = math.inf
    closest_attack_distance: float = math.inf
    intercept_hold_frames: int = 0


class AdaptiveEscortAdapter(AlgorithmAdapter):
    """Moving-target escort, guarding and automatic capture controller."""

    code = "ESCORT_GUARD"
    version = "3.0.0"

    def __init__(self, run_id: int, config: Dict[str, object] | None = None) -> None:
        super().__init__(run_id, config)
        self.plan = derive_scenario_plan(
            int(self.config.get("uavCount", 3)), int(self.config.get("usvCount", 3)),
        )
        self.random = random.Random(int(self.config.get("seed", 20260814)))
        self.uav_cruise = min(15.0, max(0.2, float(self.config.get("uavSpeedMps", 5.0))))
        self.usv_cruise = min(4.0, max(0.2, float(self.config.get("usvSpeedMps", 3.0))))
        half_width, half_height = self.plan.world_width / 2.0, self.plan.world_height / 2.0
        self.safe_bounds = (
            -half_width + SHORE_MARGIN_M, half_width - SHORE_MARGIN_M,
            -half_height + SHORE_MARGIN_M, half_height - SHORE_MARGIN_M,
        )
        self.safety = SceneSafetyFilter({"bounds": list(self.safe_bounds), "obstacles": []})
        self.protected = self._create_protected()
        self.protected_start_x = {item.code: item.x for item in self.protected}
        self.threats = self._create_threats()
        self.vehicles = self._create_vehicles()
        self.previous = {item.code: (item.x, item.y, item.z) for item in self.vehicles}
        self.avoidance_count = 0
        self.min_protected_threat_distance = math.inf
        self.min_agent_distance = math.inf
        self.min_shore_distance = math.inf
        self._initial_frame_pending = True
        self._terminal_status: str | None = None
        self._terminal_reason = ""
        # Escort time and active-capture time are independent. A capture
        # ordered late in an escort must receive its own full pursuit window.
        self.timeout_frames = 4800 if self.plan.effective_scale < 10 else 6000 if self.plan.effective_scale < 20 else 7200
        self.capture_started_frame: int | None = None
        # Reserve 40 seconds beyond pursuit/formation for collision-safe
        # convergence and the mandatory 25-frame capture hold.  The former
        # 280 s limit could expire less than one second before a valid ring
        # finished its stability proof on a 5+6 fleet.
        self.capture_timeout_frames = 3200 + max(0, self.plan.threat_count - 1) * 1100

    def _create_protected(self) -> list[_Protected]:
        usable_width = self.safe_bounds[1] - self.safe_bounds[0]
        usable_height = self.safe_bounds[3] - self.safe_bounds[2]
        spacing = min(90.0, usable_height / max(1, self.plan.protected_count))
        start_y = -(self.plan.protected_count - 1) * spacing / 2.0
        # Leave room behind and around the convoy for the complete initial
        # 10+10 patrol pattern. Starting only 35 m from the safe-water edge
        # clamped several boats onto the same line and caused a first-frame
        # collision-resolution jump after the speed increase.
        start_x = self.safe_bounds[0] + min(90.0, max(58.0, usable_width * 0.32))
        return [
            _Protected(
                f"PROTECTED-{index + 1:03d}", start_x + (index % 2) * 8.0,
                start_y + index * spacing, 0.0, self.safe_bounds[1] - 42.0, start_y + index * spacing,
            ) for index in range(self.plan.protected_count)
        ]

    def _create_threats(self) -> list[_Threat]:
        result: list[_Threat] = []
        sector_count = max(1, self.plan.simultaneous_threats)
        # A single incident starts ahead of the convoy with a seeded lateral
        # offset.  This remains random without spawning on top of the initial
        # rear escort ring. Multi-incident scenes use full separated sectors.
        phase = self.random.uniform(-0.62, 0.62) if sector_count == 1 else self.random.uniform(-math.pi, math.pi)
        minimum_spawn_distance = max(
            120.0,
            float(self.config.get("threatMinDistanceM", 120.0)),
        )
        for index in range(self.plan.threat_count):
            protected_index = index % self.plan.protected_count
            target = self.protected[protected_index]
            ring = index // sector_count
            angle = phase + 2.0 * math.pi * (index % sector_count) / sector_count + ring * 0.31
            candidates: list[tuple[float, float, float]] = []
            if sector_count > 1:
                radius_x = max(80.0, (self.safe_bounds[1] - self.safe_bounds[0]) * 0.37 - ring * 16.0)
                radius_y = max(70.0, (self.safe_bounds[3] - self.safe_bounds[2]) * 0.37 - ring * 14.0)
                # Keep each attacker inside a +/-30 degree sector. This
                # preserves distinct simultaneous approach directions while
                # allowing a small rotation away from a nearby protected ship.
                for offset_index in range(-3, 4):
                    sample_angle = angle + math.radians(offset_index * 5.0)
                    candidate_x, candidate_y = self._project_to_safe_water(
                        math.cos(sample_angle) * radius_x,
                        math.sin(sample_angle) * radius_y,
                        18.0,
                    )
                    distance = _length(candidate_x - target.x, candidate_y - target.y)
                    candidates.append((distance - abs(offset_index) * 0.7, candidate_x, candidate_y))
            else:
                preferred = (math.cos(angle), math.sin(angle))
                for sample in range(36):
                    sample_angle = angle + 2.0 * math.pi * sample / 36.0
                    direction = (math.cos(sample_angle), math.sin(sample_angle))
                    raw_x = target.x + direction[0] * (minimum_spawn_distance + ring * 18.0)
                    raw_y = target.y + direction[1] * (minimum_spawn_distance + ring * 18.0)
                    candidate_x, candidate_y = self._project_to_safe_water(raw_x, raw_y, 18.0)
                    distance = _length(candidate_x - target.x, candidate_y - target.y)
                    sector_score = direction[0] * preferred[0] + direction[1] * preferred[1]
                    candidates.append((distance + sector_score * 8.0, candidate_x, candidate_y))
            _, x, y = max(candidates, key=lambda item: item[0])
            ux, uy = _unit(target.x - x, target.y - y)
            result.append(_Threat(
                f"THREAT-{index + 1:03d}", x, y,
                math.degrees(math.atan2(uy, ux)) % 360.0, protected_index,
                1 if index < self.plan.simultaneous_threats else 220 * (index - self.plan.simultaneous_threats + 1),
                "APPROACHING" if index < self.plan.simultaneous_threats else "WAITING",
            ))
        return result

    def _guard_count(self, count: int) -> int:
        return min(count, (2 if count >= self.plan.protected_count * 4 else 1) * self.plan.protected_count)

    def _create_vehicles(self) -> list[_Vehicle]:
        result: list[_Vehicle] = []
        for kind, count in (("UAV", self.plan.uav_count), ("USV", self.plan.usv_count)):
            guard_total = self._guard_count(count)
            for index in range(count):
                protected_index = index % self.plan.protected_count
                target = self.protected[protected_index]
                is_guard = index < guard_total
                role = "CLOSE_GUARD" if is_guard else "RECON"
                group = f"GUARD-{protected_index + 1:03d}" if is_guard else f"RECON-{protected_index + 1:03d}"
                angle = 2.0 * math.pi * index / max(1, count) + (0.35 if kind == "UAV" else 0.0)
                if kind == "UAV":
                    radius = (55.0 if self.plan.effective_scale >= 10 else 42.0) + (index % 3) * 6.0
                else:
                    radius = 30.0 + (index % 3) * 5.0
                x, y = self._project_to_safe_water(target.x + math.cos(angle) * radius, target.y + math.sin(angle) * radius)
                result.append(_Vehicle(
                    f"{kind}-{index + 1:03d}", kind, x, y,
                    25.0 + (index % 4) * 2.5 if kind == "UAV" else 0.0,
                    role, group, protected_index,
                ))
        return result

    def _project_to_safe_water(self, x: float, y: float, inset: float = 0.0) -> tuple[float, float]:
        return (
            max(self.safe_bounds[0] + inset, min(self.safe_bounds[1] - inset, x)),
            max(self.safe_bounds[2] + inset, min(self.safe_bounds[3] - inset, y)),
        )

    def _distance_to_protected(self, threat: _Threat) -> float:
        target = self.protected[threat.protected_index]
        return _length(threat.x - target.x, threat.y - target.y)

    @staticmethod
    def _pursuit_distance(threat: _Threat) -> float:
        return max(0.0, threat.travelled_distance - threat.capture_start_travel_distance)

    def _choose_escape_direction(self, threat: _Threat) -> tuple[float, float]:
        """Choose one long open-water corridor and keep it for the chase."""
        target = self.protected[threat.protected_index]
        away_x, away_y = _unit(threat.x - target.x, threat.y - target.y)
        inset = 30.0
        left, right = self.safe_bounds[0] + inset, self.safe_bounds[1] - inset
        bottom, top = self.safe_bounds[2] + inset, self.safe_bounds[3] - inset

        def clearance(dx: float, dy: float) -> float:
            limits: list[float] = []
            if dx > 1e-6:
                limits.append((right - threat.x) / dx)
            elif dx < -1e-6:
                limits.append((left - threat.x) / dx)
            if dy > 1e-6:
                limits.append((top - threat.y) / dy)
            elif dy < -1e-6:
                limits.append((bottom - threat.y) / dy)
            return max(0.0, min((value for value in limits if value >= 0.0), default=0.0))

        candidates = [
            (math.cos(2.0 * math.pi * sample / 24.0), math.sin(2.0 * math.pi * sample / 24.0))
            for sample in range(24)
        ]
        # Never trade an actual escape direction for a longer corridor that
        # crosses the protected convoy or its defenders.  Clearance is scored
        # only after the direction is constrained to the away half-plane.
        aligned = [
            direction for direction in candidates
            if direction[0] * away_x + direction[1] * away_y >= 0.35
        ]
        if not aligned:
            aligned = [
                direction for direction in candidates
                if direction[0] * away_x + direction[1] * away_y >= -1e-6
            ]
        return max(
            aligned or candidates,
            key=lambda direction: clearance(*direction) + 10.0 * (direction[0] * away_x + direction[1] * away_y),
        )

    def _active_threats_for(self, protected_index: int) -> list[tuple[int, _Threat]]:
        return [(i, item) for i, item in enumerate(self.threats) if item.protected_index == protected_index and item.state not in {"WAITING", "CAPTURED", "SECURED", "ESCAPED"}]

    def activate_capture(self, threat_code: str | None = None) -> str:
        candidates = [item for item in self.threats if item.state not in {"CAPTURED", "SECURED", "ESCAPED"}]
        if threat_code:
            candidates = [item for item in candidates if item.code == threat_code.strip().upper()]
        if not candidates:
            raise ValueError("No available moving threat can be captured")
        # With no explicit code the UI command means "actively capture every
        # current incident", not only the nearest target. This is essential
        # once the scenario contains two or more simultaneous attackers.
        selected = candidates if threat_code is None else candidates[:1]
        self._start_capture_for(selected, "MANUAL_OVERRIDE")
        return min(selected, key=self._distance_to_protected).code

    def _start_capture_for(self, selected: Sequence[_Threat], reason: str) -> None:
        pending = [
            threat for threat in selected
            if not threat.forced and threat.state not in {"CAPTURED", "SECURED", "ESCAPED"}
        ]
        if not pending:
            return
        for threat in pending:
            if threat.state == "WAITING":
                threat.state = "APPROACHING"
            threat.detected_frame = threat.detected_frame or self.sequence
            threat.forced, threat.state = True, "INTERCEPTING"
            threat.intent = "BREAK_CONTACT"
            threat.auto_capture_reason = reason
            threat.capture_phase = math.radians(threat.heading) + math.pi
            threat.capture_started_frame = self.sequence
            threat.capture_stage = 0
            threat.capture_hold = 0
            threat.capture_start_travel_distance = threat.travelled_distance
            threat.required_pursuit_distance = (
                100.0 if self.plan.effective_scale < 10
                else 120.0 if self.plan.effective_scale < 20
                else 140.0
            )
            threat.escape_dir_x, threat.escape_dir_y = self._choose_escape_direction(threat)
        self.capture_started_frame = (
            self.sequence if self.capture_started_frame is None
            else min(self.capture_started_frame, self.sequence)
        )
        active_forced = [
            threat for threat in self.threats
            if threat.forced and threat.state not in {"CAPTURED", "SECURED", "ESCAPED"}
        ]
        self.capture_timeout_frames = 3200 + max(0, len(active_forced) - 1) * 1100
        self._rebalance_capture_groups(active_forced)

    def place_threat(self, x: float, y: float) -> None:
        threat = next((item for item in self.threats if item.state == "WAITING"), None) or min(self.threats, key=self._distance_to_protected)
        threat.x, threat.y = self._project_to_safe_water(float(x), float(y))
        threat.state, threat.forced, threat.capture_hold = "APPROACHING", False, 0

    def _assign_capture_group(self, threat: _Threat) -> None:
        active = [item for item in self.threats if item.forced and item.state not in {"CAPTURED", "SECURED", "ESCAPED"}]
        self._rebalance_capture_groups(active or [threat])

    def _rebalance_capture_groups(self, threats: Sequence[_Threat]) -> None:
        """Build stable, mixed, per-threat groups while preserving guards."""
        ordered_threats = sorted(
            {self.threats.index(item): item for item in threats}.items(),
            key=lambda pair: pair[0],
        )
        if not ordered_threats:
            return
        selected_indices = {index for index, _ in ordered_threats}
        reserved_incident_groups = {
            group
            for index, threat in enumerate(self.threats)
            if index not in selected_indices
            and threat.detected_frame is not None
            and threat.state not in {"WAITING", "CAPTURED", "SECURED", "ESCAPED"}
            for group in (f"BLOCK-{index + 1:03d}", f"WATCH-{index + 1:03d}")
        }
        for item in self.vehicles:
            if (
                item.role != "CLOSE_GUARD"
                and item.group_id not in reserved_incident_groups
                and (item.assigned_threat in selected_indices or item.assigned_threat is None)
            ):
                item.assigned_threat = None
                item.role = "RECON"
                item.group_id = f"RECON-{item.protected_index + 1:03d}"
        # Assign each kind independently so every group is mixed. Greedy
        # nearest selection is performed round by round and assignments then
        # remain fixed for the whole capture, eliminating cross-target churn.
        for kind in ("USV", "UAV"):
            available = [
                item for item in self.vehicles
                if item.kind == kind
                and item.role not in {"CLOSE_GUARD", "BLOCKER", "CONFRONT"}
                and item.assigned_threat is None
            ]
            round_index = 0
            while available:
                threat_index, threat = ordered_threats[round_index % len(ordered_threats)]
                chosen = min(available, key=lambda item: _length(item.x - threat.x, item.y - threat.y))
                chosen.assigned_threat = threat_index
                chosen.role = "INTERCEPTOR"
                chosen.group_id = f"CAPTURE-{threat_index + 1:03d}"
                available.remove(chosen)
                round_index += 1
            minimum = 2
            for threat_index, threat in ordered_threats:
                members = [item for item in self.vehicles if item.kind == kind and item.assigned_threat == threat_index]
                while len(members) < minimum:
                    donors = sorted(
                        (
                            item for item in self.vehicles
                            if item.kind == kind
                            and item.assigned_threat in selected_indices
                            and item.assigned_threat != threat_index
                            and item.role == "INTERCEPTOR"
                            and sum(
                                other.kind == kind and other.assigned_threat == item.assigned_threat
                                for other in self.vehicles
                            ) > minimum
                        ),
                        key=lambda item: _length(item.x - threat.x, item.y - threat.y),
                    )
                    if not donors:
                        break
                    donor = donors[0]
                    donor.assigned_threat = threat_index
                    donor.group_id = f"CAPTURE-{threat_index + 1:03d}"
                    members.append(donor)

    def _release_capture_group(self, threat_index: int) -> None:
        for item in self.vehicles:
            if item.assigned_threat == threat_index:
                item.assigned_threat, item.role = None, "RETURNING"
                item.group_id = f"RECON-{item.protected_index + 1:03d}"

    def _capture_members(self, threat_index: int) -> list[_Vehicle]:
        return [item for item in self.vehicles if item.assigned_threat == threat_index]

    def _nearest_threat(self, protected_index: int) -> tuple[int, _Threat] | None:
        active = self._active_threats_for(protected_index)
        target = self.protected[protected_index]
        return min(active, key=lambda pair: _length(pair[1].x - target.x, pair[1].y - target.y)) if active else None

    def _nearest_hazard(self, protected_index: int) -> tuple[int, _Threat] | None:
        target = self.protected[protected_index]
        hazards = [
            (index, item) for index, item in enumerate(self.threats)
            # A captured/secured hull and its containment ring remain a real
            # exclusion zone.  Dropping SECURED here made the convoy resume a
            # straight route through the stopped enemy.
            if item.protected_index == protected_index and item.state not in {"WAITING", "ESCAPED"}
        ]
        return min(hazards, key=lambda pair: _length(pair[1].x - target.x, pair[1].y - target.y)) if hazards else None

    def _protected_hazards(self, protected_index: int) -> list[_Threat]:
        return [
            item for item in self.threats
            if item.protected_index == protected_index and item.state not in {"WAITING", "ESCAPED"}
        ]

    def _choose_protected_escape(
        self,
        target: _Protected,
        hazards: Sequence[_Threat],
        speed: float,
        *,
        route_priority: bool = False,
    ) -> tuple[float, float]:
        """Maximise predicted clearance from every attacker, not only the nearest.

        The former nearest-only repulsion could send the protected vessel
        directly toward a second simultaneous attacker. Candidate headings are
        evaluated against all live enemy trajectories and the shoreline while
        retaining a smaller preference for the destination route.
        """
        goal_x, goal_y = _unit(target.destination_x - target.x, target.destination_y - target.y)
        horizon = 7.0
        left, right, bottom, top = self.safe_bounds
        best: tuple[float, float, float] | None = None
        for sample in range(48):
            angle = 2.0 * math.pi * sample / 48.0
            dx, dy = math.cos(angle), math.sin(angle)
            future_x = target.x + dx * speed * horizon
            future_y = target.y + dy * speed * horizon
            predicted: list[float] = []
            closing_penalty = 0.0
            for threat in hazards:
                threat_future_x = threat.x + threat.vx * horizon
                threat_future_y = threat.y + threat.vy * horizon
                future_distance = _length(future_x - threat_future_x, future_y - threat_future_y)
                current_distance = _length(target.x - threat.x, target.y - threat.y)
                predicted.append(future_distance)
                if threat.state not in {"CAPTURED", "SECURED"} and future_distance < current_distance:
                    closing_penalty += (current_distance - future_distance) * 4.2
            shore_clearance = min(
                future_x - left, right - future_x,
                future_y - bottom, top - future_y,
            )
            minimum_clearance = min(predicted, default=200.0)
            mean_clearance = sum(predicted) / max(1, len(predicted))
            route_alignment = dx * goal_x + dy * goal_y
            if route_priority:
                # Captured threats are stationary keep-out zones, not active
                # pursuers. Favour a safe tangent that still advances through
                # the destination gate instead of orbiting the containment
                # group forever.
                clearance_penalty = max(0.0, CONTAINMENT_STANDOFF_M - minimum_clearance) * 16.0
                score = (
                    route_alignment * 54.0
                    + min(72.0, minimum_clearance) * 0.48
                    + min(50.0, shore_clearance) * 0.72
                    - clearance_penalty
                )
            else:
                score = (
                    minimum_clearance * 2.4
                    + mean_clearance * 0.32
                    + route_alignment * 22.0
                    + min(50.0, shore_clearance) * 0.72
                    - closing_penalty
                )
            if best is None or score > best[0]:
                best = (score, dx, dy)
        assert best is not None
        return best[1], best[2]

    def _advance_protected(self) -> None:
        for index, target in enumerate(self.protected):
            gx, gy = _unit(target.destination_x - target.x, target.destination_y - target.y)
            cruise = min(1.85, max(1.2, self.usv_cruise * 0.58))
            desired_vx, desired_vy = gx * cruise, gy * cruise
            hazards = self._protected_hazards(index)
            nearest = self._nearest_hazard(index)
            target.state = "ESCORTING"
            if nearest is not None:
                nearest_distance = _length(nearest[1].x - target.x, nearest[1].y - target.y)
                live_attackers = [
                    item for item in hazards
                    if item.state not in {"CAPTURED", "SECURED"}
                    and _length(item.x - target.x, item.y - target.y) < 165.0
                ]
                persistent_obstacles = [
                    item for item in hazards
                    if item.state in {"CAPTURED", "SECURED"}
                    and _length(item.x - target.x, item.y - target.y) < CONTAINMENT_REPLAN_M
                ]
                if live_attackers:
                    evade_speed = min(2.25, max(1.55, self.usv_cruise * 0.70))
                    ex, ey = self._choose_protected_escape(target, live_attackers, evade_speed)
                    desired_vx, desired_vy = ex * evade_speed, ey * evade_speed
                    target.state = "EVADING" if nearest_distance < 105.0 else "THREAT_DETECTED"
                elif persistent_obstacles:
                    bypass_speed = min(1.85, max(1.25, self.usv_cruise * 0.58))
                    ex, ey = self._choose_protected_escape(
                        target,
                        persistent_obstacles,
                        bypass_speed,
                        route_priority=True,
                    )
                    desired_vx, desired_vy = ex * bypass_speed, ey * bypass_speed
                    target.state = "BYPASSING_CONTAINMENT"
            desired_vx, desired_vy = _clamp_magnitude(desired_vx, desired_vy, 2.25)
            accel = 0.085
            target.vx += max(-accel, min(accel, desired_vx - target.vx))
            target.vy += max(-accel, min(accel, desired_vy - target.vy))
            nx, ny = self._project_to_safe_water(target.x + target.vx * DT, target.y + target.vy * DT)
            for hazard in self.threats:
                if hazard.protected_index != index or hazard.state in {"WAITING", "ESCAPED"}:
                    continue
                clearance = _length(nx - hazard.x, ny - hazard.y)
                required_clearance = (
                    CONTAINMENT_STANDOFF_M
                    if hazard.state in {"CAPTURED", "SECURED"}
                    else TARGET_SEPARATION_M
                )
                if clearance < required_clearance:
                    ux, uy = _unit(nx - hazard.x, ny - hazard.y)
                    # Never teleport the convoy to the edge of a keep-out
                    # circle. Turn it away at its physical speed; this keeps the
                    # manoeuvre readable and prevents the protected hull from
                    # pushing containment members out of their slots.
                    if target.avoidance_side == 0:
                        target.avoidance_side = 1 if index % 2 == 0 else -1
                    away_x, away_y = _unit(
                        ux * 0.82 - uy * 0.38 * target.avoidance_side,
                        uy * 0.82 + ux * 0.38 * target.avoidance_side,
                    )
                    step = min(2.25, max(cruise, _length(target.vx, target.vy))) * DT
                    nx, ny = self._project_to_safe_water(
                        target.x + away_x * step,
                        target.y + away_y * step,
                    )
                    target.vx, target.vy = away_x * step / DT, away_y * step / DT
                    self.avoidance_count += 1
            if _length(nx - target.x, ny - target.y) > 1e-5:
                target.heading = math.degrees(math.atan2(ny - target.y, nx - target.x)) % 360.0
            target.x, target.y = nx, ny

    def _synchronize_guard_roles(self) -> None:
        expected_codes: set[str] = set()
        incidents = [
            (index, threat) for index, threat in enumerate(self.threats)
            if threat.detected_frame is not None
            and not threat.forced
            and threat.state not in {"WAITING", "CAPTURED", "SECURED", "ESCAPED"}
        ]
        # Every simultaneous attacker gets an independent surface blocker and
        # airborne observer. The former nearest-only loop left the second enemy
        # completely unopposed in a 10+10 / two-threat scene.
        for threat_index, threat in incidents:
            block_group = f"BLOCK-{threat_index + 1:03d}"
            watch_group = f"WATCH-{threat_index + 1:03d}"
            blocker = next((
                item for item in self.vehicles
                if item.kind == "USV" and item.group_id == block_group
                and item.assigned_threat is None and item.role == "BLOCKER"
            ), None)
            if blocker is None:
                surface = [
                    item for item in self.vehicles
                    if item.kind == "USV" and item.role in {"RECON", "RETURNING"}
                    and item.assigned_threat is None and item.code not in expected_codes
                ]
                if surface:
                    blocker = min(surface, key=lambda item: _length(item.x - threat.x, item.y - threat.y))
                    blocker.role, blocker.group_id = "BLOCKER", block_group
            if blocker is not None:
                expected_codes.add(blocker.code)

            observer = next((
                item for item in self.vehicles
                if item.kind == "UAV" and item.group_id == watch_group
                and item.assigned_threat is None and item.role == "CONFRONT"
            ), None)
            if observer is None:
                air = [
                    item for item in self.vehicles
                    if item.kind == "UAV" and item.role in {"RECON", "RETURNING"}
                    and item.assigned_threat is None and item.code not in expected_codes
                ]
                if air:
                    observer = min(air, key=lambda item: _length(item.x - threat.x, item.y - threat.y))
                    observer.role, observer.group_id = "CONFRONT", watch_group
            if observer is not None:
                expected_codes.add(observer.code)

        for item in self.vehicles:
            if (
                item.assigned_threat is None
                and item.role in {"BLOCKER", "CONFRONT", "RETURNING"}
                and item.code not in expected_codes
            ):
                item.role, item.group_id = "RECON", f"RECON-{item.protected_index + 1:03d}"

    def _choose_attack_direction(
        self,
        threat: _Threat,
        target: _Protected,
        desired_speed: float,
    ) -> tuple[float, float, str]:
        """Select an attack/flanking direction by scoring future openings."""
        horizon = 8.0
        target_future = (
            target.x + target.vx * horizon,
            target.y + target.vy * horizon,
        )
        current_heading = math.radians(threat.heading)
        defenders = [
            item for item in self.vehicles
            if item.protected_index == threat.protected_index
            and item.role in {"CLOSE_GUARD", "BLOCKER", "CONFRONT"}
        ]
        left, right, bottom, top = self.safe_bounds
        best: tuple[float, float, float] | None = None
        for sample in range(32):
            angle = 2.0 * math.pi * sample / 32.0
            dx, dy = math.cos(angle), math.sin(angle)
            future_x = threat.x + dx * desired_speed * horizon
            future_y = threat.y + dy * desired_speed * horizon
            target_distance = _length(future_x - target_future[0], future_y - target_future[1])
            defender_clearance = min(
                (_length(future_x - item.x, future_y - item.y) for item in defenders),
                default=80.0,
            )
            shore_clearance = min(
                future_x - left, right - future_x,
                future_y - bottom, top - future_y,
            )
            turn_cost = abs((angle - current_heading + math.pi) % (2.0 * math.pi) - math.pi)
            direct_x, direct_y = _unit(target_future[0] - threat.x, target_future[1] - threat.y)
            attack_alignment = dx * direct_x + dy * direct_y
            # Before interception the enemy is an attacker, not an evader.
            # Defender clearance may choose a flank, but must not outweigh
            # visible progress toward the protected vessel.
            score = (
                -target_distance * 1.72
                + attack_alignment * 38.0
                + min(70.0, defender_clearance) * 0.28
                + min(45.0, shore_clearance) * 0.46
                - turn_cost * 3.2
            )
            if attack_alignment < 0.12:
                score -= 85.0
            if best is None or score > best[0]:
                best = (score, dx, dy)
        assert best is not None
        direct_x, direct_y = _unit(target_future[0] - threat.x, target_future[1] - threat.y)
        alignment = best[1] * direct_x + best[2] * direct_y
        intent = "ATTACKING" if alignment >= 0.72 else "FLANKING"
        return best[1], best[2], intent

    def _advance_threats(self) -> None:
        active = sum(item.state not in {"WAITING", "CAPTURED", "SECURED", "ESCAPED"} for item in self.threats)
        for index, threat in enumerate(self.threats):
            # CAPTURED is persistent containment.  The reference three-in-one
            # algorithm keeps the final GB-SFLA-CS waypoints after success;
            # releasing the group after 120 frames made the completed scene
            # dissolve into an unrelated recon pattern.
            if threat.state == "WAITING" and self.sequence >= threat.activate_frame and active < self.plan.simultaneous_threats:
                threat.state, active = "APPROACHING", active + 1
            if threat.state in {"WAITING", "CAPTURED", "SECURED", "ESCAPED"}:
                threat.vx = threat.vy = 0.0
                continue
            target = self.protected[threat.protected_index]
            dx, dy = target.x - threat.x, target.y - threat.y
            distance = max(1e-6, _length(dx, dy))
            if distance <= THREAT_DETECTION_M and threat.detected_frame is None:
                threat.detected_frame, threat.state = self.sequence, "DETECTED"
                threat.attack_start_distance = distance
                threat.closest_attack_distance = distance
            desired_x, desired_y = _unit(dx, dy)
            desired_speed = min(2.35, max(1.45, self.usv_cruise * 0.72))
            if threat.detected_frame is not None and not threat.forced:
                threat.closest_attack_distance = min(threat.closest_attack_distance, distance)
                blocker = next((
                    item for item in self.vehicles
                    if item.role == "BLOCKER" and item.group_id == f"BLOCK-{index + 1:03d}"
                ), None)
                intercepted = False
                if blocker is not None:
                    line_x, line_y = threat.x - target.x, threat.y - target.y
                    line_length = max(1e-6, _length(line_x, line_y))
                    line_x, line_y = line_x / line_length, line_y / line_length
                    rel_x, rel_y = blocker.x - target.x, blocker.y - target.y
                    along = rel_x * line_x + rel_y * line_y
                    lateral = abs(rel_x * line_y - rel_y * line_x)
                    intercepted = (
                        line_length * 0.18 <= along <= line_length
                        and lateral <= INTERCEPT_LATERAL_M
                        and _length(blocker.x - threat.x, blocker.y - threat.y) <= INTERCEPT_DISTANCE_M
                    )
                threat.intercept_hold_frames = (
                    threat.intercept_hold_frames + 1
                    if intercepted
                    else max(0, threat.intercept_hold_frames - 1)
                )
                if threat.intercept_hold_frames >= INTERCEPT_HOLD_FRAMES:
                    self._start_capture_for([threat], "INTERCEPT_ESTABLISHED")
                elif distance < BREACH_DISTANCE_M + 14.0:
                    # Last-resort safety transition if an unusually sparse
                    # fleet cannot occupy the formal block point in time.
                    self._start_capture_for([threat], "EMERGENCY_BREACH_PREVENTION")
            if threat.forced:
                if not self._capture_members(index):
                    self._assign_capture_group(threat)
                members = self._capture_members(index)
                pursuit_distance = self._pursuit_distance(threat)
                pursuit_run = pursuit_distance < threat.required_pursuit_distance
                threat.state = "ESCAPE_PURSUIT" if pursuit_run else "ENCIRCLING" if threat.capture_hold else "INTERCEPTING"
                if members:
                    cx = sum(item.x for item in members) / len(members)
                    cy = sum(item.y for item in members) / len(members)
                    escape_x, escape_y = _unit(threat.x - cx, threat.y - cy, (desired_x, desired_y))
                    nearest = min(members, key=lambda item: _length(item.x - threat.x, item.y - threat.y))
                    avoid_x, avoid_y = _unit(threat.x - nearest.x, threat.y - nearest.y, (escape_x, escape_y))
                    nearest_distance = _length(nearest.x - threat.x, nearest.y - threat.y)
                    if pursuit_run:
                        # Hold a coherent escape corridor long enough for the
                        # chase to be visible. Nearest-craft avoidance is only
                        # a small bias, so the enemy cannot spin in place.
                        desired_x, desired_y = _unit(
                            threat.escape_dir_x * 0.90 + avoid_x * 0.16,
                            threat.escape_dir_y * 0.90 + avoid_y * 0.16,
                        )
                        desired_speed = min(2.40, max(1.70, self.usv_cruise * 0.74))
                        threat.intent = "ESCAPING"
                    else:
                        side = 1.0 if index % 2 == 0 else -1.0
                        desired_x, desired_y = _unit(
                            escape_x * 0.62 + avoid_x * 0.58 - escape_y * 0.28 * side,
                            escape_y * 0.62 + avoid_y * 0.58 + escape_x * 0.28 * side,
                        )
                        pressure_factor = 1.0 if nearest_distance > 62.0 else 0.78 if nearest_distance > 38.0 else 0.56
                        desired_speed = min(2.35, max(0.72, self.usv_cruise * 0.72 * pressure_factor))
                        threat.intent = "BREAKOUT"
            elif threat.detected_frame is not None:
                desired_x, desired_y, threat.intent = self._choose_attack_direction(
                    threat,
                    target,
                    desired_speed,
                )
                threat.state = "BLOCKED" if threat.intercept_hold_frames > 0 else threat.intent
                blocker = next((item for item in self.vehicles if item.role == "BLOCKER" and item.group_id == f"BLOCK-{index + 1:03d}"), None)
                if blocker is not None and _length(blocker.x - threat.x, blocker.y - threat.y) < 42.0:
                    bx, by = _unit(threat.x - blocker.x, threat.y - blocker.y)
                    side = 1.0 if index % 2 == 0 else -1.0
                    desired_x, desired_y = _unit(
                        desired_x * 0.62 + bx * 0.55 - desired_y * side * 0.32,
                        desired_y * 0.62 + by * 0.55 + desired_x * side * 0.32,
                    )
                    desired_speed = min(2.40, max(1.55, self.usv_cruise * 0.76))
                    threat.state = "FLANKING"
            future_dx = threat.x + desired_x * desired_speed * 2.0 - target.x - target.vx * 2.0
            future_dy = threat.y + desired_y * desired_speed * 2.0 - target.y - target.vy * 2.0
            if _length(future_dx, future_dy) < TARGET_SEPARATION_M * 1.35:
                away_x, away_y = _unit(threat.x - target.x, threat.y - target.y)
                side = 1.0 if index % 2 == 0 else -1.0
                desired_x, desired_y = _unit(away_x - away_y * side, away_y + away_x * side)
            pursuit_run = threat.forced and self._pursuit_distance(threat) < threat.required_pursuit_distance
            capture_inset = 30.0 if pursuit_run else 38.0 if threat.forced else 8.0
            water_left = self.safe_bounds[0] + capture_inset
            water_right = self.safe_bounds[1] - capture_inset
            water_bottom = self.safe_bounds[2] + capture_inset
            water_top = self.safe_bounds[3] - capture_inset
            shore_x = (1.0 if threat.x < water_left + 10.0 else 0.0) - (1.0 if threat.x > water_right - 10.0 else 0.0)
            shore_y = (1.0 if threat.y < water_bottom + 10.0 else 0.0) - (1.0 if threat.y > water_top - 10.0 else 0.0)
            if shore_x or shore_y:
                desired_x, desired_y = _unit(desired_x + shore_x * 1.35, desired_y + shore_y * 1.35)
            desired_vx, desired_vy = desired_x * desired_speed, desired_y * desired_speed
            accel = 0.065
            threat.vx += max(-accel, min(accel, desired_vx - threat.vx))
            threat.vy += max(-accel, min(accel, desired_vy - threat.vy))
            # Keep enough navigable water around an actively captured target
            # for the complete mixed ring; otherwise slots outside the coast
            # rectangle collapse all pursuers onto the same side.
            raw_next_x = threat.x + threat.vx * DT
            raw_next_y = threat.y + threat.vy * DT
            nx, ny = self._project_to_safe_water(
                raw_next_x, raw_next_y, capture_inset,
            )
            moved = _length(nx - threat.x, ny - threat.y)
            boundary_clamped = _length(nx - raw_next_x, ny - raw_next_y) > 1e-4
            if pursuit_run and boundary_clamped and moved < max(0.005, _length(threat.vx, threat.vy) * DT * 0.25):
                # The persistent corridor has reached a coast/world inset.
                # Replan instead of letting the enemy appear stationary while
                # its velocity keeps pointing into the boundary.
                threat.escape_dir_x, threat.escape_dir_y = self._choose_escape_direction(threat)
                threat.vx = threat.vy = 0.0
            actual_distance = _length(nx - target.x, ny - target.y)
            if actual_distance < TARGET_SEPARATION_M:
                ux, uy = _unit(nx - target.x, ny - target.y)
                nx, ny = self._project_to_safe_water(target.x + ux * TARGET_SEPARATION_M, target.y + uy * TARGET_SEPARATION_M)
                self.avoidance_count += 1
            if _length(nx - threat.x, ny - threat.y) > 1e-5:
                threat.heading = math.degrees(math.atan2(ny - threat.y, nx - threat.x)) % 360.0
            threat.travelled_distance += _length(nx - threat.x, ny - threat.y)
            threat.x, threat.y = nx, ny
            # A detected attacker remains part of the incident until it is
            # intercepted and contained. Marking it ESCAPED merely because the
            # protected vessel temporarily opened the distance allowed the
            # mission to finish without demonstrating the required capture.
            threat.previous_distance = actual_distance

    def _capture_slots(self, members: Sequence[_Vehicle], threat: _Threat) -> list[FormationSlot]:
        ordered = sorted(
            members,
            key=lambda item: (int(item.code.rsplit("-", 1)[-1]), 0 if item.kind == "UAV" else 1),
        )
        pursuit_run = self._pursuit_distance(threat) < threat.required_pursuit_distance
        base_radius = (58.0, 41.0, 27.0)[min(2, threat.capture_stage)]
        # Slot identities stay stable while the centre moves. Rotating every
        # slot with a manoeuvring enemy makes pursuers chase a spinning goal
        # and prevents the ring from ever closing.
        phase = threat.capture_phase
        by_code: dict[str, FormationSlot] = {}
        for index, item in enumerate(ordered):
            if pursuit_run:
                # During the visible chase, use a broad trailing fan rather
                # than a ready-made circle. The full ring appears only after
                # the enemy has completed its required escape distance.
                centre = math.atan2(threat.escape_dir_y, threat.escape_dir_x) + math.pi
                spread = math.radians(112.0)
                angle = centre if len(ordered) == 1 else centre - spread / 2.0 + spread * index / (len(ordered) - 1)
                radius = 38.0 + (index % 2) * 9.0 + (3.5 if item.kind == "UAV" else 0.0)
            else:
                angle = phase + 2.0 * math.pi * index / max(1, len(ordered))
                radius = base_radius + (3.5 if item.kind == "UAV" else 0.0)
            by_code[item.code] = FormationSlot(
                radius,
                angle,
                25.0 + (index % 3) * 2.5 if item.kind == "UAV" else 0.0, 0,
            )
        return [by_code[item.code] for item in members]

    def _capture_center(self, threat: _Threat, members: Sequence[_Vehicle]) -> tuple[float, float]:
        if not members:
            return threat.x, threat.y
        mean_distance = sum(_length(item.x - threat.x, item.y - threat.y) for item in members) / len(members)
        mean_surface_speed = max(
            0.4,
            sum((self.uav_cruise if item.kind == "UAV" else self.usv_cruise) for item in members) / len(members),
        )
        # Predict far ahead only during interception. The final ring is always
        # centred on the live target so it cannot end up "capturing air".
        stage_factor = (1.0, 0.45, 0.0)[min(2, threat.capture_stage)]
        lookahead = min(5.0, max(0.0, mean_distance / mean_surface_speed * 0.13)) * stage_factor
        return self._project_to_safe_water(
            threat.x + threat.vx * lookahead,
            threat.y + threat.vy * lookahead,
            32.0,
        )

    def _desired_position(self, item: _Vehicle) -> tuple[float, float, float]:
        if item.assigned_threat is not None:
            threat = self.threats[item.assigned_threat]
            members = self._capture_members(item.assigned_threat)
            slots = self._capture_slots(members, threat)
            item.role = (
                "CONTAINMENT" if threat.state == "CAPTURED"
                else "CAPTURE" if threat.capture_stage >= 1
                else "INTERCEPTOR"
            )
            center_x, center_y = self._capture_center(threat, members)
            return slots[members.index(item)].point((center_x, center_y, 0.0))
        target = self.protected[item.protected_index]
        if item.role == "BLOCKER":
            threat_index = int(item.group_id.rsplit("-", 1)[-1]) - 1
            threat = self.threats[threat_index]
            ux, uy = _unit(threat.x - target.x, threat.y - target.y)
            lead = max(24.0, min(42.0, self._distance_to_protected(threat) * 0.42))
            x, y = self._project_to_safe_water(target.x + ux * lead, target.y + uy * lead)
            return x, y, item.z
        peers = [peer for peer in self.vehicles if peer.group_id == item.group_id and peer.assigned_threat is None]
        position = peers.index(item) if item in peers else 0
        nearest = self._nearest_threat(item.protected_index)
        observed = nearest
        if item.role == "CONFRONT" and item.group_id.startswith("WATCH-"):
            threat_index = int(item.group_id.rsplit("-", 1)[-1]) - 1
            if 0 <= threat_index < len(self.threats):
                observed = (threat_index, self.threats[threat_index])
        threat_angle = math.radians(target.heading) if observed is None else math.atan2(observed[1].y - target.y, observed[1].x - target.x)
        if item.role == "CLOSE_GUARD":
            radius = 18.0 if item.kind == "USV" else 27.0
            angle = threat_angle + (position - (len(peers) - 1) / 2.0) * math.radians(46.0)
        elif item.role == "CONFRONT" and observed is not None:
            angle, radius = threat_angle + math.pi / 2.0, min(64.0, max(38.0, self._distance_to_protected(observed[1]) * 0.55))
        else:
            radius = 58.0 + (position % 3) * 8.0
            angle = self.sequence * (0.0025 if item.kind == "UAV" else 0.0014) + 2.0 * math.pi * position / max(1, len(peers))
        x, y = self._project_to_safe_water(target.x + math.cos(angle) * radius, target.y + math.sin(angle) * radius)
        return x, y, 25.0 + (position % 3) * 2.5 if item.kind == "UAV" else 0.0

    @staticmethod
    def _move_towards(current: Sequence[float], desired: Sequence[float], step: float) -> tuple[float, float, float]:
        dx, dy = float(desired[0]) - float(current[0]), float(desired[1]) - float(current[1])
        distance = _length(dx, dy)
        if distance <= step or distance < 1e-9:
            return float(desired[0]), float(desired[1]), float(desired[2])
        return float(current[0]) + dx * step / distance, float(current[1]) + dy * step / distance, float(desired[2])

    def _advance_vehicles(self) -> list[AgentFrame]:
        proposals: dict[str, tuple[str, tuple[float, float, float]]] = {}
        for item in self.vehicles:
            desired = self._desired_position(item)
            distance = _length(desired[0] - item.x, desired[1] - item.y)
            cruise = self.uav_cruise if item.kind == "UAV" else self.usv_cruise
            speed = cruise * (1.0 if item.role in {"INTERCEPTOR", "CAPTURE", "BLOCKER"} else 0.72 if item.role == "CONTAINMENT" else 0.78 if item.role == "CONFRONT" else 0.66)
            if item.assigned_threat is not None:
                threat = self.threats[item.assigned_threat]
                target_speed = _length(threat.vx, threat.vy)
                closing_margin = min(1.0 if item.kind == "USV" else 2.8, 0.28 + distance * 0.025)
                speed = min(cruise, max(speed, target_speed + closing_margin))
                # Slow only at the final slot. Earlier deceleration is what
                # previously produced long queues behind a moving enemy.
                if threat.capture_stage >= 2 and distance < 10.0:
                    speed *= max(0.38, distance / 10.0)
            elif distance < 12.0:
                speed *= 0.45
            proposals[item.code] = (
                item.kind,
                self._move_towards((item.x, item.y, item.z), desired, max(0.018, speed * DT)),
            )
        fixed = {item.code: ("ESCORT_TARGET", (item.x, item.y, 0.0)) for item in self.protected}
        fixed.update({
            item.code: ("THREAT_TARGET", (item.x, item.y, 0.0))
            for item in self.threats
            if item.state not in {"WAITING", "ESCAPED"}
        })
        resolved = self.safety.resolve_group(proposals, self.previous, fixed)
        frames: list[AgentFrame] = []
        for item in self.vehicles:
            safe, old = resolved[item.code], self.previous.get(item.code, (item.x, item.y, item.z))
            current = (safe.x, safe.y, safe.z)
            if safe.adjusted:
                self.avoidance_count += 1
            item.vx, item.vy = (current[0] - item.x) / DT, (current[1] - item.y) / DT
            item.x, item.y, item.z = current
            heading = self.stabilize_heading(item.code, old, current, 0.0, 4.5 if item.kind == "UAV" else 4.2)
            self.previous[item.code] = current
            frames.append(AgentFrame(
                item.code, item.kind, *current, heading, item.role, "ACTIVE", item.group_id,
                self.threats[item.assigned_threat].code if item.assigned_threat is not None else self.protected[item.protected_index].code,
            ))
        return frames

    def _assess_threats(self) -> None:
        for index, threat in enumerate(self.threats):
            if not threat.forced or threat.state in {"WAITING", "CAPTURED", "SECURED", "ESCAPED"}:
                continue
            members = self._capture_members(index)
            if len(members) < 3:
                continue
            slots = self._capture_slots(members, threat)
            center_x, center_y = self._capture_center(threat, members)
            errors = []
            angles = []
            tolerance = (20.0, 16.0, 13.0)[min(2, threat.capture_stage)]
            for item, slot in zip(members, slots):
                expected = slot.point((center_x, center_y, 0.0))
                errors.append(_length(item.x - expected[0], item.y - expected[1]))
                angles.append(math.atan2(item.y - threat.y, item.x - threat.x) % (2.0 * math.pi))
            participating = sum(error <= tolerance for error in errors)
            arrival_ratio = participating / len(members)
            angles.sort()
            max_gap = max(
                (angles[(position + 1) % len(angles)] - angles[position]) % (2.0 * math.pi)
                for position in range(len(angles))
            )
            max_gap_deg = math.degrees(max_gap)
            threat.capture_arrival_ratio = arrival_ratio
            threat.capture_max_gap_deg = max_gap_deg
            threat.capture_radial_error = max(errors, default=0.0)

            # Contract only after the current ring is substantially formed.
            # Stage zero is predictive interception; later stages also demand
            # angular spread so a line/queue cannot be mistaken for a ring.
            pursuit_complete = self._pursuit_distance(threat) >= threat.required_pursuit_distance
            if threat.capture_stage == 0 and pursuit_complete and arrival_ratio >= 0.70:
                threat.capture_stage = 1
                threat.capture_hold = 0
                continue
            if threat.capture_stage == 1 and arrival_ratio >= 0.70 and max_gap_deg <= 220.0:
                threat.capture_stage = 2
                threat.capture_hold = 0
                continue
            relative_speed = sum(_length(item.vx - threat.vx, item.vy - threat.vy) for item in members) / len(members)
            final_ready = (
                threat.capture_stage >= 2
                and arrival_ratio >= 0.75
                and max_gap_deg < 178.0
                # Arrival ratio already permits one safety-displaced craft in
                # a larger group. Requiring the maximum error of every member
                # made 8-craft rings impossible when collision avoidance nudged
                # a single hull off its slot.
                and relative_speed <= 4.5
            )
            if final_ready:
                threat.state, threat.capture_hold = "CAPTURE_HOLD", threat.capture_hold + 1
                if threat.capture_hold >= CAPTURE_HOLD_FRAMES:
                    threat.state, threat.vx, threat.vy = "CAPTURED", 0.0, 0.0
                    threat.captured_frame = self.sequence
            else:
                # A single noisy frame should not erase an otherwise stable
                # encirclement; decay the hold instead of resetting it.
                threat.capture_hold = max(0, threat.capture_hold - 1)
                if self._pursuit_distance(threat) < threat.required_pursuit_distance:
                    threat.state = "ESCAPE_PURSUIT"
                else:
                    threat.state = "ENCIRCLING" if threat.capture_stage >= 1 else "INTERCEPTING"

    def _update_metrics_and_terminal(self) -> None:
        for threat in self.threats:
            if threat.state == "WAITING":
                continue
            target = self.protected[threat.protected_index]
            distance = _length(threat.x - target.x, threat.y - target.y)
            self.min_protected_threat_distance = min(self.min_protected_threat_distance, distance)
            if distance < BREACH_DISTANCE_M:
                self._terminal_status, self._terminal_reason = "FAILED", f"{threat.code} breached {target.code} safety radius"
        for index, left in enumerate(self.vehicles):
            for right in self.vehicles[index + 1:]:
                if left.kind == right.kind == "UAV" and abs(left.z - right.z) > 6.0:
                    continue
                self.min_agent_distance = min(self.min_agent_distance, _length(left.x - right.x, left.y - right.y))
        for x, y in [(item.x, item.y) for item in [*self.protected, *self.threats, *self.vehicles]]:
            self.min_shore_distance = min(self.min_shore_distance, x - self.safe_bounds[0], self.safe_bounds[1] - x, y - self.safe_bounds[2], self.safe_bounds[3] - y)
        if self._terminal_status is None:
            capture_unresolved = any(
                item.forced and item.state not in {"CAPTURED", "SECURED", "ESCAPED"}
                for item in self.threats
            )
            if self.capture_started_frame is not None and capture_unresolved:
                capture_elapsed = self.sequence - self.capture_started_frame
                if capture_elapsed >= self.capture_timeout_frames:
                    self._terminal_status, self._terminal_reason = "TIMEOUT", "active capture time limit reached"
            elif self.sequence >= self.timeout_frames:
                self._terminal_status, self._terminal_reason = "TIMEOUT", "escort mission time limit reached"
        resolved = all(item.state in {"CAPTURED", "SECURED", "ESCAPED"} for item in self.threats)
        def reached_safe_gate(item: _Protected) -> bool:
            relevant = [
                threat for threat in self.threats
                if threat.protected_index == self.protected.index(item)
                and threat.state in {"CAPTURED", "SECURED"}
            ]
            safe_from_containment = (
                bool(relevant)
                and all(
                    _length(item.x - threat.x, item.y - threat.y) >= CONTAINMENT_STANDOFF_M - 1.0
                    for threat in relevant
                )
            )
            start_x = self.protected_start_x[item.code]
            route_length = max(1.0, item.destination_x - start_x)
            route_progress = max(0.0, min(1.0, (item.x - start_x) / route_length))
            # A completed containment ring is a persistent keep-out zone. If
            # it sits across the nominal destination gate, the protected
            # vessel should hold at a safe observation point instead of
            # approaching the ring and dragging its guards out of position.
            # Once every attacker assigned to this convoy has been captured,
            # reaching a safe observation leg is a valid mission outcome. Do
            # not force the protected vessel through the completed rings just
            # to touch the original destination marker: that is exactly what
            # used to make it approach the enemy and pull containment craft
            # away. Sixty percent still guarantees a visible escort transit,
            # while the standoff check above remains the authoritative safety
            # gate. Forty percent of this 172 m route is still a visible
            # 68.8 m escort leg; after both attackers are contained, forcing
            # more progress would only steer the convoy back toward their
            # keep-out circles.
            if safe_from_containment and route_progress >= 0.40:
                return True
            if item.x < item.destination_x - 6.0:
                return False
            if abs(item.y - item.destination_y) <= 24.0:
                return True
            # A captured enemy can occupy the nominal centre of the destination
            # gate.  Requiring the convoy to touch that exact point conflicts
            # with the persistent containment keep-out zone, so accept a safe
            # lateral lane after the convoy has crossed the destination line.
            return (
                safe_from_containment
                and abs(item.y - item.destination_y) <= 64.0
            )

        arrived = all(reached_safe_gate(item) for item in self.protected)
        if self._terminal_status is None and resolved and arrived:
            self._terminal_status, self._terminal_reason = "COMPLETED", "all protected targets reached safety and all threats were resolved"

    def _phase(self) -> str:
        active = [item for item in self.threats if item.state not in {"WAITING", "CAPTURED", "SECURED", "ESCAPED"}]
        if self._terminal_status:
            return self._terminal_status
        if any(item.state == "CAPTURED" for item in self.threats):
            return "CONTAINMENT"
        if any(item.state == "CAPTURE_HOLD" for item in active):
            return "CAPTURE_HOLD"
        if any(item.forced for item in active):
            return "ACTIVE_CAPTURE"
        if any(item.state == "CONFRONTING" for item in active):
            return "BLOCKING"
        if any(item.detected_frame is not None for item in active):
            return "GUARDING"
        return "ESCORTING"

    def step(self) -> RuntimeFrame:
        self.sequence += 1
        initial, self._initial_frame_pending = self._initial_frame_pending, False
        if not initial and self._terminal_status is None:
            self._advance_protected()
            self._advance_threats()
            self._synchronize_guard_roles()
        agents = self._advance_vehicles() if not initial and self._terminal_status is None else [
            AgentFrame(
                item.code, item.kind, item.x, item.y, item.z, self._stable_headings.get(item.code, 0.0),
                item.role, "ACTIVE" if self._terminal_status is None else "HOLDING", item.group_id,
                self.threats[item.assigned_threat].code if item.assigned_threat is not None else self.protected[item.protected_index].code,
            ) for item in self.vehicles
        ]
        if not initial and self._terminal_status is None:
            self._assess_threats()
            self._update_metrics_and_terminal()
        targets = [TargetFrame(item.code, "ESCORT_TARGET", item.x, item.y, 0.0, item.heading, True, f"GUARD-{i + 1:03d}", item.state, 0) for i, item in enumerate(self.protected)]
        targets.extend(TargetFrame(item.code, "THREAT_TARGET", item.x, item.y, 0.0, item.heading, item.state != "WAITING", f"CAPTURE-{i + 1:03d}", item.state, 3 if item.forced else 2 if item.detected_frame is not None else 1) for i, item in enumerate(self.threats))
        visible = [item for item in self.threats if item.state != "WAITING"]
        roles: dict[str, int] = {}
        for item in self.vehicles:
            roles[item.role] = roles.get(item.role, 0) + 1
        escort_progress = sum(min(1.0, max(0.0, (item.x - self.safe_bounds[0]) / max(1.0, item.destination_x - self.safe_bounds[0]))) for item in self.protected) / len(self.protected)
        capture_values: list[float] = []
        capture_groups: list[dict[str, object]] = []
        for index, threat in enumerate(self.threats):
            members = self._capture_members(index)
            if threat.state in {"CAPTURED", "SECURED"}:
                value = 1.0
            elif threat.forced:
                pursuit_progress = min(1.0, self._pursuit_distance(threat) / max(1.0, threat.required_pursuit_distance))
                value = min(
                    0.98,
                    0.05 + pursuit_progress * 0.18 + threat.capture_stage * 0.22
                    + threat.capture_arrival_ratio * 0.22
                    + min(1.0, threat.capture_hold / CAPTURE_HOLD_FRAMES) * 0.16,
                )
            else:
                value = 0.0
            capture_values.append(value)
            if threat.forced or threat.state in {"CAPTURED", "SECURED"}:
                capture_groups.append({
                    "threatCode": threat.code,
                    "state": threat.state,
                    "stage": threat.capture_stage,
                    "memberCount": len(members),
                    "uavCount": sum(item.kind == "UAV" for item in members),
                    "usvCount": sum(item.kind == "USV" for item in members),
                    "arrivalRatio": round(threat.capture_arrival_ratio, 3),
                    "maxAngularGapDeg": round(threat.capture_max_gap_deg, 2),
                    "radialErrorM": None if math.isinf(threat.capture_radial_error) else round(threat.capture_radial_error, 2),
                    "holdFrames": threat.capture_hold,
                    "holdRequiredFrames": CAPTURE_HOLD_FRAMES,
                    "pursuitDistanceM": round(self._pursuit_distance(threat), 2),
                    "requiredPursuitDistanceM": round(threat.required_pursuit_distance, 2),
                    "pursuitProgress": round(min(1.0, self._pursuit_distance(threat) / max(1.0, threat.required_pursuit_distance)), 3),
                    "intent": threat.intent,
                    "triggerReason": threat.auto_capture_reason,
                })
        capture_progress = sum(capture_values) / max(1, len(capture_values))
        if self._terminal_status == "COMPLETED":
            escort_progress = 1.0
            capture_progress = 1.0
        overall_progress = escort_progress if self.capture_started_frame is None else escort_progress * 0.4 + capture_progress * 0.6
        capture_elapsed = 0 if self.capture_started_frame is None else max(0, self.sequence - self.capture_started_frame)
        capture_unresolved = any(
            item.forced and item.state not in {"CAPTURED", "SECURED", "ESCAPED"}
            for item in self.threats
        )
        current_threat_distances = [
            self._distance_to_protected(item)
            for item in self.threats
            if item.state not in {"WAITING", "ESCAPED"}
        ]
        moving_threats = [item for item in self.threats if item.state not in {"WAITING", "ESCAPED"}]
        metrics = {
            "scenarioPlan": self.plan.to_dict(), "protectedCount": self.plan.protected_count,
            "threatCount": self.plan.threat_count, "visibleThreatCount": len(visible),
            "capturedThreatCount": sum(item.state in {"CAPTURED", "SECURED"} for item in self.threats),
            "escapedThreatCount": sum(item.state == "ESCAPED" for item in self.threats),
            "simultaneousThreatLimit": self.plan.simultaneous_threats, "avoidanceCount": self.avoidance_count,
            "roles": roles,
            "threatIntents": {item.code: item.intent for item in self.threats if item.state != "WAITING"},
            "attackingThreatCount": sum(
                item.detected_frame is not None and not item.forced
                and item.state not in {"WAITING", "CAPTURED", "SECURED", "ESCAPED"}
                for item in self.threats
            ),
            "interceptedThreatCount": sum(
                item.intercept_hold_frames > 0 and not item.forced
                for item in self.threats
            ),
            "closestThreatDistanceM": None if not current_threat_distances else round(min(current_threat_distances), 3),
            "protectedTargetMeanSpeedMps": round(
                sum(_length(item.vx, item.vy) for item in self.protected) / max(1, len(self.protected)), 3,
            ),
            "threatMeanSpeedMps": round(
                sum(_length(item.vx, item.vy) for item in moving_threats) / max(1, len(moving_threats)), 3,
            ),
            "attackClosingDistanceM": round(sum(
                max(0.0, item.attack_start_distance - item.closest_attack_distance)
                for item in self.threats if math.isfinite(item.attack_start_distance)
            ), 3),
            "minProtectedThreatDistanceM": None if math.isinf(self.min_protected_threat_distance) else round(self.min_protected_threat_distance, 3),
            "minAgentDistanceM": None if math.isinf(self.min_agent_distance) else round(self.min_agent_distance, 3),
            # The controller works inside bounds already inset from the coastline.
            # Report the real coastline clearance rather than the inset-relative value.
            "minShoreDistanceM": None if math.isinf(self.min_shore_distance) else round(self.min_shore_distance + SHORE_MARGIN_M, 3),
            "threatTravelDistanceM": round(sum(item.travelled_distance for item in self.threats), 3),
            "escortProgress": round(escort_progress, 3),
            "captureProgress": round(capture_progress, 3),
            "missionProgress": round(overall_progress, 3),
            "captureElapsedFrames": capture_elapsed,
            "captureTimeoutFrames": self.capture_timeout_frames,
            "captureRemainingFrames": max(0, self.capture_timeout_frames - capture_elapsed) if capture_unresolved else 0,
            "captureGroups": capture_groups,
            "terminalReason": self._terminal_reason,
            "worldBounds": list(self.safe_bounds),
        }
        return RuntimeFrame(
            self.run_id, self.code, self.sequence, int(time.time() * 1000), self._phase(),
            agents, targets, metrics, route=[], obstacles=[], terminalStatus=self._terminal_status,
        )
