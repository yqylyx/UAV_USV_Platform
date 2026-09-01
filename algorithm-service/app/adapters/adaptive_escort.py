from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from functools import lru_cache
from heapq import heappop, heappush
from typing import Dict, Sequence

from app.adapters.base import AlgorithmAdapter
from app.capture import (
    FormationSlot,
    RingMember,
    RingSlot,
    assess_canonical_ring,
    assess_containment,
    build_canonical_slots,
    maximum_capture_gap_deg,
)
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
CONVOY_TARGET_SPACING_M = 42.0
# Keep the square close to both protected hulls while preserving the rendered
# USV/escort-target clearance (5.2 + 7.3 + 1.4 = 13.9 m).
CONVOY_GUARD_MARGIN_M = 15.0
SHORE_MARGIN_M = 28.0
THREAT_DETECTION_M = 155.0
INTERCEPT_DISTANCE_M = 58.0
INTERCEPT_LATERAL_M = 30.0
INTERCEPT_HOLD_FRAMES = 16
URGENT_INTERCEPT_HOLD_FRAMES = 5
URGENT_TTI_SECONDS = 34.0
URGENT_DISTANCE_M = 105.0
CONTAINMENT_STANDOFF_M = 78.0
CONTAINMENT_REPLAN_M = 108.0
POST_CAPTURE_CONVOY_CLEARANCE_M = TARGET_SEPARATION_M + 8.0
POST_MISSION_SLOT_TOLERANCE_M = 7.5
POST_MISSION_STABLE_FRAMES = 12
POST_MISSION_RING_AVOIDANCE_M = TARGET_SEPARATION_M + 18.0
POST_MISSION_OUTER_GUARD_GAP_M = 22.0
POST_MISSION_ROUTE_ARRIVAL_M = 8.0
PROTECTED_SAFE_GATE_OFFSET_M = 6.0


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


def _square_formation_offsets(count: int, spacing: float) -> list[tuple[float, float]]:
    """Return centred, route-aligned slots for a compact protected convoy."""
    columns = max(1, math.ceil(math.sqrt(max(1, count))))
    rows = max(1, math.ceil(max(1, count) / columns))
    raw = [
        (
            (index // columns - (rows - 1) / 2.0) * spacing,
            (index % columns - (columns - 1) / 2.0) * spacing,
        )
        for index in range(max(1, count))
    ]
    mean_x = sum(item[0] for item in raw) / len(raw)
    mean_y = sum(item[1] for item in raw) / len(raw)
    return [(x - mean_x, y - mean_y) for x, y in raw]


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
    final_slot_angle: float | None = None


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
    intercept_stage_frames: int = 0
    last_retarget_frame: int = 0
    cruise_speed: float = 1.8
    maximum_speed: float = 2.8
    intercept_attempts: int = 0
    breach_until_frame: int = 0
    gap_filler_code: str = ""
    gap_center_angle: float = 0.0
    mission_stage: str = "ESCAPE"
    containment_stage_latched: bool = False
    containment_soft_failure_frames: int = 0


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
        self.seed = int(self.config.get("seed", 20260814))
        self.uav_cruise = min(15.0, max(0.2, float(self.config.get("uavSpeedMps", 5.0))))
        self.usv_cruise = min(4.0, max(0.2, float(self.config.get("usvSpeedMps", 3.0))))
        half_width, half_height = self.plan.world_width / 2.0, self.plan.world_height / 2.0
        self.safe_bounds = (
            -half_width + SHORE_MARGIN_M, half_width - SHORE_MARGIN_M,
            -half_height + SHORE_MARGIN_M, half_height - SHORE_MARGIN_M,
        )
        self.safety = SceneSafetyFilter({"bounds": list(self.safe_bounds), "obstacles": []})
        self.protected = self._create_protected()
        protected_center_x = sum(item.x for item in self.protected) / len(self.protected)
        protected_center_y = sum(item.y for item in self.protected) / len(self.protected)
        self._protected_formation_offsets = {
            item.code: (item.x - protected_center_x, item.y - protected_center_y)
            for item in self.protected
        }
        self._protected_start_positions = {
            item.code: (item.x, item.y)
            for item in self.protected
        }
        self.protected_start_x = {item.code: item.x for item in self.protected}
        self.threats = self._create_threats()
        self.vehicles = self._create_vehicles()
        initial_guards = sorted(
            (item for item in self.vehicles if item.role == "CLOSE_GUARD"),
            key=lambda item: (
                int(item.code.rsplit("-", 1)[-1]),
                0 if item.kind == "USV" else 1,
            ),
        )
        self._convoy_guard_slot_by_code = {
            item.code: position for position, item in enumerate(initial_guards)
        }
        self._separate_initial_response_craft()
        self.previous = {item.code: (item.x, item.y, item.z) for item in self.vehicles}
        self.avoidance_count = 0
        self.min_protected_threat_distance = math.inf
        self.min_agent_distance = math.inf
        self.min_shore_distance = math.inf
        self._initial_frame_pending = True
        self._terminal_status: str | None = None
        self._terminal_reason = ""
        self._terminal_blocker = "MISSION_IN_PROGRESS"
        self._protected_arrival_ready = False
        self._captured_rings_ready = False
        self._display_progress = 0.0
        self._display_escort_progress = 0.0
        self._reported_mission_stage = "ESCORTING"
        self._final_containment_consolidated = False
        self._ring_slots: dict[int, dict[str, RingSlot]] = {}
        self._ring_best_arrival: dict[int, float] = {}
        self._ring_stalled_frames: dict[int, int] = {}
        self._ring_replans: dict[int, int] = {}
        self._convoy_support_slot_by_code: dict[str, int] = {}
        self._convoy_support_goal_override_by_code: dict[str, tuple[float, float]] = {}
        self._convoy_support_route_by_code: dict[str, list[tuple[float, float]]] = {}
        self._convoy_support_route_cursor_by_code: dict[str, int] = {}
        self._convoy_support_route_replan_frame_by_code: dict[str, int] = {}
        self._convoy_support_swap_pairs: set[tuple[str, str]] = set()
        self._post_watch_threat_by_code: dict[str, int] = {}
        self._post_watch_angle_by_code: dict[str, float] = {}
        self._post_mission_initial_error_by_code: dict[str, float] = {}
        self._post_mission_formation_initialized = False
        self._post_mission_final_replan_done = False
        self._post_mission_best_maximum_error = math.inf
        self._post_mission_stalled_frames = 0
        self._post_mission_slot_replans = 0
        self._convoy_support_ready_frames = 0
        self.capture_started_frame: int | None = None
        self._parallel_response_enabled = bool(self.config.get(
            "parallelThreatResponse",
            self.plan.effective_scale >= 15
            and self.plan.realtime_tier == "PHASE_TWO_REALTIME",
        ))
        self._parallel_response_started = False

    def _create_protected(self) -> list[_Protected]:
        usable_width = self.safe_bounds[1] - self.safe_bounds[0]
        # Leave room behind and around the convoy for the complete initial
        # 10+10 patrol pattern. Starting only 35 m from the safe-water edge
        # clamped several boats onto the same line and caused a first-frame
        # collision-resolution jump after the speed increase.
        start_x = self.safe_bounds[0] + min(90.0, max(58.0, usable_width * 0.32))
        offsets = _square_formation_offsets(
            self.plan.protected_count,
            CONVOY_TARGET_SPACING_M,
        )
        destination_x = self.safe_bounds[1] - 42.0
        return [
            _Protected(
                f"PROTECTED-{index + 1:03d}", start_x + offsets[index][0],
                offsets[index][1], 0.0,
                destination_x + offsets[index][0], offsets[index][1],
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
                preserve_multi_sector = sector_count >= 3
                radius_x = max(
                    minimum_spawn_distance if preserve_multi_sector else 80.0,
                    (self.safe_bounds[1] - self.safe_bounds[0]) * 0.37 - ring * 16.0,
                )
                radius_y = max(
                    minimum_spawn_distance if preserve_multi_sector else 70.0,
                    (self.safe_bounds[3] - self.safe_bounds[2]) * 0.37 - ring * 14.0,
                )
                # Preserve the established +/-30 degree approach distribution.
                # Only widen one shoreline-constrained sector when every normal
                # candidate would spawn inside the 112 m guard area; globally
                # widening the distribution changed otherwise valid 10+10 and
                # 20+20 seeded attack profiles.
                for offset_index in range(-6, 7):
                    sample_angle = angle + math.radians(offset_index * 5.0)
                    intended_x, intended_y = math.cos(angle), math.sin(angle)
                    candidate_x, candidate_y = self._project_to_safe_water(
                        (target.x if preserve_multi_sector else 0.0)
                        + math.cos(sample_angle) * radius_x,
                        (target.y if preserve_multi_sector else 0.0)
                        + math.sin(sample_angle) * radius_y,
                        18.0,
                    )
                    distance = _length(candidate_x - target.x, candidate_y - target.y)
                    actual_x, actual_y = _unit(candidate_x - target.x, candidate_y - target.y)
                    angular_error = math.degrees(math.acos(max(
                        -1.0,
                        min(1.0, actual_x * intended_x + actual_y * intended_y),
                    )))
                    # Distance alone pulled multiple shoreline-projected
                    # attackers into the same long-water corridor. Penalise
                    # sector error so three advertised incidents remain
                    # visually distinct while still preferring open water.
                    candidates.append((
                        distance
                        - (angular_error * 4.0 if preserve_multi_sector else 0.0)
                        - abs(offset_index) * 0.7,
                        candidate_x,
                        candidate_y,
                    ))
                if max(
                    _length(candidate_x - target.x, candidate_y - target.y)
                    for _, candidate_x, candidate_y in candidates
                ) < 112.0:
                    for offset_index in (*range(-12, -6), *range(7, 13)):
                        sample_angle = angle + math.radians(offset_index * 5.0)
                        intended_x, intended_y = math.cos(angle), math.sin(angle)
                        candidate_x, candidate_y = self._project_to_safe_water(
                            (target.x if preserve_multi_sector else 0.0)
                            + math.cos(sample_angle) * radius_x,
                            (target.y if preserve_multi_sector else 0.0)
                            + math.sin(sample_angle) * radius_y,
                            18.0,
                        )
                        distance = _length(candidate_x - target.x, candidate_y - target.y)
                        actual_x, actual_y = _unit(candidate_x - target.x, candidate_y - target.y)
                        angular_error = math.degrees(math.acos(max(
                            -1.0,
                            min(1.0, actual_x * intended_x + actual_y * intended_y),
                        )))
                        candidates.append((
                            distance
                            - (angular_error * 4.0 if preserve_multi_sector else 0.0)
                            - abs(offset_index) * 0.7,
                            candidate_x,
                            candidate_y,
                        ))
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
            cruise_speed = self.random.uniform(1.5, 2.2)
            result.append(_Threat(
                f"THREAT-{index + 1:03d}", x, y,
                math.degrees(math.atan2(uy, ux)) % 360.0, protected_index,
                1 if index < self.plan.simultaneous_threats else 220 * (index - self.plan.simultaneous_threats + 1),
                "APPROACHING" if index < self.plan.simultaneous_threats else "WAITING",
                vx=ux * cruise_speed,
                vy=uy * cruise_speed,
                cruise_speed=cruise_speed,
            ))
        return result

    def _guard_count(self, count: int) -> int:
        desired = (
            4
            if self.plan.protected_count == 1 and self.plan.effective_scale >= 18
            else (2 if count >= self.plan.protected_count * 4 else 1)
            * self.plan.protected_count
        )
        # Parallel realtime capture reserves four craft of each kind per
        # threat. Never improve the close-guard picture by starving a ring.
        capture_reserve = (
            self.plan.threat_count * 4
            if self.plan.realtime_tier == "PHASE_TWO_REALTIME"
            else 0
        )
        available = max(self.plan.protected_count, count - capture_reserve)
        return min(count, max(self.plan.protected_count, min(desired, available)))

    def _create_vehicles(self) -> list[_Vehicle]:
        result: list[_Vehicle] = []
        for kind, count in (("UAV", self.plan.uav_count), ("USV", self.plan.usv_count)):
            guard_total = self._guard_count(count)
            for index in range(count):
                protected_index = index % self.plan.protected_count
                target = self.protected[protected_index]
                is_guard = index < guard_total
                role = "CLOSE_GUARD" if is_guard else "RECON"
                group = (
                    "CONVOY-GUARD"
                    if is_guard and len(self.protected) > 1
                    else f"GUARD-{protected_index + 1:03d}"
                    if is_guard
                    else f"RECON-{protected_index + 1:03d}"
                )
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
        guards = sorted(
            (item for item in result if item.role == "CLOSE_GUARD"),
            key=lambda item: (
                int(item.code.rsplit("-", 1)[-1]),
                0 if item.kind == "USV" else 1,
            ),
        )
        for position, guard in enumerate(guards):
            guard.x, guard.y = self._convoy_guard_point(position, len(guards))
        return result

    def _separate_initial_response_craft(self) -> None:
        """Resolve overlapping per-target patrol rings before frame one.

        Two protected vessels are deliberately close, so independently seeded
        patrol circles can intersect even though every circle is valid by
        itself.  Waiting for the per-frame motion limiter to separate those
        craft left some USV pairs only 1.2 m apart at startup and still below
        the 7 m acceptance floor ten frames later.  Keep the compact convoy
        guard square authoritative and globally project only the free response
        craft before their initial poses are published.
        """
        if len(self.protected) <= 1:
            return
        movable = [item for item in self.vehicles if item.role != "CLOSE_GUARD"]
        if not movable:
            return
        proposals = {
            item.code: (item.kind, (item.x, item.y, item.z))
            for item in movable
        }
        fixed = {
            item.code: (item.kind, (item.x, item.y, item.z))
            for item in self.vehicles
            if item.role == "CLOSE_GUARD"
        }
        fixed.update({
            item.code: ("ESCORT_TARGET", (item.x, item.y, 0.0))
            for item in self.protected
        })
        fixed.update({
            item.code: ("THREAT_TARGET", (item.x, item.y, 0.0))
            for item in self.threats
            if item.state != "WAITING"
        })
        resolved = self.safety.resolve_group(
            proposals,
            fixed=fixed,
            iterations=96,
        )
        for item in movable:
            safe = resolved[item.code]
            item.x, item.y, item.z = safe.x, safe.y, safe.z

    def _convoy_center(self) -> tuple[float, float]:
        return (
            sum(item.x for item in self.protected) / len(self.protected),
            sum(item.y for item in self.protected) / len(self.protected),
        )

    def _convoy_guard_point(self, position: int, count: int) -> tuple[float, float]:
        """Place close guards at evenly spaced points on one convoy square."""
        center_x, center_y = self._convoy_center()
        protected_extent = max(
            max(abs(offset[0]), abs(offset[1]))
            for offset in self._protected_formation_offsets.values()
        )
        half_extent = protected_extent + CONVOY_GUARD_MARGIN_M
        phase = 4.0 * position / max(1, count)
        if phase < 1.0:
            offset_x, offset_y = half_extent, -half_extent + 2.0 * half_extent * phase
        elif phase < 2.0:
            edge = phase - 1.0
            offset_x, offset_y = half_extent - 2.0 * half_extent * edge, half_extent
        elif phase < 3.0:
            edge = phase - 2.0
            offset_x, offset_y = -half_extent, half_extent - 2.0 * half_extent * edge
        else:
            edge = phase - 3.0
            offset_x, offset_y = -half_extent + 2.0 * half_extent * edge, -half_extent
        return self._project_to_safe_water(center_x + offset_x, center_y + offset_y)

    def _convoy_support_point(self, position: int, count: int) -> tuple[float, float]:
        """Place released responders on a second square around the convoy."""
        center_x, center_y = self._convoy_center()
        protected_extent = max(
            max(abs(offset[0]), abs(offset[1]))
            for offset in self._protected_formation_offsets.values()
        )
        inner_half_extent = protected_extent + CONVOY_GUARD_MARGIN_M
        # The perimeter is 8 * half_extent. Keep neighbouring 30+30 slots at
        # least 16 m apart while leaving a visible lane outside the close guard.
        half_extent = max(
            inner_half_extent + POST_MISSION_OUTER_GUARD_GAP_M,
            max(1, count) * 2.0,
        )
        current_clearances = {
            "LEFT": center_x - self.safe_bounds[0],
            "RIGHT": self.safe_bounds[1] - center_x,
            "BOTTOM": center_y - self.safe_bounds[2],
            "TOP": self.safe_bounds[3] - center_y,
        }
        blocked_edge, blocked_clearance = min(
            current_clearances.items(),
            key=lambda row: (row[1], row[0]),
        )
        if blocked_clearance < half_extent + 2.0 and count > 1:
            # The destination is intentionally close to the harbour shoreline.
            # A full outer edge there overlaps the close-guard square and is
            # physically unreachable. Use the other three sides at even spacing;
            # the shoreline closes the fourth side and both corner sentries stay.
            # SceneSafetyFilter reserves the rendered USV footprint (5.2 m)
            # inside its bounds. Keep nominal slots inside the same reachable
            # centreline instead of asking a hull to approach an impossible
            # one-metre shoreline inset.
            open_offset = max(0.0, blocked_clearance - 6.0)
            if blocked_edge == "RIGHT":
                vertices = [
                    (open_offset, half_extent),
                    (-half_extent, half_extent),
                    (-half_extent, -half_extent),
                    (open_offset, -half_extent),
                ]
            elif blocked_edge == "LEFT":
                vertices = [
                    (-open_offset, -half_extent),
                    (half_extent, -half_extent),
                    (half_extent, half_extent),
                    (-open_offset, half_extent),
                ]
            elif blocked_edge == "TOP":
                vertices = [
                    (-half_extent, open_offset),
                    (-half_extent, -half_extent),
                    (half_extent, -half_extent),
                    (half_extent, open_offset),
                ]
            else:
                vertices = [
                    (half_extent, -open_offset),
                    (half_extent, half_extent),
                    (-half_extent, half_extent),
                    (-half_extent, -open_offset),
                ]
            segment_lengths = [
                _length(
                    vertices[index + 1][0] - vertices[index][0],
                    vertices[index + 1][1] - vertices[index][1],
                )
                for index in range(3)
            ]
            perimeter_position = (
                sum(segment_lengths) * position / (count - 1)
            )
            offset_x, offset_y = vertices[-1]
            traversed = 0.0
            for index, segment_length in enumerate(segment_lengths):
                if perimeter_position > traversed + segment_length:
                    traversed += segment_length
                    continue
                ratio = (
                    0.0 if segment_length <= 1e-9
                    else (perimeter_position - traversed) / segment_length
                )
                offset_x = (
                    vertices[index][0]
                    + (vertices[index + 1][0] - vertices[index][0]) * ratio
                )
                offset_y = (
                    vertices[index][1]
                    + (vertices[index + 1][1] - vertices[index][1]) * ratio
                )
                break
            return self._project_to_safe_water(
                center_x + offset_x,
                center_y + offset_y,
                6.0,
            )
        phase = 4.0 * position / max(1, count)
        if phase < 1.0:
            offset_x, offset_y = half_extent, -half_extent + 2.0 * half_extent * phase
        elif phase < 2.0:
            edge = phase - 1.0
            offset_x, offset_y = half_extent - 2.0 * half_extent * edge, half_extent
        elif phase < 3.0:
            edge = phase - 2.0
            offset_x, offset_y = -half_extent, half_extent - 2.0 * half_extent * edge
        else:
            edge = phase - 3.0
            offset_x, offset_y = -half_extent + 2.0 * half_extent * edge, -half_extent
        return self._project_to_safe_water(
            center_x + offset_x,
            center_y + offset_y,
        )

    def _safe_convoy_support_point(
        self,
        position: int,
        count: int,
    ) -> tuple[float, float]:
        """Keep a convoy slot on its square while clearing captured rings."""
        nominal = self._convoy_support_point(position, count)
        obstacles = self._captured_return_obstacles()
        if not obstacles or all(
            _length(nominal[0] - x, nominal[1] - y) >= radius + 0.5
            for x, y, radius in obstacles
        ):
            return nominal

        candidates: list[tuple[float, float, float]] = []
        for center_x, center_y, radius in obstacles:
            for sample in range(72):
                angle = 2.0 * math.pi * sample / 72.0
                candidate = self._project_to_safe_water(
                    center_x + math.cos(angle) * (radius + 3.0),
                    center_y + math.sin(angle) * (radius + 3.0),
                    6.0,
                )
                if not all(
                    _length(candidate[0] - x, candidate[1] - y) >= other_radius + 0.5
                    for x, y, other_radius in obstacles
                ):
                    continue
                candidates.append((
                    _length(candidate[0] - nominal[0], candidate[1] - nominal[1]),
                    candidate[0],
                    candidate[1],
                ))
        if not candidates:
            return nominal
        _, x, y = min(candidates, key=lambda row: (row[0], row[1], row[2]))
        return x, y

    def _convoy_inner_escape_point(
        self,
        item: _Vehicle,
    ) -> tuple[float, float] | None:
        """Lead a recalled responder out of a moving close-guard square."""
        center_x, center_y = self._convoy_center()
        protected_extent = max(
            max(abs(offset[0]), abs(offset[1]))
            for offset in self._protected_formation_offsets.values()
        )
        inner_half_extent = protected_extent + CONVOY_GUARD_MARGIN_M
        relative_x = item.x - center_x
        relative_y = item.y - center_y
        if max(abs(relative_x), abs(relative_y)) >= inner_half_extent - 1.0:
            return None
        escape_extent = inner_half_extent + 9.0
        if abs(relative_x) >= abs(relative_y):
            side = 1.0 if relative_x >= 0.0 else -1.0
            return self._project_to_safe_water(
                center_x + side * escape_extent,
                item.y,
                6.0,
            )
        side = 1.0 if relative_y >= 0.0 else -1.0
        return self._project_to_safe_water(
            item.x,
            center_y + side * escape_extent,
            6.0,
        )

    def _convoy_support_members(self) -> list[_Vehicle]:
        return sorted(
            (item for item in self.vehicles if item.role == "CONVOY_SUPPORT"),
            key=lambda item: (
                self._convoy_support_slot_by_code.get(item.code, 10_000),
                int(item.code.rsplit("-", 1)[-1]),
                0 if item.kind == "USV" else 1,
            ),
        )

    def _convoy_reserve_members(self) -> list[_Vehicle]:
        return sorted(
            (item for item in self.vehicles if item.role == "CAPTURE_RESERVE"),
            key=lambda item: (
                int(item.code.rsplit("-", 1)[-1]),
                0 if item.kind == "USV" else 1,
            ),
        )

    def _swap_enclosed_surplus_with_guards(self) -> None:
        """Move an enclosed reserve into the guard line without crossing it."""
        center_x, center_y = self._convoy_center()
        protected_extent = max(
            max(abs(offset[0]), abs(offset[1]))
            for offset in self._protected_formation_offsets.values()
        )
        inner_half_extent = protected_extent + CONVOY_GUARD_MARGIN_M
        enclosed = sorted(
            (
                item for item in self.vehicles
                if item.role != "CLOSE_GUARD"
                and item.assigned_threat is None
                and max(abs(item.x - center_x), abs(item.y - center_y))
                < inner_half_extent - 1.0
            ),
            key=lambda item: (item.kind, item.code),
        )
        available_guards = [
            item for item in self.vehicles
            if item.role == "CLOSE_GUARD"
        ]
        guard_count = len(available_guards)
        for item in enclosed:
            same_kind = [
                guard for guard in available_guards
                if guard.kind == item.kind
            ]
            if not same_kind:
                continue
            released = min(
                same_kind,
                key=lambda guard: (
                    _length(
                        item.x - self._convoy_guard_point(
                            self._convoy_guard_slot_by_code[guard.code],
                            guard_count,
                        )[0],
                        item.y - self._convoy_guard_point(
                            self._convoy_guard_slot_by_code[guard.code],
                            guard_count,
                        )[1],
                    ),
                    guard.code,
                ),
            )
            slot = self._convoy_guard_slot_by_code.pop(released.code)
            self._convoy_guard_slot_by_code[item.code] = slot
            item.role = "CLOSE_GUARD"
            item.group_id = released.group_id
            item.protected_index = released.protected_index
            released.role = "CAPTURE_RESERVE"
            released.group_id = "POST-MISSION-RELEASE"
            released.final_slot_angle = None
            available_guards.remove(released)

    def _swap_enclosed_support_with_guards(self) -> None:
        """Keep a moving convoy from enclosing a recalled support craft."""
        center_x, center_y = self._convoy_center()
        protected_extent = max(
            max(abs(offset[0]), abs(offset[1]))
            for offset in self._protected_formation_offsets.values()
        )
        inner_half_extent = protected_extent + CONVOY_GUARD_MARGIN_M
        enclosed: list[_Vehicle] = []
        for item in self._convoy_support_members():
            same_kind_guards = [
                guard for guard in self.vehicles
                if guard.role == "CLOSE_GUARD" and guard.kind == item.kind
            ]
            all_guards = [
                guard for guard in self.vehicles
                if guard.role == "CLOSE_GUARD"
            ]
            inside_guard_square = (
                max(abs(item.x - center_x), abs(item.y - center_y))
                < inner_half_extent - 1.0
            )
            pinned_to_guard = any(
                _length(item.x - guard.x, item.y - guard.y) < 16.0
                for guard in all_guards
            )
            if inside_guard_square or pinned_to_guard:
                enclosed.append(item)
        for item in enclosed:
            guards = [
                guard for guard in self.vehicles
                if guard.role == "CLOSE_GUARD" and guard.kind == item.kind
                and tuple(sorted((item.code, guard.code)))
                not in self._convoy_support_swap_pairs
            ]
            if not guards or item.code not in self._convoy_support_slot_by_code:
                continue
            released = min(
                guards,
                key=lambda guard: (
                    _length(item.x - guard.x, item.y - guard.y),
                    guard.code,
                ),
            )
            support_slot = self._convoy_support_slot_by_code.pop(item.code)
            guard_slot = self._convoy_guard_slot_by_code.pop(released.code)

            item.role = "CLOSE_GUARD"
            item.group_id = released.group_id
            item.protected_index = released.protected_index
            item.assigned_threat = None
            self._convoy_guard_slot_by_code[item.code] = guard_slot

            released.role = "CONVOY_SUPPORT"
            released.group_id = "CONVOY-SUPPORT"
            released.assigned_threat = None
            released.final_slot_angle = None
            self._convoy_support_slot_by_code[released.code] = support_slot
            self._convoy_support_swap_pairs.add(
                tuple(sorted((item.code, released.code)))
            )

            self._convoy_support_route_by_code.pop(item.code, None)
            self._convoy_support_route_cursor_by_code.pop(item.code, None)
            self._convoy_support_route_replan_frame_by_code.pop(item.code, None)
            self._convoy_support_goal_override_by_code.pop(item.code, None)
            self._convoy_support_goal_override_by_code.pop(released.code, None)
            support_count = len(self._convoy_support_members())
            goal = self._safe_convoy_support_point(support_slot, support_count)
            route, effective_goal = self._build_convoy_support_route(released, goal)
            self._convoy_support_route_by_code[released.code] = route
            if (
                self._post_mission_final_replan_done
                and _length(effective_goal[0] - goal[0], effective_goal[1] - goal[1]) > 0.05
            ):
                self._convoy_support_goal_override_by_code[released.code] = effective_goal
            self._convoy_support_route_cursor_by_code[released.code] = 0
            self._convoy_support_route_replan_frame_by_code[released.code] = self.sequence
            self._post_mission_initial_error_by_code.pop(item.code, None)
            self._post_mission_initial_error_by_code[released.code] = max(
                POST_MISSION_SLOT_TOLERANCE_M + 1.0,
                _length(released.x - goal[0], released.y - goal[1]),
            )

    def _redeploy_surplus_to_convoy(self) -> None:
        """Recall every released responder into an ordered outer guard square."""
        if not self.threats or not all(
            item.state in {"CAPTURED", "SECURED", "ESCAPED"}
            for item in self.threats
        ):
            return
        if self._post_mission_formation_initialized:
            if not self._post_mission_final_replan_done:
                self._swap_enclosed_support_with_guards()
            return

        self._swap_enclosed_surplus_with_guards()
        free = [
            item for item in self.vehicles
            if item.role != "CLOSE_GUARD" and item.assigned_threat is None
        ]
        support = sorted(free, key=lambda item: (item.kind, item.code))
        for item in support:
            item.role = "CONVOY_SUPPORT"
            item.group_id = "CONVOY-SUPPORT"
            item.final_slot_angle = None
        self._assign_convoy_support_slots(support)
        self._assign_convoy_support_routes(support)

        self._post_mission_formation_initialized = True
        for item in self._post_mission_members():
            desired_x, desired_y = self._post_mission_point(item)
            self._post_mission_initial_error_by_code[item.code] = max(
                POST_MISSION_SLOT_TOLERANCE_M + 1.0,
                _length(item.x - desired_x, item.y - desired_y),
            )

    def _replan_final_convoy_support_formation(self) -> None:
        """Reassign moving support slots once the convoy reaches its gate."""
        if self._post_mission_final_replan_done:
            return
        self._convoy_support_swap_pairs.clear()
        self._swap_enclosed_support_with_guards()
        support = self._convoy_support_members()
        if support:
            self._assign_convoy_support_slots(support)
            self._assign_convoy_support_routes(support, allow_terminal_fallback=True)
        self._post_mission_initial_error_by_code = {}
        for item in self._post_mission_members():
            desired_x, desired_y = self._post_mission_point(item)
            self._post_mission_initial_error_by_code[item.code] = max(
                POST_MISSION_SLOT_TOLERANCE_M + 1.0,
                _length(item.x - desired_x, item.y - desired_y),
            )
        self._convoy_support_ready_frames = 0
        self._post_mission_best_maximum_error = math.inf
        self._post_mission_stalled_frames = 0
        self._post_mission_final_replan_done = True

    def _replan_stalled_convoy_support_formation(self) -> None:
        # If one responder is physically wedged between close guards, path
        # reassignment alone cannot move it. Exchange it with one same-kind
        # guard before rebuilding the remaining outer-slot routes.
        self._swap_enclosed_support_with_guards()
        support = self._convoy_support_members()
        if not support:
            return
        self._assign_convoy_support_slots(support)
        self._assign_convoy_support_routes(support, allow_terminal_fallback=True)
        for item in support:
            desired_x, desired_y = self._post_mission_point(item)
            self._post_mission_initial_error_by_code[item.code] = max(
                POST_MISSION_SLOT_TOLERANCE_M + 1.0,
                _length(item.x - desired_x, item.y - desired_y),
            )
        self._post_mission_best_maximum_error = math.inf
        self._post_mission_stalled_frames = 0
        self._post_mission_slot_replans += 1

    def _post_watch_members(self) -> list[_Vehicle]:
        return sorted(
            (item for item in self.vehicles if item.role == "LOCAL_OVERWATCH"),
            key=lambda item: (
                self._post_watch_threat_by_code.get(item.code, 10_000),
                item.kind,
                item.code,
            ),
        )

    def _post_watch_point(self, item: _Vehicle) -> tuple[float, float]:
        threat_index = self._post_watch_threat_by_code[item.code]
        threat = self.threats[threat_index]
        angle = self._post_watch_angle_by_code[item.code]
        radius = TARGET_SEPARATION_M + (14.0 if item.kind == "USV" else 26.0)
        return self._project_to_safe_water(
            threat.x + math.cos(angle) * radius,
            threat.y + math.sin(angle) * radius,
            12.0,
        )

    def _post_mission_members(self) -> list[_Vehicle]:
        return [*self._convoy_support_members(), *self._post_watch_members()]

    def _post_mission_point(self, item: _Vehicle) -> tuple[float, float]:
        if item.role == "CONVOY_SUPPORT":
            override = self._convoy_support_goal_override_by_code.get(item.code)
            if override is not None:
                return override
            support = self._convoy_support_members()
            return self._safe_convoy_support_point(support.index(item), len(support))
        return self._post_watch_point(item)

    def _post_mission_formation_status(self) -> dict[str, object]:
        members = self._post_mission_members()
        if not members:
            return {
                "ready": True,
                "readyCount": 0,
                "requiredCount": 0,
                "progress": 1.0,
                "maximumErrorM": 0.0,
                "blockerCode": "",
            }
        errors: list[tuple[float, _Vehicle]] = []
        progress_values: list[float] = []
        for item in members:
            desired_x, desired_y = self._post_mission_point(item)
            error = _length(item.x - desired_x, item.y - desired_y)
            errors.append((error, item))
            initial = self._post_mission_initial_error_by_code.get(
                item.code,
                max(POST_MISSION_SLOT_TOLERANCE_M + 1.0, error),
            )
            remaining_range = max(1.0, initial - POST_MISSION_SLOT_TOLERANCE_M)
            progress_values.append(max(
                0.0,
                min(1.0, 1.0 - max(0.0, error - POST_MISSION_SLOT_TOLERANCE_M) / remaining_range),
            ))
        maximum_error, blocker = max(errors, key=lambda row: (row[0], row[1].code))
        ready_count = sum(
            error <= POST_MISSION_SLOT_TOLERANCE_M
            for error, _ in errors
        )
        return {
            "ready": ready_count == len(members),
            "readyCount": ready_count,
            "requiredCount": len(members),
            "progress": sum(progress_values) / len(progress_values),
            "maximumErrorM": maximum_error,
            "blockerCode": "" if ready_count == len(members) else blocker.code,
        }

    def _assign_convoy_support_slots(self, members: Sequence[_Vehicle]) -> None:
        """Bind recalled craft to nearby rear slots without crossing traffic.

        Code-order assignment sent a late responder from the convoy's front to
        the farthest rear slot while nearer craft crossed in the opposite
        direction.  That produced a long collision-avoidance oscillation at
        maximum speed.  Use an exact small-fleet assignment and a deterministic
        nearest-pair fallback for capacity-mode fleets.
        """
        ordered = sorted(members, key=lambda item: item.code)
        count = len(ordered)
        if not count:
            self._convoy_support_slot_by_code = {}
            return
        points = [self._safe_convoy_support_point(index, count) for index in range(count)]
        costs = [
            [
                _length(item.x - point[0], item.y - point[1])
                for point in points
            ]
            for item in ordered
        ]
        if count <= 12:
            @lru_cache(maxsize=None)
            def solve(member_index: int, used_mask: int) -> tuple[float, tuple[int, ...]]:
                if member_index >= count:
                    return 0.0, ()
                best_cost = math.inf
                best_slots: tuple[int, ...] = ()
                for slot_index in range(count):
                    if used_mask & (1 << slot_index):
                        continue
                    remaining_cost, remaining_slots = solve(
                        member_index + 1,
                        used_mask | (1 << slot_index),
                    )
                    candidate_cost = costs[member_index][slot_index] + remaining_cost
                    if candidate_cost < best_cost - 1e-9:
                        best_cost = candidate_cost
                        best_slots = (slot_index, *remaining_slots)
                return best_cost, best_slots

            _, slots = solve(0, 0)
            self._convoy_support_slot_by_code = {
                item.code: slots[index]
                for index, item in enumerate(ordered)
            }
            return

        # Hungarian assignment keeps capacity-mode fleets globally optimal.
        # The old nearest-pair greedy pass could leave the final USV with the
        # diagonally opposite slot, adding more than 100 m to its return leg.
        potentials_left = [0.0] * (count + 1)
        potentials_right = [0.0] * (count + 1)
        matched_left = [0] * (count + 1)
        predecessor = [0] * (count + 1)
        for left in range(1, count + 1):
            matched_left[0] = left
            minimum = [math.inf] * (count + 1)
            used = [False] * (count + 1)
            right = 0
            while True:
                used[right] = True
                current_left = matched_left[right]
                delta = math.inf
                next_right = 0
                for candidate_right in range(1, count + 1):
                    if used[candidate_right]:
                        continue
                    reduced = (
                        costs[current_left - 1][candidate_right - 1]
                        - potentials_left[current_left]
                        - potentials_right[candidate_right]
                    )
                    if reduced < minimum[candidate_right] - 1e-9:
                        minimum[candidate_right] = reduced
                        predecessor[candidate_right] = right
                    if minimum[candidate_right] < delta - 1e-9:
                        delta = minimum[candidate_right]
                        next_right = candidate_right
                for candidate_right in range(count + 1):
                    if used[candidate_right]:
                        potentials_left[matched_left[candidate_right]] += delta
                        potentials_right[candidate_right] -= delta
                    else:
                        minimum[candidate_right] -= delta
                right = next_right
                if matched_left[right] == 0:
                    break
            while True:
                previous_right = predecessor[right]
                matched_left[right] = matched_left[previous_right]
                right = previous_right
                if right == 0:
                    break
        slots_by_member = [0] * count
        for right in range(1, count + 1):
            slots_by_member[matched_left[right] - 1] = right - 1
        self._convoy_support_slot_by_code = {
            item.code: slots_by_member[index]
            for index, item in enumerate(ordered)
        }

    @staticmethod
    def _segment_distance_to_point(
        start: tuple[float, float],
        end: tuple[float, float],
        point: tuple[float, float],
    ) -> float:
        dx, dy = end[0] - start[0], end[1] - start[1]
        denominator = dx * dx + dy * dy
        if denominator <= 1e-9:
            return _length(start[0] - point[0], start[1] - point[1])
        ratio = max(0.0, min(
            1.0,
            ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy)
            / denominator,
        ))
        closest_x = start[0] + dx * ratio
        closest_y = start[1] + dy * ratio
        return _length(closest_x - point[0], closest_y - point[1])

    def _captured_return_obstacles(self) -> list[tuple[float, float, float]]:
        return [
            (threat.x, threat.y, POST_MISSION_RING_AVOIDANCE_M)
            for threat in self.threats
            if threat.state in {"CAPTURED", "SECURED"}
        ]

    def _convoy_return_obstacles(self) -> list[tuple[float, float, float]]:
        """Return rings plus the moving inner convoy as route obstacles."""
        center_x, center_y = self._convoy_center()
        protected_extent = max(
            max(abs(offset[0]), abs(offset[1]))
            for offset in self._protected_formation_offsets.values()
        )
        inner_radius = protected_extent + CONVOY_GUARD_MARGIN_M + 9.0
        return [
            *self._captured_return_obstacles(),
            (center_x, center_y, inner_radius),
        ]

    def _return_segment_is_clear(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        obstacles: Sequence[tuple[float, float, float]],
    ) -> bool:
        return all(
            self._segment_distance_to_point(start, end, (x, y)) >= radius - 0.25
            for x, y, radius in obstacles
        )

    def _build_convoy_support_route(
        self,
        item: _Vehicle,
        goal: tuple[float, float],
    ) -> tuple[list[tuple[float, float]], tuple[float, float]]:
        """Find waypoints and a reachable terminal point around fixed obstacles.

        A shoreline can join overlapping convoy/ring avoidance discs into a
        closed pocket. In that case the nominal outer-square slot is physically
        unreachable even though the point itself lies just outside both discs.
        Return the closest reachable visibility node as a deformed-but-safe
        terminal slot instead of repeatedly sending one craft into the pocket.
        """
        obstacles = self._convoy_return_obstacles()
        if not obstacles:
            return [], goal

        start = (item.x, item.y)
        escape_prefix: list[tuple[float, float]] = []
        # A responder can already be inside the conservative planning buffer
        # while still outside the occupied 34 m ring. Move radially outward
        # first, so no return route cuts through a completed containment ring.
        for _ in range(len(obstacles) + 1):
            containing = [
                obstacle for obstacle in obstacles
                if _length(start[0] - obstacle[0], start[1] - obstacle[1])
                < obstacle[2] + 0.5
            ]
            if not containing:
                break
            center_x, center_y, radius = max(
                containing,
                key=lambda obstacle: obstacle[2] - _length(
                    start[0] - obstacle[0], start[1] - obstacle[1],
                ),
            )
            start_radius = _length(start[0] - center_x, start[1] - center_y)
            candidates: list[tuple[float, tuple[float, float]]] = []
            for sample in range(40):
                angle = 2.0 * math.pi * sample / 40.0
                escaped = self._project_to_safe_water(
                    center_x + math.cos(angle) * (radius + 8.0),
                    center_y + math.sin(angle) * (radius + 8.0),
                    6.0,
                )
                if _length(escaped[0] - center_x, escaped[1] - center_y) < radius + 0.5:
                    continue
                if self._segment_distance_to_point(
                    start,
                    escaped,
                    (center_x, center_y),
                ) < min(start_radius - 0.25, TARGET_SEPARATION_M + 6.0):
                    continue
                if any(
                    other != (center_x, center_y, radius)
                    and self._segment_distance_to_point(
                        start,
                        escaped,
                        (other[0], other[1]),
                    ) < min(
                        other[2] - 0.25,
                        max(
                            TARGET_SEPARATION_M + 6.0,
                            _length(start[0] - other[0], start[1] - other[1]) - 0.25,
                        ),
                    )
                    for other in containing
                ):
                    continue
                candidates.append((
                    _length(escaped[0] - start[0], escaped[1] - start[1])
                    + 0.18 * _length(escaped[0] - goal[0], escaped[1] - goal[1]),
                    escaped,
                ))
            if not candidates:
                break
            _, escaped = min(candidates, key=lambda row: (row[0], row[1]))
            escape_prefix.append(escaped)
            start = escaped

        if self._return_segment_is_clear(start, goal, obstacles):
            return escape_prefix, goal

        nodes: list[tuple[float, float]] = [start, goal]
        samples_per_ring = 20
        for center_x, center_y, radius in obstacles:
            sample_radius = radius + 8.0
            for sample in range(samples_per_ring):
                angle = 2.0 * math.pi * sample / samples_per_ring
                candidate = self._project_to_safe_water(
                    center_x + math.cos(angle) * sample_radius,
                    center_y + math.sin(angle) * sample_radius,
                    6.0,
                )
                if all(
                    _length(candidate[0] - x, candidate[1] - y) >= other_radius + 0.5
                    for x, y, other_radius in obstacles
                ):
                    nodes.append(candidate)

        adjacency: list[list[tuple[float, int]]] = [[] for _ in nodes]
        for left in range(len(nodes)):
            for right in range(left + 1, len(nodes)):
                if not self._return_segment_is_clear(nodes[left], nodes[right], obstacles):
                    continue
                distance = _length(
                    nodes[left][0] - nodes[right][0],
                    nodes[left][1] - nodes[right][1],
                )
                adjacency[left].append((distance, right))
                adjacency[right].append((distance, left))

        distances = [math.inf] * len(nodes)
        previous = [-1] * len(nodes)
        distances[0] = 0.0
        queue: list[tuple[float, int]] = [(0.0, 0)]
        while queue:
            distance, index = heappop(queue)
            if distance > distances[index] + 1e-9:
                continue
            if index == 1:
                break
            for edge, neighbour in adjacency[index]:
                candidate = distance + edge
                if candidate >= distances[neighbour] - 1e-9:
                    continue
                distances[neighbour] = candidate
                previous[neighbour] = index
                heappush(queue, (candidate, neighbour))

        target_index = 1
        effective_goal = goal
        if not math.isfinite(distances[target_index]):
            reachable = [
                index for index in range(2, len(nodes))
                if math.isfinite(distances[index])
            ]
            if not reachable:
                # The escape point is already outside every conservative
                # obstacle and is the safest attainable holding station.
                return escape_prefix, start
            target_index = min(
                reachable,
                key=lambda index: (
                    _length(nodes[index][0] - goal[0], nodes[index][1] - goal[1]),
                    distances[index],
                    nodes[index][0],
                    nodes[index][1],
                ),
            )
            effective_goal = nodes[target_index]
        indices: list[int] = []
        cursor = target_index
        while cursor >= 0:
            indices.append(cursor)
            cursor = previous[cursor]
        indices.reverse()
        return (
            [*escape_prefix, *(nodes[index] for index in indices[1:-1])],
            effective_goal,
        )

    def _assign_convoy_support_routes(
        self,
        members: Sequence[_Vehicle],
        *,
        allow_terminal_fallback: bool = False,
    ) -> None:
        self._convoy_support_route_by_code = {}
        self._convoy_support_route_cursor_by_code = {}
        self._convoy_support_route_replan_frame_by_code = {}
        self._convoy_support_goal_override_by_code = {}
        count = len(members)
        for item in members:
            slot = self._convoy_support_slot_by_code[item.code]
            goal = self._safe_convoy_support_point(slot, count)
            route, effective_goal = self._build_convoy_support_route(item, goal)
            self._convoy_support_route_by_code[item.code] = route
            if (
                allow_terminal_fallback
                and _length(effective_goal[0] - goal[0], effective_goal[1] - goal[1]) > 0.05
            ):
                self._convoy_support_goal_override_by_code[item.code] = effective_goal
            self._convoy_support_route_cursor_by_code[item.code] = 0
            self._convoy_support_route_replan_frame_by_code[item.code] = self.sequence

    def _convoy_support_route_point(
        self,
        item: _Vehicle,
    ) -> tuple[float, float] | None:
        route = self._convoy_support_route_by_code.get(item.code, [])
        cursor = self._convoy_support_route_cursor_by_code.get(item.code, 0)
        while cursor < len(route) and _length(
            item.x - route[cursor][0],
            item.y - route[cursor][1],
        ) <= POST_MISSION_ROUTE_ARRIVAL_M:
            cursor += 1
        self._convoy_support_route_cursor_by_code[item.code] = cursor
        if cursor < len(route):
            return route[cursor]

        members = self._convoy_support_members()
        if item not in members:
            return None
        if item.code in self._convoy_support_goal_override_by_code:
            # A terminal fallback is a deliberately deformed outer slot chosen
            # from the reachable visibility component. Replanning it back to
            # the sealed nominal pocket would recreate the same oscillation.
            return None
        slot = self._convoy_support_slot_by_code[item.code]
        goal = self._safe_convoy_support_point(slot, len(members))
        obstacles = self._convoy_return_obstacles()
        if not obstacles or self._return_segment_is_clear(
            (item.x, item.y),
            goal,
            obstacles,
        ):
            return None

        last_replan = self._convoy_support_route_replan_frame_by_code.get(
            item.code,
            -10_000,
        )
        if self.sequence - last_replan < 30:
            return None
        route, effective_goal = self._build_convoy_support_route(item, goal)
        if (
            self._post_mission_final_replan_done
            and _length(effective_goal[0] - goal[0], effective_goal[1] - goal[1]) > 0.05
        ):
            self._convoy_support_goal_override_by_code[item.code] = effective_goal
        self._convoy_support_route_by_code[item.code] = route
        self._convoy_support_route_cursor_by_code[item.code] = 0
        self._convoy_support_route_replan_frame_by_code[item.code] = self.sequence
        return None if not route else route[0]

    def _convoy_support_ready(self, tolerance_m: float = 7.5) -> bool:
        members = self._convoy_support_members()
        return all(
            _length(
                item.x - self._safe_convoy_support_point(position, len(members))[0],
                item.y - self._safe_convoy_support_point(position, len(members))[1],
            ) <= tolerance_m
            for position, item in enumerate(members)
        )

    def _project_to_safe_water(self, x: float, y: float, inset: float = 0.0) -> tuple[float, float]:
        return (
            max(self.safe_bounds[0] + inset, min(self.safe_bounds[1] - inset, x)),
            max(self.safe_bounds[2] + inset, min(self.safe_bounds[3] - inset, y)),
        )

    def _distance_to_protected(self, threat: _Threat) -> float:
        target = self.protected[threat.protected_index]
        return _length(threat.x - target.x, threat.y - target.y)

    def _threat_risk(self, threat: _Threat) -> tuple[float, float, float]:
        """Return risk, predicted impact time and positive closing speed."""
        target = self.protected[threat.protected_index]
        dx, dy = target.x - threat.x, target.y - threat.y
        distance = max(1e-6, _length(dx, dy))
        ux, uy = dx / distance, dy / distance
        closing = max(
            0.0,
            (threat.vx - target.vx) * ux + (threat.vy - target.vy) * uy,
        )
        tti = distance / max(0.12, closing)
        risk = (
            max(0.0, THREAT_DETECTION_M - distance) * 0.75
            + max(0.0, 55.0 - tti) * 2.4
            + closing * 18.0
            + (30.0 if distance < URGENT_DISTANCE_M else 0.0)
        )
        return risk, tti, closing

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

    def _retarget_attackers(self) -> None:
        """Let free attackers choose a credible convoy target with hysteresis.

        The previous modulo binding meant an enemy could continue toward a
        distant protected vessel while another one passed beside it.  We score
        predicted arrival time, close-guard density and shoreline clearance,
        then switch only when the new target is materially better.  Forced
        capture keeps its current incident identity so containment teams do
        not churn between targets.
        """
        if len(self.protected) < 2:
            return

        def score(threat: _Threat, protected_index: int) -> float:
            target = self.protected[protected_index]
            future_x = target.x + target.vx * 6.0
            future_y = target.y + target.vy * 6.0
            distance = _length(threat.x - future_x, threat.y - future_y)
            guards = sum(
                item.protected_index == protected_index
                and item.role in {"CLOSE_GUARD", "BLOCKER", "CONFRONT"}
                for item in self.vehicles
            )
            shore_clearance = min(
                target.x - self.safe_bounds[0], self.safe_bounds[1] - target.x,
                target.y - self.safe_bounds[2], self.safe_bounds[3] - target.y,
            )
            # Lower is more attractive. Sparse protection is attractive, but
            # distance remains dominant so enemies visibly pursue rather than
            # oscillating between convoys.
            return distance + guards * 7.5 - min(45.0, shore_clearance) * 0.12

        for threat in self.threats:
            if (
                threat.forced
                or threat.state in {"WAITING", "CAPTURED", "SECURED", "ESCAPED"}
                or self.sequence - threat.last_retarget_frame < 25
            ):
                continue
            current_score = score(threat, threat.protected_index)
            candidate = min(range(len(self.protected)), key=lambda index: score(threat, index))
            candidate_score = score(threat, candidate)
            if candidate != threat.protected_index and candidate_score <= current_score * 0.84:
                threat.protected_index = candidate
                threat.detected_frame = None
                threat.intercept_hold_frames = 0
                threat.intent = "RETARGETING"
            threat.last_retarget_frame = self.sequence

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
            threat.intercept_stage_frames = 0
            threat.mission_stage = "ESCAPE"
            threat.containment_stage_latched = False
            threat.containment_soft_failure_frames = 0
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
        self._rebalance_capture_groups(active_forced)

    def _start_parallel_response(self) -> None:
        """Dispatch one fixed mixed team to every simultaneous attacker.

        The earlier incident-driven path waited for each block condition before
        assigning a capture group. With three visible attackers that made a
        seeded run look serial: one 4+4 ring was already complete while the
        other two cards still showed 0+0. Realtime fleets from 15+15 through
        30+30 have enough mixed capacity for one 4+4 team per visible threat,
        the 4+4 close guard and a mixed response reserve. Allocate those teams
        together and keep their incident identity through intercept, pursuit
        and containment.
        """
        if self._parallel_response_started or not self._parallel_response_enabled:
            return
        simultaneous = [
            threat for threat in self.threats
            if threat.state not in {"WAITING", "CAPTURED", "SECURED", "ESCAPED"}
        ]
        if not simultaneous:
            return
        self._parallel_response_started = True
        self._start_capture_for(simultaneous, "PARALLEL_RESPONSE")

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
        # A completed ring persists, but it must not permanently monopolise
        # the whole fleet. Keep the smallest robust mixed ring (2 UAV + 2 USV)
        # around every captured threat and release surplus craft for later
        # incidents. Without this hand-off THREAT-003/004 had no blocker or
        # capture members at 20+ and remained ATTACKING/INTERCEPTING forever.
        self._release_surplus_containment()
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
            # Four craft of each kind per target is the preferred scalable
            # ring. Only fall back toward the structural 2-per-kind minimum
            # when the configured fleet cannot supply both that ring and a
            # response reserve.
            preferred_required = len(ordered_threats) * 4
            # Preserve a mixed quick-response reserve whenever capacity permits.
            # Previously every free craft was consumed by the first capture,
            # leaving a later attacker with no timely blocker.
            reserve = min(
                max(1, math.ceil(getattr(
                    self.plan,
                    "uav_count" if kind == "UAV" else "usv_count",
                    len(available),
                ) * 0.18)),
                max(0, len(available) - preferred_required),
            )
            reserve = min(
                reserve,
                max(0, len(available) - len(ordered_threats) * 2),
            )
            assignable = max(0, len(available) - reserve)
            per_threat_quota = min(
                4,
                max(2, assignable // max(1, len(ordered_threats))),
            )
            # A bounded quota prevents one early incident from absorbing every
            # free craft. Four of each kind gives an unambiguous eight-point
            # ring; remaining craft stay available for blockers and later
            # threats instead of producing a 32-member ring beside an empty
            # group.
            for _ in range(per_threat_quota):
                for threat_index, threat in ordered_threats:
                    if not available:
                        break
                    chosen = min(
                        available,
                        key=lambda item: _length(item.x - threat.x, item.y - threat.y),
                    )
                    chosen.assigned_threat = threat_index
                    chosen.role = "INTERCEPTOR"
                    chosen.group_id = f"CAPTURE-{threat_index + 1:03d}"
                    available.remove(chosen)
            available.sort(key=lambda item: item.code)
            if len(self.protected) > 1:
                # The fixed 4+4 teams already provide a complete mixed ring
                # for every simultaneous threat.  Sending the remaining large
                # fleet on 78 m incident orbits made the advertised escort
                # force look like scattered stragglers.  Keep every surplus
                # craft in one ordered outer convoy square instead: it remains
                # a quick-response reserve, but is visibly part of the escort
                # formation until a real reassignment is required.
                for position, reserved in enumerate(available):
                    threat_index = ordered_threats[position % len(ordered_threats)][0]
                    reserved.role = "CAPTURE_RESERVE"
                    reserved.group_id = f"RESERVE-{threat_index + 1:03d}"
            else:
                for reserved in available[:reserve]:
                    reserved.role = "CAPTURE_RESERVE"
                    reserved.group_id = f"RESERVE-{reserved.protected_index + 1:03d}"
                for patrol in available[reserve:]:
                    patrol.role = "RECON"
                    patrol.group_id = f"RECON-{patrol.protected_index + 1:03d}"
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
            if item.state not in {"WAITING", "ESCAPED"}
        ]
        return min(hazards, key=lambda pair: _length(pair[1].x - target.x, pair[1].y - target.y)) if hazards else None

    def _protected_hazards(self, protected_index: int) -> list[_Threat]:
        return [
            item for item in self.threats
            if item.state not in {"WAITING", "ESCAPED"}
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
            shore_penalty = max(0.0, 18.0 - shore_clearance) * 18.0
            minimum_clearance = min(predicted, default=200.0)
            mean_clearance = sum(predicted) / max(1, len(predicted))
            route_alignment = dx * goal_x + dy * goal_y
            if route_priority:
                # Captured threats are stationary keep-out zones, not active
                # pursuers. Favour a safe tangent that still advances through
                # the destination gate instead of orbiting the containment
                # group forever.
                clearance_penalty = max(
                    0.0,
                    POST_CAPTURE_CONVOY_CLEARANCE_M - minimum_clearance,
                ) * 16.0
                score = (
                    route_alignment * 54.0
                    + min(72.0, minimum_clearance) * 0.48
                    + min(50.0, shore_clearance) * 0.72
                    - clearance_penalty
                    - shore_penalty
                )
            else:
                score = (
                    minimum_clearance * 2.4
                    + mean_clearance * 0.32
                    + route_alignment * 22.0
                    + min(50.0, shore_clearance) * 0.72
                    - closing_penalty
                    - shore_penalty
                )
            if best is None or score > best[0]:
                best = (score, dx, dy)
        assert best is not None
        return best[1], best[2]

    def _choose_convoy_escape(
        self,
        hazards: Sequence[_Threat],
        speed: float,
        *,
        route_priority: bool = False,
    ) -> tuple[float, float]:
        """Choose one safe heading for the complete protected formation.

        Scoring every protected hull against every hostile prevents separate
        targets from selecting opposite evasive corridors. The chosen intent
        is later applied as one rigid translation, preserving every slot.
        """
        center_x, center_y = self._convoy_center()
        destination_x = sum(item.destination_x for item in self.protected) / len(self.protected)
        destination_y = sum(item.destination_y for item in self.protected) / len(self.protected)
        goal_x, goal_y = _unit(destination_x - center_x, destination_y - center_y)
        horizon = 7.0
        left, right, bottom, top = self.safe_bounds
        best: tuple[float, float, float] | None = None
        for sample in range(48):
            angle = 2.0 * math.pi * sample / 48.0
            dx, dy = math.cos(angle), math.sin(angle)
            predicted: list[float] = []
            closing_penalty = 0.0
            shore_clearance = math.inf
            for target in self.protected:
                future_x = target.x + dx * speed * horizon
                future_y = target.y + dy * speed * horizon
                shore_clearance = min(
                    shore_clearance,
                    future_x - left,
                    right - future_x,
                    future_y - bottom,
                    top - future_y,
                )
                for threat in hazards:
                    threat_future_x = threat.x + threat.vx * horizon
                    threat_future_y = threat.y + threat.vy * horizon
                    future_distance = _length(
                        future_x - threat_future_x,
                        future_y - threat_future_y,
                    )
                    current_distance = _length(target.x - threat.x, target.y - threat.y)
                    predicted.append(future_distance)
                    if (
                        threat.state not in {"CAPTURED", "SECURED"}
                        and future_distance < current_distance
                    ):
                        closing_penalty += (current_distance - future_distance) * 4.2
            shore_penalty = max(0.0, 18.0 - shore_clearance) * 18.0
            minimum_clearance = min(predicted, default=200.0)
            mean_clearance = sum(predicted) / max(1, len(predicted))
            route_alignment = dx * goal_x + dy * goal_y
            if route_priority:
                clearance_penalty = max(
                    0.0,
                    POST_CAPTURE_CONVOY_CLEARANCE_M - minimum_clearance,
                ) * 16.0
                score = (
                    route_alignment * 54.0
                    + min(72.0, minimum_clearance) * 0.48
                    + min(50.0, shore_clearance) * 0.72
                    - clearance_penalty
                    - shore_penalty
                )
            else:
                score = (
                    minimum_clearance * 2.4
                    + mean_clearance * 0.32
                    + route_alignment * 22.0
                    + min(50.0, shore_clearance) * 0.72
                    - closing_penalty
                    - shore_penalty
                )
            if best is None or score > best[0]:
                best = (score, dx, dy)
        assert best is not None
        return best[1], best[2]

    def _translate_protected_convoy(
        self,
        direction_x: float,
        direction_y: float,
        speed: float,
        state: str,
        hazards: Sequence[_Threat],
        containment_clearance_m: float = CONTAINMENT_STANDOFF_M,
    ) -> None:
        """Apply one rigid, safety-scored translation to every protected hull."""
        current_vx = sum(item.vx for item in self.protected) / len(self.protected)
        current_vy = sum(item.vy for item in self.protected) / len(self.protected)
        desired_vx, desired_vy = direction_x * speed, direction_y * speed
        accel = 0.085
        shared_vx = current_vx + max(-accel, min(accel, desired_vx - current_vx))
        shared_vy = current_vy + max(-accel, min(accel, desired_vy - current_vy))
        shared_vx, shared_vy = _clamp_magnitude(shared_vx, shared_vy, 2.25)
        step = _length(shared_vx, shared_vy) * DT
        desired_heading_x, desired_heading_y = _unit(
            shared_vx,
            shared_vy,
            (direction_x, direction_y),
        )

        candidates: list[tuple[bool, float, float, float]] = []
        for sample in range(72):
            angle = 2.0 * math.pi * sample / 72.0
            candidate_x = math.cos(angle) * step
            candidate_y = math.sin(angle) * step
            margins: list[float] = []
            shore_clearance = math.inf
            for target in self.protected:
                next_x = target.x + candidate_x
                next_y = target.y + candidate_y
                shore_clearance = min(
                    shore_clearance,
                    next_x - self.safe_bounds[0],
                    self.safe_bounds[1] - next_x,
                    next_y - self.safe_bounds[2],
                    self.safe_bounds[3] - next_y,
                )
                for hazard in hazards:
                    required = (
                        containment_clearance_m
                        if hazard.state in {"CAPTURED", "SECURED"}
                        else TARGET_SEPARATION_M
                    )
                    margins.append(
                        _length(next_x - hazard.x, next_y - hazard.y) - required
                    )
            minimum_margin = min(margins, default=100.0)
            feasible = minimum_margin >= 0.0 and shore_clearance >= 0.5
            alignment = (
                math.cos(angle) * desired_heading_x
                + math.sin(angle) * desired_heading_y
            )
            clearance_score = (
                minimum_margin * 22.0
                if minimum_margin < 0.0
                else min(12.0, minimum_margin) * 0.5
            )
            score = (
                clearance_score
                + alignment * 18.0
                + min(20.0, shore_clearance) * 1.8
            )
            candidates.append((feasible, score, candidate_x, candidate_y))

        feasible_candidates = [candidate for candidate in candidates if candidate[0]]
        current_safe = all(
            _length(target.x - hazard.x, target.y - hazard.y) >= (
                containment_clearance_m
                if hazard.state in {"CAPTURED", "SECURED"}
                else TARGET_SEPARATION_M
            )
            for target in self.protected
            for hazard in hazards
        )
        if feasible_candidates:
            _, _, displacement_x, displacement_y = max(
                feasible_candidates,
                key=lambda candidate: candidate[1],
            )
        elif current_safe:
            displacement_x = displacement_y = 0.0
        else:
            _, _, displacement_x, displacement_y = max(
                candidates,
                key=lambda candidate: candidate[1],
            )

        if _length(displacement_x, displacement_y) > 1e-8:
            shared_vx = displacement_x / DT
            shared_vy = displacement_y / DT
            heading = math.degrees(math.atan2(displacement_y, displacement_x)) % 360.0
        else:
            shared_vx = shared_vy = 0.0
            heading = self.protected[0].heading
        if (
            abs(displacement_x - desired_heading_x * step) > 0.01
            or abs(displacement_y - desired_heading_y * step) > 0.01
        ):
            self.avoidance_count += 1
        for target in self.protected:
            target.x += displacement_x
            target.y += displacement_y
            target.vx = shared_vx
            target.vy = shared_vy
            target.heading = heading
            target.state = state

    def _advance_protected(self) -> None:
        cruise = min(1.85, max(1.2, self.usv_cruise * 0.58))
        hazards = [
            item for item in self.threats
            if item.state not in {"WAITING", "ESCAPED"}
        ]
        mission_resolved = bool(self.threats) and all(
            item.state in {"CAPTURED", "SECURED", "ESCAPED"}
            for item in self.threats
        )
        # Once every hostile is resolved and the rigid convoy has cleared the
        # safe observation gate, hold that water-space while escorts regroup.
        # Continuing all the way to harbour made moving support slots overlap a
        # completed containment ring and needlessly lengthened the final phase.
        if mission_resolved and all(
            self._protected_reached_safe_gate(item)
            for item in self.protected
        ):
            for target in self.protected:
                target.vx = target.vy = 0.0
                target.state = "REGROUPING"
            return
        live_attackers = [
            item for item in hazards
            if item.state not in {"CAPTURED", "SECURED"}
            and min(
                _length(item.x - target.x, item.y - target.y)
                for target in self.protected
            ) < 165.0
        ]
        persistent_obstacles = [
            item for item in hazards
            if item.state in {"CAPTURED", "SECURED"}
            and min(
                _length(item.x - target.x, item.y - target.y)
                for target in self.protected
            ) < CONTAINMENT_REPLAN_M
        ]
        destination_x = sum(item.destination_x for item in self.protected) / len(self.protected)
        destination_y = sum(item.destination_y for item in self.protected) / len(self.protected)
        center_x, center_y = self._convoy_center()
        common_x, common_y = _unit(destination_x - center_x, destination_y - center_y)
        common_speed = cruise
        common_state = "ESCORTING"
        nearest_distance = min(
            (
                _length(threat.x - target.x, threat.y - target.y)
                for threat in hazards
                for target in self.protected
            ),
            default=math.inf,
        )
        if live_attackers:
            common_speed = min(2.25, max(1.55, self.usv_cruise * 0.70))
            common_x, common_y = self._choose_convoy_escape(
                live_attackers,
                common_speed,
            )
            common_state = "EVADING" if nearest_distance < 105.0 else "THREAT_DETECTED"
        elif persistent_obstacles:
            common_speed = min(1.85, max(1.25, self.usv_cruise * 0.58))
            common_x, common_y = self._choose_convoy_escape(
                persistent_obstacles,
                common_speed,
                route_priority=True,
            )
            common_state = "BYPASSING_CONTAINMENT"

        if len(self.protected) > 1:
            self._translate_protected_convoy(
                common_x,
                common_y,
                common_speed,
                common_state,
                hazards,
                (
                    POST_CAPTURE_CONVOY_CLEARANCE_M
                    if mission_resolved
                    else CONTAINMENT_STANDOFF_M
                ),
            )
            return

        for index, target in enumerate(self.protected):
            offset_x, offset_y = self._protected_formation_offsets[target.code]
            slot_error_x = center_x + offset_x - target.x
            slot_error_y = center_y + offset_y - target.y
            correction_x, correction_y = _clamp_magnitude(
                slot_error_x * 0.18,
                slot_error_y * 0.18,
                0.55,
            )
            desired_vx = common_x * common_speed + correction_x
            desired_vy = common_y * common_speed + correction_y
            target.state = common_state
            desired_vx, desired_vy = _clamp_magnitude(desired_vx, desired_vy, 2.25)
            accel = 0.085
            target.vx += max(-accel, min(accel, desired_vx - target.vx))
            target.vy += max(-accel, min(accel, desired_vy - target.vy))
            nx, ny = self._project_to_safe_water(target.x + target.vx * DT, target.y + target.vy * DT)
            relevant_hazards = [
                hazard for hazard in self.threats
                if hazard.state not in {"WAITING", "ESCAPED"}
            ]
            containment_clearance_m = (
                POST_CAPTURE_CONVOY_CLEARANCE_M
                if mission_resolved
                else CONTAINMENT_STANDOFF_M
            )
            if any(
                _length(nx - hazard.x, ny - hazard.y) < (
                    containment_clearance_m
                    if hazard.state in {"CAPTURED", "SECURED"}
                    else TARGET_SEPARATION_M
                )
                for hazard in relevant_hazards
            ):
                # Select a feasible one-tick heading against every hazard and
                # the shoreline together. The old fixed left/right tangent
                # could point outside the water at a corner; projection then
                # reduced the physical step to zero and stranded a convoy.
                step = min(2.25, max(cruise, _length(target.vx, target.vy))) * DT
                goal_x, goal_y = _unit(
                    target.destination_x - target.x,
                    target.destination_y - target.y,
                )
                velocity_x, velocity_y = _unit(target.vx, target.vy, (goal_x, goal_y))
                candidates: list[tuple[float, float, float, float, float, float]] = []
                for sample in range(72):
                    angle = 2.0 * math.pi * sample / 72.0
                    direction_x, direction_y = math.cos(angle), math.sin(angle)
                    candidate_x, candidate_y = self._project_to_safe_water(
                        target.x + direction_x * step,
                        target.y + direction_y * step,
                        0.5,
                    )
                    displacement = _length(candidate_x - target.x, candidate_y - target.y)
                    if displacement < step * 0.45:
                        continue
                    margins = [
                        _length(candidate_x - hazard.x, candidate_y - hazard.y) - (
                            containment_clearance_m
                            if hazard.state in {"CAPTURED", "SECURED"}
                            else TARGET_SEPARATION_M
                        )
                        for hazard in relevant_hazards
                    ]
                    minimum_margin = min(margins, default=100.0)
                    shore_clearance = min(
                        candidate_x - self.safe_bounds[0], self.safe_bounds[1] - candidate_x,
                        candidate_y - self.safe_bounds[2], self.safe_bounds[3] - candidate_y,
                    )
                    route_alignment = direction_x * goal_x + direction_y * goal_y
                    smooth_alignment = direction_x * velocity_x + direction_y * velocity_y
                    score = (
                        minimum_margin * (22.0 if minimum_margin < 0.0 else 3.0)
                        + route_alignment * 16.0
                        + smooth_alignment * 2.0
                        + min(20.0, shore_clearance) * 1.8
                    )
                    candidates.append((
                        score, minimum_margin, candidate_x, candidate_y,
                        direction_x, direction_y,
                    ))
                feasible_candidates = [
                    candidate for candidate in candidates if candidate[1] >= 0.0
                ]
                if candidates:
                    best_candidate = max(
                        feasible_candidates or candidates,
                        key=lambda candidate: candidate[0],
                    )
                    _, _, nx, ny, direction_x, direction_y = best_candidate
                    target.vx = direction_x * step / DT
                    target.vy = direction_y * step / DT
                    self.avoidance_count += 1
            # Protected vessels are independent moving hulls, not points. In
            # multi-convoy scenes they can choose the same escape corridor and
            # converge even though each one is clear of its assigned threat.
            # Start a deterministic lateral split before their hull envelopes
            # touch; keep the correction at the vessel's physical step so the
            # WebGL presentation never jumps.
            for other_index, other in enumerate(self.protected):
                if other is target:
                    continue
                separation = _length(nx - other.x, ny - other.y)
                if separation >= 34.0:
                    continue
                away_x, away_y = _unit(
                    nx - other.x,
                    ny - other.y,
                    (0.0, 1.0 if index < other_index else -1.0),
                )
                side = 1.0 if index < other_index else -1.0
                split_x, split_y = _unit(away_x - away_y * 0.48 * side, away_y + away_x * 0.48 * side)
                step = min(2.25, max(cruise, _length(target.vx, target.vy))) * DT
                nx, ny = self._project_to_safe_water(
                    target.x + split_x * step,
                    target.y + split_y * step,
                    12.0,
                )
                target.vx, target.vy = split_x * step / DT, split_y * step / DT
                self.avoidance_count += 1
            # Final emitted-pose guard: a convoy never enters any enemy hull
            # or completed containment keep-out zone. If a crowded multi-
            # threat candidate cannot maintain the safety radius this tick,
            # hold the previous safe pose and let the next scored heading find
            # another corridor. Holding is physically smooth; reporting a
            # terminal failure after an avoidable one-frame overlap is not.
            if any(
                _length(nx - hazard.x, ny - hazard.y) < (
                    POST_CAPTURE_CONVOY_CLEARANCE_M
                    if mission_resolved and hazard.state in {"CAPTURED", "SECURED"}
                    else TARGET_SEPARATION_M
                )
                for hazard in hazards
            ):
                previous_is_safe = all(
                    _length(target.x - hazard.x, target.y - hazard.y) >= (
                        POST_CAPTURE_CONVOY_CLEARANCE_M
                        if mission_resolved and hazard.state in {"CAPTURED", "SECURED"}
                        else TARGET_SEPARATION_M
                    )
                    for hazard in hazards
                )
                if previous_is_safe:
                    nx, ny = target.x, target.y
                    target.vx = target.vy = 0.0
                    self.avoidance_count += 1
            if _length(nx - target.x, ny - target.y) > 1e-5:
                target.heading = math.degrees(math.atan2(ny - target.y, nx - target.x)) % 360.0
            target.x, target.y = nx, ny

    def _release_surplus_containment(self) -> None:
        """Keep completed teams intact so a captured target cannot regain a gap.

        The previous implementation reduced a finished group to 2 UAV + 2 USV
        and later pulled other craft back during final consolidation. That
        release/rejoin cycle was the main source of visually broken rings.
        Response reserve is now decided before assignment, not by dismantling
        an already valid containment team.
        """
        return
        # Legacy release code remains below temporarily for history and will be
        # removed after the compatibility matrix has passed.
        # Surplus is released only while another incident still needs a
        # response team. Once every threat is resolved, all available craft
        # are deliberately consolidated into the visible final rings instead
        # of ending the mission as a few tiny polygons plus unrelated dots.
        if self.threats and all(
            item.state in {"CAPTURED", "SECURED", "ESCAPED"}
            for item in self.threats
        ):
            return
        for completed_index, completed in enumerate(self.threats):
            if completed.state not in {"CAPTURED", "SECURED"}:
                continue
            released_any = False
            for kind in ("UAV", "USV"):
                completed_members = sorted(
                    (
                        item for item in self.vehicles
                        if item.kind == kind and item.assigned_threat == completed_index
                    ),
                    key=lambda item: int(item.code.rsplit("-", 1)[-1]),
                )
                for released in completed_members[2:]:
                    released.assigned_threat = None
                    released.role = "RETURNING"
                    released.group_id = f"RECON-{released.protected_index + 1:03d}"
                    released.final_slot_angle = None
                    released_any = True
            if released_any:
                self._freeze_even_slot_angles(completed_index)

    def _freeze_even_slot_angles(self, threat_index: int) -> None:
        """Preserve the current circular order and distribute it uniformly."""
        threat = self.threats[threat_index]
        members = self._capture_members(threat_index)
        if not members:
            return
        angular = sorted(
            (
                math.atan2(item.y - threat.y, item.x - threat.x)
                % (2.0 * math.pi),
                item,
            )
            for item in members
        )
        gaps = [
            (angular[(index + 1) % len(angular)][0] - angular[index][0])
            % (2.0 * math.pi)
            for index in range(len(angular))
        ]
        start = (max(range(len(gaps)), key=gaps.__getitem__) + 1) % len(angular)
        start_angle = angular[start][0]
        for offset in range(len(angular)):
            item = angular[(start + offset) % len(angular)][1]
            item.final_slot_angle = (
                start_angle + 2.0 * math.pi * offset / len(angular)
            ) % (2.0 * math.pi)

    def _consolidate_final_containment(self) -> None:
        """Final containment is already authoritative; never reshuffle it."""
        self._final_containment_consolidated = True
        return
        # Legacy consolidation code remains unreachable during migration.
        if self._final_containment_consolidated:
            return
        captured_indices = [
            index for index, threat in enumerate(self.threats)
            if threat.state in {"CAPTURED", "SECURED"}
        ]
        if not captured_indices:
            return
        for kind in ("UAV", "USV"):
            counts = {
                index: sum(
                    item.kind == kind and item.assigned_threat == index
                    for item in self.vehicles
                )
                for index in captured_indices
            }
            candidates = [
                item for item in self.vehicles
                if item.kind == kind
                and item.role != "CLOSE_GUARD"
                and item.assigned_threat not in captured_indices
            ]
            # Four craft of each kind make an unambiguous eight-point ring.
            # Pulling every surplus patrol craft into containment congests the
            # scene and can force a distant craft to cross the protected
            # convoy. Fill only deficient rings, always with the closest free
            # responder; remaining craft continue an orderly outer patrol.
            while candidates and any(counts[index] < 4 for index in captured_indices):
                target_index = min(
                    (index for index in captured_indices if counts[index] < 4),
                    key=lambda index: counts[index],
                )
                item = min(
                    candidates,
                    key=lambda candidate: _length(
                        candidate.x - self.threats[target_index].x,
                        candidate.y - self.threats[target_index].y,
                    ),
                )
                candidates.remove(item)
                item.assigned_threat = target_index
                item.role = "CONTAINMENT"
                item.group_id = f"CAPTURE-{target_index + 1:03d}"
                counts[target_index] += 1
        for target_index in captured_indices:
            self._freeze_even_slot_angles(target_index)
        self._final_containment_consolidated = True

    def _synchronize_guard_roles(self) -> None:
        self._release_surplus_containment()
        expected_codes: set[str] = set()
        incidents = [
            (index, threat) for index, threat in enumerate(self.threats)
            if threat.detected_frame is not None
            and not threat.forced
            and threat.state not in {"WAITING", "CAPTURED", "SECURED", "ESCAPED"}
        ]
        incidents.sort(key=lambda pair: self._threat_risk(pair[1])[0], reverse=True)
        # Every simultaneous attacker gets an independent surface blocker and
        # airborne observer. The former nearest-only loop left the second enemy
        # completely unopposed in a 10+10 / two-threat scene.
        for threat_index, threat in incidents:
            block_group = f"BLOCK-{threat_index + 1:03d}"
            watch_group = f"WATCH-{threat_index + 1:03d}"
            _, tti, closing = self._threat_risk(threat)
            distance = self._distance_to_protected(threat)
            urgent = tti <= URGENT_TTI_SECONDS or distance <= URGENT_DISTANCE_M
            desired_responders = 2 if urgent and closing > 0.05 else 1
            blockers = [
                item for item in self.vehicles
                if item.kind == "USV" and item.group_id == block_group
                and item.assigned_threat is None and item.role == "BLOCKER"
            ]
            while len(blockers) < desired_responders:
                surface = [
                    item for item in self.vehicles
                    if item.kind == "USV" and item.role in {"RECON", "RETURNING"}
                    and item.assigned_threat is None and item.code not in expected_codes
                ]
                if surface:
                    blocker = min(surface, key=lambda item: _length(item.x - threat.x, item.y - threat.y))
                    blocker.role, blocker.group_id = "BLOCKER", block_group
                    blockers.append(blocker)
                else:
                    break
            for blocker in blockers:
                expected_codes.add(blocker.code)

            observers = [
                item for item in self.vehicles
                if item.kind == "UAV" and item.group_id == watch_group
                and item.assigned_threat is None and item.role == "CONFRONT"
            ]
            while len(observers) < desired_responders:
                air = [
                    item for item in self.vehicles
                    if item.kind == "UAV" and item.role in {"RECON", "RETURNING"}
                    and item.assigned_threat is None and item.code not in expected_codes
                ]
                if air:
                    observer = min(air, key=lambda item: _length(item.x - threat.x, item.y - threat.y))
                    observer.role, observer.group_id = "CONFRONT", watch_group
                    observers.append(observer)
                else:
                    break
            for observer in observers:
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
                target = self.protected[threat.protected_index]
                start_x, start_y = _unit(target.x - threat.x, target.y - threat.y)
                threat.vx = start_x * threat.cruise_speed
                threat.vy = start_y * threat.cruise_speed
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
            # Enemy motion is not derived from the friendly slider.  Each
            # threat owns a seeded 1.5-2.2 m/s cruise speed and may make a
            # bounded 2.8 m/s burst when defenders close in.
            desired_speed = threat.cruise_speed
            if threat.detected_frame is not None and not threat.forced:
                threat.closest_attack_distance = min(threat.closest_attack_distance, distance)
                # A late incident can become the only remaining live threat
                # after earlier containment teams have completed.  In that
                # state the first-line blocker may never occupy the formal
                # interception corridor (the convoy and attacker can keep
                # choosing opposite flanks), while dozens of released craft
                # remain available.  After a visible attack/manoeuvre window,
                # let the second defensive line take over.  The guard is kept
                # deliberately conditional: it never pre-empts another active
                # pursuit and therefore does not turn initial escort into an
                # immediate ready-made encirclement.
                unresolved_capture = any(
                    other is not threat
                    and other.forced
                    and other.state not in {"CAPTURED", "SECURED", "ESCAPED"}
                    for other in self.threats
                )
                attack_elapsed = self.sequence - threat.detected_frame
                if attack_elapsed >= 850 and not unresolved_capture:
                    self._start_capture_for([threat], "SECOND_LINE_REDEPLOY")
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
                if self.sequence < threat.breach_until_frame:
                    # The hostile has committed to a scored flank. Give the
                    # manoeuvre a visible window before the second defensive
                    # line is allowed to establish another hold.
                    intercepted = False
                threat.intercept_hold_frames = (
                    threat.intercept_hold_frames + 1
                    if intercepted
                    else max(0, threat.intercept_hold_frames - 1)
                )
                nearby_defenders = sum(
                    _length(item.x - threat.x, item.y - threat.y) <= 46.0
                    for item in self.vehicles
                    if item.role in {"CLOSE_GUARD", "BLOCKER", "CONFRONT"}
                    and item.protected_index == threat.protected_index
                )
                _, tti, closing = self._threat_risk(threat)
                urgent_intercept = (
                    (tti <= URGENT_TTI_SECONDS or distance <= URGENT_DISTANCE_M)
                    and closing > 0.05
                    and nearby_defenders >= 2
                )
                required_intercept_hold = (
                    URGENT_INTERCEPT_HOLD_FRAMES
                    if urgent_intercept
                    else INTERCEPT_HOLD_FRAMES
                )
                if threat.intercept_hold_frames >= required_intercept_hold:
                    # A seeded, capacity-aware first-line outcome makes the
                    # escort scenario a real attack/defence exchange.  A
                    # bounded subset of runs breaches the first line, but a
                    # second established intercept always transitions to
                    # pursuit and containment.
                    breach_roll = random.Random(
                        self.seed * 1009 + index * 97 + threat.intercept_attempts * 7919
                    ).random()
                    enough_water = distance > BREACH_DISTANCE_M + 38.0
                    first_line_breach = (
                        threat.intercept_attempts == 0
                        and enough_water
                        and breach_roll < 0.32
                    )
                    threat.intercept_attempts += 1
                    threat.intercept_hold_frames = 0
                    if first_line_breach:
                        threat.breach_until_frame = self.sequence + 70
                        threat.state = "BREACHING"
                        threat.intent = "FLANKING_BREAKTHROUGH"
                    else:
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
                threat.state = (
                    "ESCAPE_PURSUIT"
                    if pursuit_run
                    else "ENCIRCLING"
                    if threat.capture_hold
                    else "INTERCEPTING"
                )
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
                        pressure = max(0.0, min(1.0, (70.0 - nearest_distance) / 46.0))
                        desired_speed = min(
                            threat.maximum_speed,
                            threat.cruise_speed + pressure * 0.6,
                        )
                        threat.intent = "ESCAPING"
                    else:
                        side = 1.0 if index % 2 == 0 else -1.0
                        desired_x, desired_y = _unit(
                            escape_x * 0.62 + avoid_x * 0.58 - escape_y * 0.28 * side,
                            escape_y * 0.62 + avoid_y * 0.58 + escape_x * 0.28 * side,
                        )
                        if threat.capture_hold > 0:
                            # Deceleration belongs exclusively to a real ring
                            # that is currently passing the geometric hold
                            # contract. A travelled-distance or stage flag can
                            # no longer make an uncontained enemy stop early.
                            hold_ratio = min(1.0, threat.capture_hold / CAPTURE_HOLD_FRAMES)
                            desired_speed = max(
                                0.08,
                                threat.cruise_speed * (1.0 - 0.94 * hold_ratio),
                            )
                        else:
                            pressure = max(0.0, min(1.0, (70.0 - nearest_distance) / 46.0))
                            desired_speed = min(
                                threat.maximum_speed,
                                threat.cruise_speed + pressure * 0.6,
                            )
                        threat.intent = "BREAKOUT"
            elif threat.detected_frame is not None:
                desired_x, desired_y, threat.intent = self._choose_attack_direction(
                    threat,
                    target,
                    desired_speed,
                )
                in_breach_window = self.sequence < threat.breach_until_frame
                threat.state = (
                    "BREACHING"
                    if in_breach_window
                    else "BLOCKED" if threat.intercept_hold_frames > 0 else threat.intent
                )
                blocker = next((item for item in self.vehicles if item.role == "BLOCKER" and item.group_id == f"BLOCK-{index + 1:03d}"), None)
                if blocker is not None and _length(blocker.x - threat.x, blocker.y - threat.y) < 42.0:
                    bx, by = _unit(threat.x - blocker.x, threat.y - blocker.y)
                    side = 1.0 if index % 2 == 0 else -1.0
                    desired_x, desired_y = _unit(
                        desired_x * 0.62 + bx * 0.55 - desired_y * side * 0.32,
                        desired_y * 0.62 + by * 0.55 + desired_x * side * 0.32,
                    )
                    desired_speed = min(
                        threat.maximum_speed,
                        max(
                            threat.cruise_speed,
                            threat.cruise_speed + (0.55 if in_breach_window else 0.25),
                        ),
                    )
                    threat.state = "BREACHING" if in_breach_window else "FLANKING"
            future_dx = threat.x + desired_x * desired_speed * 2.0 - target.x - target.vx * 2.0
            future_dy = threat.y + desired_y * desired_speed * 2.0 - target.y - target.vy * 2.0
            if _length(future_dx, future_dy) < TARGET_SEPARATION_M * 1.35:
                away_x, away_y = _unit(threat.x - target.x, threat.y - target.y)
                side = 1.0 if index % 2 == 0 else -1.0
                desired_x, desired_y = _unit(away_x - away_y * side, away_y + away_x * side)
            pursuit_run = threat.forced and self._pursuit_distance(threat) < threat.required_pursuit_distance
            if threat.forced and not pursuit_run:
                nearest_protected = min(
                    self.protected,
                    key=lambda protected: _length(
                        threat.x - protected.x, threat.y - protected.y,
                    ),
                )
                protected_clearance = _length(
                    threat.x - nearest_protected.x,
                    threat.y - nearest_protected.y,
                )
                if protected_clearance < CONTAINMENT_STANDOFF_M + 4.0:
                    # A final 27 m ring plus hull separation cannot physically
                    # fit beside a convoy only 34 m away. Open a visible safety
                    # corridor first; otherwise the protected hull blocks one
                    # or more canonical slots and no amount of slot rotation
                    # can close the circle.
                    away_x, away_y = _unit(
                        threat.x - nearest_protected.x,
                        threat.y - nearest_protected.y,
                    )
                    side = 1.0 if index % 2 == 0 else -1.0
                    desired_x, desired_y = _unit(
                        away_x * 0.94 - away_y * 0.22 * side,
                        away_y * 0.94 + away_x * 0.22 * side,
                    )
                    desired_speed = max(threat.cruise_speed, desired_speed)
                    threat.intent = "CLEARING_CONVOY"
            capture_inset = 30.0 if pursuit_run else 38.0 if threat.forced else 8.0
            water_left = self.safe_bounds[0] + capture_inset
            water_right = self.safe_bounds[1] - capture_inset
            water_bottom = self.safe_bounds[2] + capture_inset
            water_top = self.safe_bounds[3] - capture_inset
            shore_x = (1.0 if threat.x < water_left + 10.0 else 0.0) - (1.0 if threat.x > water_right - 10.0 else 0.0)
            shore_y = (1.0 if threat.y < water_bottom + 10.0 else 0.0) - (1.0 if threat.y > water_top - 10.0 else 0.0)
            if shore_x or shore_y:
                desired_x, desired_y = _unit(desired_x + shore_x * 1.35, desired_y + shore_y * 1.35)
            # Hostile targets also occupy water area. The vehicle resolver only
            # separates friendly proposals from fixed targets, so two moving
            # threats (or one moving threat and an already-contained one) used
            # to pass through each other at larger fleet sizes. Predict two
            # seconds ahead and choose opposite seeded passing sides early.
            separation_x = separation_y = 0.0
            for other_index, other in enumerate(self.threats):
                if other is threat or other.state in {"WAITING", "ESCAPED"}:
                    continue
                other_future_x = other.x + other.vx * 2.0
                other_future_y = other.y + other.vy * 2.0
                future_x = threat.x + desired_x * desired_speed * 2.0
                future_y = threat.y + desired_y * desired_speed * 2.0
                clearance = _length(future_x - other_future_x, future_y - other_future_y)
                current_clearance = _length(threat.x - other.x, threat.y - other.y)
                # A 38 m hull-to-hull threshold only prevents the target
                # centres from colliding; it cannot fit two 27 m final rings.
                # When either incident is already forming/holding a ring, keep
                # the centres far enough apart for both sets of slots plus the
                # safety resolver's target exclusion radius.  Otherwise a
                # perfectly valid slot can land inside a captured target's
                # keep-out zone and one pursuer will appear permanently dead.
                containment_nearby = (
                    other.state in {"CAPTURED", "SECURED", "STABLE_CONTAINMENT"}
                    or threat.capture_stage >= 1
                    or other.capture_stage >= 1
                )
                required_clearance = 76.0 if containment_nearby else 48.0
                if min(clearance, current_clearance) >= required_clearance:
                    continue
                away_x, away_y = _unit(
                    threat.x - other.x,
                    threat.y - other.y,
                    (0.0, 1.0 if index < other_index else -1.0),
                )
                side = 1.0 if index < other_index else -1.0
                urgency = 1.0 + max(
                    0.0,
                    (required_clearance - min(clearance, current_clearance))
                    / required_clearance,
                )
                separation_x += (away_x - away_y * 0.55 * side) * urgency
                separation_y += (away_y + away_x * 0.55 * side) * urgency
            if abs(separation_x) + abs(separation_y) > 1e-6:
                desired_x, desired_y = _unit(
                    desired_x * 0.52 + separation_x * 0.92,
                    desired_y * 0.52 + separation_y * 0.92,
                )
                desired_speed = max(threat.cruise_speed, desired_speed)
            desired_vx, desired_vy = desired_x * desired_speed, desired_y * desired_speed
            accel = 0.05
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
                retained_speed = min(
                    threat.maximum_speed,
                    max(threat.cruise_speed, _length(threat.vx, threat.vy)),
                )
                threat.vx = threat.escape_dir_x * retained_speed
                threat.vy = threat.escape_dir_y * retained_speed
            actual_distance = _length(nx - target.x, ny - target.y)
            if actual_distance < TARGET_SEPARATION_M:
                # At a coastline corner the direct away vector may point out
                # of water; clamping that one vector can still leave the two
                # hulls inside the breach radius. Select the nearest feasible
                # point on the complete safety circle instead.
                feasible: list[tuple[float, float, float]] = []
                for sample in range(72):
                    angle = 2.0 * math.pi * sample / 72.0
                    candidate_x = target.x + math.cos(angle) * TARGET_SEPARATION_M
                    candidate_y = target.y + math.sin(angle) * TARGET_SEPARATION_M
                    if not (
                        self.safe_bounds[0] + 0.5 <= candidate_x <= self.safe_bounds[1] - 0.5
                        and self.safe_bounds[2] + 0.5 <= candidate_y <= self.safe_bounds[3] - 0.5
                    ):
                        continue
                    feasible.append((
                        _length(candidate_x - nx, candidate_y - ny),
                        candidate_x,
                        candidate_y,
                    ))
                if feasible:
                    _, nx, ny = min(feasible, key=lambda candidate: candidate[0])
                else:
                    ux, uy = _unit(nx - target.x, ny - target.y)
                    nx, ny = self._project_to_safe_water(
                        target.x + ux * TARGET_SEPARATION_M,
                        target.y + uy * TARGET_SEPARATION_M,
                        0.5,
                    )
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
        # capture_stage >= 1 is the latched tactical hand-off.  A parallel
        # team may legitimately reach the predictive fan before the attacker
        # has travelled the legacy fixed distance; once assessment promotes
        # that incident, immediately replace the 112-degree chase fan with
        # canonical 360-degree ring slots.  Keying this only to the odometer
        # left every craft "100% arrived" on the wrong side of the target.
        pursuit_run = (
            threat.capture_stage == 0
            and self._pursuit_distance(threat) < threat.required_pursuit_distance
        )
        base_radius = (58.0, 41.0, 27.0)[min(2, threat.capture_stage)]
        # Slot identities stay stable while the centre moves. Rotating every
        # slot with a manoeuvring enemy makes pursuers chase a spinning goal
        # and prevents the ring from ever closing.
        phase = threat.capture_phase
        by_code: dict[str, FormationSlot] = {}
        threat_index = self.threats.index(threat)
        if not pursuit_run:
            ring_members = [
                RingMember(item.code, item.kind, item.x, item.y, item.z)
                for item in ordered
            ]
            cached = self._ring_slots.get(threat_index, {})
            if set(cached) != {item.code for item in ordered}:
                cached = build_canonical_slots(
                    ring_members,
                    (threat.x, threat.y, 0.0),
                    phase=phase,
                    minimum_spacing_m=14.0,
                )
                self._ring_slots[threat_index] = cached
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
                canonical = self._ring_slots[threat_index][item.code]
                angle = canonical.angle
                # UAV altitude already separates the two vehicle types.  A
                # shared horizontal radius produces one readable circle
                # instead of two offset, visually broken rings.
                radius = canonical.radius
            by_code[item.code] = FormationSlot(
                radius,
                angle,
                canonical.altitude if not pursuit_run else 25.0 + (index % 3) * 2.5 if item.kind == "UAV" else 0.0, 0,
            )
        return [by_code[item.code] for item in members]

    def _capture_radius_limit(self, members: Sequence[_Vehicle]) -> float:
        """Return the executed outer radius allowed by the shared contract."""
        if not members:
            return 0.0
        threat = self.threats[members[0].assigned_threat] if members[0].assigned_threat is not None else None
        if threat is None:
            return 0.0
        return max(slot.radius for slot in self._capture_slots(members, threat)) + 15.0

    def _live_containment(self, threat_index: int) -> dict[str, object]:
        """Assess the ring that is visible now, never a historical latch."""
        threat = self.threats[threat_index]
        members = self._capture_members(threat_index)
        if not members:
            contract = assess_containment(
                [],
                (threat.x, threat.y, 0.0),
                required_count=3,
                device_types=[],
                minimum_type_counts={"UAV": 1, "USV": 1},
                minimum_radius_m=18.0,
                maximum_radius_m=72.0,
                maximum_radial_spread_m=5.25,
                minimum_pairwise_separation_m=7.1,
                participating=0,
                tolerance_deg=1.0,
            )
            canonical = assess_canonical_ring(
                [], (threat.x, threat.y, 0.0), {},
                slot_tolerance_m=3.5,
                minimum_separation_m=7.0,
            )
            return {
                "members": members, "ready": False, "arrivalRatio": 0.0,
                "maxGapDeg": 360.0, "radialErrorM": math.inf,
                "contract": contract, "canonicalContract": canonical,
            }
        slots = self._capture_slots(members, threat)
        center_x, center_y = self._capture_center(threat, members)
        tolerance = 3.5 if threat.capture_stage >= 2 else 12.0
        errors = [
            _length(
                item.x - (center_x + math.cos(slot.angle) * slot.radius),
                item.y - (center_y + math.sin(slot.angle) * slot.radius),
            )
            for item, slot in zip(members, slots)
        ]
        participating = sum(error <= tolerance for error in errors)
        angles = sorted(
            math.atan2(item.y - threat.y, item.x - threat.x) % (2.0 * math.pi)
            for item in members
        )
        max_gap_deg = math.degrees(max(
            (angles[(index + 1) % len(angles)] - angles[index])
            % (2.0 * math.pi)
            for index in range(len(angles))
        ))
        contract = assess_containment(
            [(item.x, item.y, item.z) for item in members],
            (threat.x, threat.y, 0.0),
            required_count=len(members),
            device_types=[item.kind for item in members],
            minimum_type_counts={"UAV": 1, "USV": 1},
            minimum_radius_m=18.0 if threat.capture_stage >= 2 else 13.5,
            maximum_radius_m=self._capture_radius_limit(members),
            maximum_radial_spread_m=5.25 if threat.capture_stage >= 2 else 18.0,
            minimum_pairwise_separation_m=7.1,
            participating=participating,
            tolerance_deg=1.0,
        )
        slot_map = {
            item.code: RingSlot(
                index=index,
                angle=slot.angle,
                radius=slot.radius,
                altitude=slot.altitude,
            )
            for index, (item, slot) in enumerate(zip(members, slots))
        }
        canonical = assess_canonical_ring(
            [
                RingMember(
                    item.code, item.kind, item.x, item.y, item.z,
                    self._stable_headings.get(item.code),
                )
                for item in members
            ],
            (threat.x, threat.y, 0.0),
            slot_map,
            slot_tolerance_m=3.5,
            minimum_separation_m=7.0,
            require_inward_usv_heading=True,
            usv_heading_tolerance_deg=3.0,
        )
        return {
            "members": members,
            "ready": bool(contract.ready and canonical.ready),
            "arrivalRatio": canonical.arrival_ratio,
            "maxGapDeg": canonical.maximum_gap_deg,
            "radialErrorM": canonical.maximum_slot_error_m,
            "contract": contract,
            "canonicalContract": canonical,
        }

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
        # Every moving slot needs one simulation tick of velocity feed-forward.
        # Without it a surface craft that is nominally at its slot is always
        # commanded to the enemy's previous position, so sparse 2+2 rings keep
        # a permanent 12-15 degree wake-side gap.  Interception adds the longer
        # predictive horizon; final containment keeps only this one-tick term.
        lookahead = DT + min(5.0, max(0.0, mean_distance / mean_surface_speed * 0.13)) * stage_factor
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
                else "GAP_BLOCKER" if item.code == threat.gap_filler_code
                else "CAPTURE" if threat.capture_stage >= 1
                else "INTERCEPTOR"
            )
            center_x, center_y = self._capture_center(threat, members)
            slot = slots[members.index(item)]
            # The gap centre is an intent cue, not a replacement slot. The
            # selected craft accelerates to its stable angular slot; steering
            # it directly to the midpoint can merely move the opening to the
            # opposite side in sparse 2+2 groups.
            return slot.point((center_x, center_y, 0.0))
        if item.role == "CLOSE_GUARD":
            guards = sorted(
                (guard for guard in self.vehicles if guard.role == "CLOSE_GUARD"),
                key=lambda guard: (
                    int(guard.code.rsplit("-", 1)[-1]),
                    0 if guard.kind == "USV" else 1,
                ),
            )
            position = self._convoy_guard_slot_by_code.get(
                item.code,
                guards.index(item),
            )
            x, y = self._convoy_guard_point(position, len(guards))
            return x, y, item.z
        if item.role == "CONVOY_SUPPORT":
            inner_escape = self._convoy_inner_escape_point(item)
            if inner_escape is not None:
                return inner_escape[0], inner_escape[1], item.z
            route_point = self._convoy_support_route_point(item)
            if route_point is not None:
                return route_point[0], route_point[1], item.z
            supports = self._convoy_support_members()
            position = supports.index(item)
            x, y = self._safe_convoy_support_point(position, len(supports))
            return x, y, item.z
        if item.role == "LOCAL_OVERWATCH":
            x, y = self._post_watch_point(item)
            return x, y, item.z
        if len(self.protected) > 1 and item.role == "CAPTURE_RESERVE":
            reserves = self._convoy_reserve_members()
            position = reserves.index(item)
            x, y = self._safe_convoy_support_point(position, len(reserves))
            return x, y, item.z
        if (
            len(self.protected) > 1
            and item.role == "OUTER_INTERCEPT"
            and item.group_id.startswith("SUPPORT-")
        ):
            threat_index = int(item.group_id.rsplit("-", 1)[-1]) - 1
            if 0 <= threat_index < len(self.threats):
                threat = self.threats[threat_index]
                peers = sorted(
                    (
                        peer for peer in self.vehicles
                        if peer.group_id == item.group_id
                        and peer.role == item.role
                        and peer.assigned_threat is None
                    ),
                    key=lambda peer: (
                        int(peer.code.rsplit("-", 1)[-1]),
                        0 if peer.kind == "USV" else 1,
                    ),
                )
                position = peers.index(item) if item in peers else 0
                radius = 78.0
                angle = (
                    threat.capture_phase
                    + 2.0 * math.pi * position / max(1, len(peers))
                )
                center_x, center_y = self._project_to_safe_water(
                    threat.x + threat.vx * 2.0,
                    threat.y + threat.vy * 2.0,
                    radius + 8.0,
                )
                return (
                    center_x + math.cos(angle) * radius,
                    center_y + math.sin(angle) * radius,
                    item.z,
                )
        target = self.protected[item.protected_index]
        if item.role == "BLOCKER":
            threat_index = int(item.group_id.rsplit("-", 1)[-1]) - 1
            threat = self.threats[threat_index]
            ux, uy = _unit(threat.x - target.x, threat.y - target.y)
            lead = max(28.0, min(56.0, self._distance_to_protected(threat) * 0.48))
            peers = sorted(
                (
                    peer for peer in self.vehicles
                    if peer.group_id == item.group_id
                    and peer.role == "BLOCKER"
                    and peer.assigned_threat is None
                ),
                key=lambda peer: peer.code,
            )
            position = peers.index(item) if item in peers else 0
            lateral = (position - (len(peers) - 1) / 2.0) * 15.0
            # Form a moving barrier across the predicted attack corridor.
            x, y = self._project_to_safe_water(
                target.x + ux * lead - uy * lateral,
                target.y + uy * lead + ux * lateral,
            )
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
            angle = threat_angle + math.pi / 2.0 + (
                position - (len(peers) - 1) / 2.0
            ) * math.radians(28.0)
            radius = min(64.0, max(38.0, self._distance_to_protected(observed[1]) * 0.55))
        else:
            radius = 58.0 + (position % 3) * 8.0
            angle = self.sequence * (0.0040 if item.kind == "UAV" else 0.0035) + 2.0 * math.pi * position / max(1, len(peers))
        # Keep the whole patrol orbit inside navigable water. Clamping each
        # orbit point independently creates a long flat arc at the boundary,
        # which made RECON craft appear dead for hundreds of frames when the
        # convoy travelled near the coast. Moving the orbit centre inward
        # preserves continuous patrol motion without detaching the craft from
        # its protected target.
        if item.role in {"RECON", "RETURNING", "CAPTURE_RESERVE"}:
            orbit_center_x, orbit_center_y = self._project_to_safe_water(
                target.x, target.y, radius + 8.0,
            )
            x = orbit_center_x + math.cos(angle) * radius
            y = orbit_center_y + math.sin(angle) * radius
        else:
            x, y = self._project_to_safe_water(
                target.x + math.cos(angle) * radius,
                target.y + math.sin(angle) * radius,
            )
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
        step_limits: dict[str, float] = {}
        locked_ring_codes = {
            item.code
            for item in self.vehicles
            if self._post_mission_formation_initialized
            and item.assigned_threat is not None
            and self.threats[item.assigned_threat].state in {"CAPTURED", "SECURED"}
        }
        for item in self.vehicles:
            desired = self._desired_position(item)
            if item.code in locked_ring_codes:
                continue
            distance = _length(desired[0] - item.x, desired[1] - item.y)
            cruise = self.uav_cruise if item.kind == "UAV" else self.usv_cruise
            convoy_follower = (
                item.role == "CONVOY_SUPPORT"
                or len(self.protected) > 1 and item.role == "CAPTURE_RESERVE"
            )
            speed_factor = (
                1.0
                if item.role in {
                    "INTERCEPTOR", "CAPTURE", "BLOCKER", "GAP_BLOCKER",
                    "OUTER_INTERCEPT", "CAPTURE_RESERVE", "CONVOY_SUPPORT",
                    "LOCAL_OVERWATCH",
                }
                else 0.78
                if item.role == "CONFRONT"
                else 0.72
                if item.role == "CONTAINMENT"
                else 0.66
            )
            speed = cruise * speed_factor
            if convoy_follower:
                convoy_speed = max(
                    (_length(target.vx, target.vy) for target in self.protected),
                    default=0.0,
                )
                follower_cap = (
                    self.uav_cruise
                    if item.kind == "UAV"
                    else min(4.0, max(self.usv_cruise, convoy_speed + 0.9))
                )
                # A moving rear-echelon slot cannot be caught at exactly the
                # convoy's speed. Give recalled/reserve craft a bounded closing
                # margin (the same 4 m/s operational cap used by interceptors)
                # until they are back in formation.
                closing_margin = min(
                    0.9 if item.kind == "USV" else 2.8,
                    0.10 + distance * (0.035 if item.kind == "USV" else 0.08),
                )
                if distance <= 24.0:
                    # Full cruise beside a dense guard square makes the safety
                    # projection alternate sides of the slot.  Preserve the
                    # convoy's translation speed but damp only the remaining
                    # closing component as the craft reaches its station.
                    correction_speed = max(
                        0.18,
                        distance * (0.22 if item.kind == "USV" else 0.34),
                    )
                    speed = min(
                        follower_cap,
                        max(
                            correction_speed,
                            convoy_speed + min(closing_margin, 0.35),
                        ),
                    )
                else:
                    speed = min(follower_cap, max(speed, convoy_speed + closing_margin))
            if item.role == "CLOSE_GUARD":
                protected = self.protected[item.protected_index]
                protected_speed = _length(protected.vx, protected.vy)
                # A guard must be able to close on the moving convoy. The old
                # 0.66 cruise multiplier was slower than an evading protected
                # vessel, so guards drifted hundreds of metres away in 30+30.
                guard_cap = self.uav_cruise if item.kind == "UAV" else min(4.0, self.usv_cruise)
                speed = min(
                    guard_cap,
                    max(speed, protected_speed + min(0.8, 0.18 + distance * 0.035)),
                )
            if item.assigned_threat is not None:
                threat = self.threats[item.assigned_threat]
                target_speed = _length(threat.vx, threat.vy)
                gap_boost = item.role == "GAP_BLOCKER"
                closing_margin = min(
                    1.25 if item.kind == "USV" and gap_boost else 1.0 if item.kind == "USV" else 3.6 if gap_boost else 2.8,
                    (0.48 if gap_boost else 0.28) + distance * (0.032 if gap_boost else 0.025),
                )
                pursuit_cap = (
                    min(4.0, max(cruise, target_speed + 0.8))
                    if item.kind == "USV"
                    else cruise
                )
                speed = min(pursuit_cap, max(speed, target_speed + closing_margin))
                # Slow only at the final slot. Earlier deceleration is what
                # previously produced long queues behind a moving enemy.
                if threat.capture_stage >= 2 and distance < 10.0:
                    # Do not decelerate below the translating ring centre.  A
                    # small distance-proportional reserve closes the remaining
                    # angular error while the target is still moving.
                    settled_speed = speed * max(0.38, distance / 10.0)
                    follow_speed = target_speed + min(
                        0.55 if item.kind == "USV" else 1.2,
                        0.08 + distance * (0.075 if item.kind == "USV" else 0.12),
                    )
                    speed = min(pursuit_cap, max(settled_speed, follow_speed))
            elif distance < 12.0 and not convoy_follower:
                speed *= 0.45
            proposals[item.code] = (
                item.kind,
                self._move_towards((item.x, item.y, item.z), desired, max(0.018, speed * DT)),
            )
            physical_cap = self.uav_cruise if item.kind == "UAV" else (
                4.0
                if item.assigned_threat is not None
                or convoy_follower
                or item.role == "LOCAL_OVERWATCH"
                else self.usv_cruise + 0.049
            )
            step_limits[item.code] = physical_cap * DT
        fixed = {item.code: ("ESCORT_TARGET", (item.x, item.y, 0.0)) for item in self.protected}
        fixed.update({
            item.code: ("THREAT_TARGET", (item.x, item.y, 0.0))
            for item in self.threats
            if item.state not in {"WAITING", "ESCAPED"}
        })
        # Once every hostile is resolved and the strict rings are valid, keep
        # those rings authoritative while surplus craft return. Otherwise the
        # symmetric collision solver lets a passing support USV push one ring
        # member 3.5+ m off-slot and reopen an already completed containment.
        fixed.update({
            item.code: (item.kind, (item.x, item.y, item.z))
            for item in self.vehicles
            if item.code in locked_ring_codes
        })
        resolved = self.safety.resolve_group(proposals, self.previous, fixed)
        frames: list[AgentFrame] = []
        for item in self.vehicles:
            old = self.previous.get(item.code, (item.x, item.y, item.z))
            safe = resolved.get(item.code)
            current = (
                (item.x, item.y, item.z)
                if safe is None
                else (safe.x, safe.y, safe.z)
            )
            dx, dy = current[0] - item.x, current[1] - item.y
            displacement = _length(dx, dy)
            limit = step_limits.get(item.code, displacement)
            if displacement > limit > 0.0:
                current = (
                    item.x + dx * limit / displacement,
                    item.y + dy * limit / displacement,
                    current[2],
                )
            if safe is not None and safe.adjusted:
                self.avoidance_count += 1
            item.vx, item.vy = (current[0] - item.x) / DT, (current[1] - item.y) / DT
            item.x, item.y, item.z = current
            heading = self.stabilize_heading(item.code, old, current, 0.0, 4.5 if item.kind == "UAV" else 4.2)
            if item.kind == "USV" and item.assigned_threat is not None:
                threat = self.threats[item.assigned_threat]
                if threat.capture_stage >= 2:
                    members = self._capture_members(item.assigned_threat)
                    slots = self._capture_slots(members, threat)
                    center_x, center_y = self._capture_center(threat, members)
                    member_index = next(
                        (
                            index for index, member in enumerate(members)
                            if member.code == item.code
                        ),
                        None,
                    )
                    if member_index is not None:
                        expected = slots[member_index].point(
                            (center_x, center_y, 0.0)
                        )
                        slot_error = _length(
                            current[0] - expected[0],
                            current[1] - expected[1],
                        )
                        if slot_error <= 8.0:
                            inward_heading = math.degrees(math.atan2(
                                threat.y - current[1],
                                threat.x - current[0],
                            )) % 360.0
                            heading_delta = (
                                inward_heading - heading + 180.0
                            ) % 360.0 - 180.0
                            heading = (
                                heading
                                + max(-6.0, min(6.0, heading_delta))
                            ) % 360.0
                            self._stable_headings[item.code] = heading
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
            tolerance = (12.0, 7.0, 3.5)[min(2, threat.capture_stage)]
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
            largest_gap_index = max(
                range(len(angles)),
                key=lambda position: (
                    angles[(position + 1) % len(angles)] - angles[position]
                ) % (2.0 * math.pi),
            )
            threat.gap_center_angle = (
                angles[largest_gap_index]
                + max_gap * 0.5
            ) % (2.0 * math.pi)

            final_gap = maximum_capture_gap_deg(len(members))
            if threat.capture_stage >= 1 and max_gap_deg > final_gap + 0.5:
                angle_items = sorted(
                    (
                        math.atan2(item.y - threat.y, item.x - threat.x) % (2.0 * math.pi),
                        item,
                    )
                    for item in members
                )
                angular_gaps = [
                    (angle_items[(position + 1) % len(angle_items)][0] - angle_items[position][0])
                    % (2.0 * math.pi)
                    for position in range(len(angle_items))
                ]
                gap_index = max(range(len(angular_gaps)), key=angular_gaps.__getitem__)
                left = angle_items[gap_index][1]
                right = angle_items[(gap_index + 1) % len(angle_items)][1]
                left_other = angular_gaps[(gap_index - 1) % len(angular_gaps)]
                right_other = angular_gaps[(gap_index + 1) % len(angular_gaps)]
                threat.gap_filler_code = left.code if left_other <= right_other else right.code
                threat.gap_center_angle = (
                    angle_items[gap_index][0] + angular_gaps[gap_index] * 0.5
                ) % (2.0 * math.pi)
            elif max_gap_deg <= final_gap + 0.5:
                threat.gap_filler_code = ""

            # Contract only after the current ring is substantially formed.
            # Stage zero is predictive interception; later stages also demand
            # angular spread so a line/queue cannot be mistaken for a ring.
            pursuit_distance = self._pursuit_distance(threat)
            # A large parallel team can physically occupy every predictive
            # interception slot before a shoreline-constrained attacker has
            # travelled the legacy fixed pursuit distance.  In that case the
            # geometry, not an arbitrary odometer, should trigger the handoff.
            # Preserve a visible escape run (45% of the configured distance)
            # and require 90% slot arrival, so this cannot skip straight from
            # spawn to containment.
            formation_handoff_ready = (
                self._parallel_response_enabled
                and len(self.protected) > 1
                and arrival_ratio >= 0.90
                and pursuit_distance >= threat.required_pursuit_distance * 0.45
            )
            pursuit_complete = (
                threat.capture_stage >= 1
                or pursuit_distance >= threat.required_pursuit_distance
                or formation_handoff_ready
            )
            just_reached_pursuit = (
                pursuit_complete and threat.mission_stage in {"ESCAPE", "PURSUIT"}
            )
            forced_intercept_stage = just_reached_pursuit or threat.intercept_stage_frames > 0
            if just_reached_pursuit:
                threat.intercept_stage_frames = 2
            elif threat.intercept_stage_frames > 0:
                threat.intercept_stage_frames -= 1
            if not pursuit_complete:
                threat.mission_stage = (
                    "ESCAPE"
                    if self._pursuit_distance(threat) < threat.required_pursuit_distance * 0.35
                    else "PURSUIT"
                )
            elif forced_intercept_stage:
                # Expose the tactical hand-off before the first formation
                # stage can request a gap repair in the same simulation tick.
                threat.mission_stage = "INTERCEPT"
            elif threat.capture_stage == 0:
                threat.mission_stage = "INTERCEPT"
            elif threat.capture_stage >= 2:
                threat.mission_stage = "GAP_REPAIR"
            else:
                threat.mission_stage = "ENCIRCLEMENT"
            if threat.capture_stage == 0 and pursuit_complete and arrival_ratio >= 0.70:
                threat.capture_stage = 1
                threat.capture_hold = 0
                threat.mission_stage = "INTERCEPT" if forced_intercept_stage else "ENCIRCLEMENT"
                continue
            stage_two_gap = min(120.0, maximum_capture_gap_deg(len(members)) + 30.0)
            if threat.capture_stage == 1 and arrival_ratio >= 0.80 and max_gap_deg <= stage_two_gap + 1e-6:
                threat.capture_stage = 2
                threat.capture_hold = 0
                threat.mission_stage = "ENCIRCLEMENT"
                continue
            relative_speed = sum(_length(item.vx - threat.vx, item.vy - threat.vy) for item in members) / len(members)
            contract = assess_containment(
                [(item.x, item.y, item.z) for item in members],
                (threat.x, threat.y, 0.0),
                required_count=len(members),
                device_types=[item.kind for item in members],
                minimum_type_counts={"UAV": 1, "USV": 1},
                minimum_radius_m=18.0 if threat.capture_stage >= 2 else 13.5,
                maximum_radius_m=self._capture_radius_limit(members),
                maximum_radial_spread_m=5.25,
                minimum_pairwise_separation_m=7.1,
                participating=participating,
                # Sub-degree tolerance absorbs floating-point/one-tick
                # tracking error at the 4+5 asymmetric geometry boundary;
                # it does not permit a visually open sector.
                tolerance_deg=1.0,
            )
            slot_map = {
                item.code: RingSlot(
                    index=position,
                    angle=slot.angle,
                    radius=slot.radius,
                    altitude=slot.altitude,
                )
                for position, (item, slot) in enumerate(zip(members, slots))
            }
            canonical = assess_canonical_ring(
                [
                    RingMember(
                        item.code, item.kind, item.x, item.y, item.z,
                        self._stable_headings.get(item.code),
                    )
                    for item in members
                ],
                (threat.x, threat.y, 0.0),
                slot_map,
                slot_tolerance_m=3.5,
                minimum_separation_m=7.0,
                require_inward_usv_heading=True,
                usv_heading_tolerance_deg=3.0,
            )
            protected_clearance_ready = all(
                _length(threat.x - protected.x, threat.y - protected.y)
                >= CONTAINMENT_STANDOFF_M - 1.0
                for protected in self.protected
            )
            best_arrival = self._ring_best_arrival.get(index, 0.0)
            if canonical.ready or canonical.arrival_ratio > best_arrival + 0.02:
                self._ring_best_arrival[index] = canonical.arrival_ratio
                self._ring_stalled_frames[index] = 0
            elif threat.capture_stage >= 2:
                stalled = self._ring_stalled_frames.get(index, 0) + 1
                self._ring_stalled_frames[index] = stalled
                if stalled >= 120:
                    # Keep assignments stable during normal convergence. Only
                    # when real slot arrival has stopped improving do we rotate
                    # the entire canonical ring by a small deterministic
                    # fraction. This changes a safety-blocked path without
                    # reassigning craft every frame or relaxing completion.
                    slot_step = 2.0 * math.pi / max(3, len(members))
                    threat.capture_phase = (
                        threat.capture_phase + slot_step * 0.38196601125
                    ) % (2.0 * math.pi)
                    self._ring_slots.pop(index, None)
                    self._ring_replans[index] = self._ring_replans.get(index, 0) + 1
                    self._ring_stalled_frames[index] = 0
                    self._ring_best_arrival[index] = canonical.arrival_ratio
            final_ready = (
                threat.capture_stage >= 2
                and contract.ready
                and canonical.ready
                and protected_clearance_ready
                and relative_speed <= 4.5
            )
            if final_ready:
                threat.containment_stage_latched = True
                threat.containment_soft_failure_frames = 0
                threat.state = "CAPTURE_HOLD"
                threat.capture_hold = min(
                    CAPTURE_HOLD_FRAMES,
                    threat.capture_hold + 1,
                )
                threat.mission_stage = "STABLE_CONTAINMENT"
                if threat.capture_hold >= CAPTURE_HOLD_FRAMES:
                    threat.state, threat.vx, threat.vy = "CAPTURED", 0.0, 0.0
                    threat.captured_frame = self.sequence
            else:
                # Completion requires consecutive valid emitted frames. A
                # broken visual ring immediately cancels the confirmation hold.
                threat.containment_stage_latched = False
                threat.containment_soft_failure_frames = 0
                threat.capture_hold = 0
                if not pursuit_complete:
                    threat.state = "ESCAPE_PURSUIT"
                    threat.mission_stage = (
                        "ESCAPE"
                        if self._pursuit_distance(threat) < threat.required_pursuit_distance * 0.35
                        else "PURSUIT"
                    )
                else:
                    threat.state = "ENCIRCLING" if threat.capture_stage >= 1 else "INTERCEPTING"
                    threat.mission_stage = (
                        "GAP_REPAIR" if threat.capture_stage >= 2
                        else "ENCIRCLEMENT" if threat.capture_stage >= 1
                        else "INTERCEPT"
                    )

    def _escort_route_progress(self, item: _Protected) -> float:
        """Return progress from the real convoy start to its terminal gate.

        The previous metric used the left world boundary as its origin and then
        forced the terminal frame to 100%. A convoy that had physically covered
        only 34% of its route therefore appeared as 48% and jumped to 100% in a
        single frame. The same terminal gate now defines both the displayed
        route and the completion contract.
        """
        start_x = self.protected_start_x[item.code]
        gate_x = item.destination_x - PROTECTED_SAFE_GATE_OFFSET_M
        route_length = max(1.0, gate_x - start_x)
        return max(0.0, min(1.0, (item.x - start_x) / route_length))

    def _protected_reached_safe_gate(self, item: _Protected) -> bool:
        protected_index = self.protected.index(item)
        captured = [
            threat for threat in self.threats
            if threat.state in {"CAPTURED", "SECURED"}
        ]
        # Multi-protected targets move as one rigid convoy. Attackers may
        # retarget during the mission, so keying the final safety gate to each
        # threat's last protected_index can leave one convoy member with an
        # empty relevant set forever. Every hull must instead clear every
        # completed containment zone before the shared convoy may finish.
        relevant = (
            captured
            if len(self.protected) > 1
            else [
                threat for threat in captured
                if threat.protected_index == protected_index
            ]
        )
        safe_from_containment = (
            bool(relevant)
            and all(
                _length(item.x - threat.x, item.y - threat.y)
                >= TARGET_SEPARATION_M + 8.0
                for threat in relevant
            )
        )
        # Completed containment rings remain keep-out zones, but they no longer
        # permit a 34%-route early exit. The convoy must bypass them and reach
        # the same physical gate used by the progress metric.
        if self._escort_route_progress(item) < 1.0:
            return False
        if relevant and not safe_from_containment:
            return False
        if abs(item.y - item.destination_y) <= 24.0:
            return True
        return (
            safe_from_containment
            and abs(item.y - item.destination_y) <= 64.0
        )

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
        resolved = all(item.state in {"CAPTURED", "SECURED", "ESCAPED"} for item in self.threats)
        if resolved:
            self._redeploy_surplus_to_convoy()
        arrived = all(self._protected_reached_safe_gate(item) for item in self.protected)
        if resolved:
            self._consolidate_final_containment()
        if resolved and arrived:
            self._replan_final_convoy_support_formation()
        # Surplus members can be reassigned after one threat is captured. The
        # remaining 2+2 persistent ring needs several physical frames to close
        # its new slots; do not report mission success during that transition.
        # This keeps the terminal screenshot and WebGL state consistent with
        # the same geometric contract used to declare the capture itself.
        captured_rings_ready = True
        for threat_index, threat in enumerate(self.threats):
            if threat.state not in {"CAPTURED", "SECURED"}:
                continue
            if not bool(self._live_containment(threat_index)["ready"]):
                captured_rings_ready = False
                break
        post_formation = self._post_mission_formation_status()
        support_ready = bool(post_formation["ready"])
        if resolved and arrived and not support_ready:
            maximum_error = float(post_formation["maximumErrorM"])
            if maximum_error < self._post_mission_best_maximum_error - 0.5:
                self._post_mission_best_maximum_error = maximum_error
                self._post_mission_stalled_frames = 0
            else:
                self._post_mission_stalled_frames += 1
            if self._post_mission_stalled_frames >= 120:
                self._replan_stalled_convoy_support_formation()
                post_formation = self._post_mission_formation_status()
                support_ready = bool(post_formation["ready"])
        else:
            self._post_mission_stalled_frames = 0
        self._convoy_support_ready_frames = (
            self._convoy_support_ready_frames + 1
            if resolved and support_ready
            else 0
        )
        self._protected_arrival_ready = arrived
        self._captured_rings_ready = captured_rings_ready
        if not resolved:
            self._terminal_blocker = "THREATS_UNRESOLVED"
        elif not arrived:
            self._terminal_blocker = "PROTECTED_TARGET_NOT_SAFE"
        elif not captured_rings_ready:
            self._terminal_blocker = "CONTAINMENT_RECONFIGURING"
        elif not support_ready:
            blocker_code = str(post_formation["blockerCode"])
            self._terminal_blocker = (
                f"POST_MISSION_FORMATION:{blocker_code}"
                if blocker_code
                else "POST_MISSION_FORMATION"
            )
        elif self._convoy_support_ready_frames < POST_MISSION_STABLE_FRAMES:
            self._terminal_blocker = "POST_MISSION_STABILIZING"
        else:
            self._terminal_blocker = "NONE"
        if (
            self._terminal_status is None
            and resolved
            and arrived
            and captured_rings_ready
            and self._convoy_support_ready_frames >= POST_MISSION_STABLE_FRAMES
        ):
            self._terminal_status, self._terminal_reason = "COMPLETED", "all protected targets reached safety and all threats were resolved"
            self._terminal_blocker = "NONE"

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

    def _mission_stage(self) -> str:
        active = [item for item in self.threats if item.state not in {"WAITING", "CAPTURED", "SECURED", "ESCAPED"}]
        if self._terminal_status == "COMPLETED":
            return "COMPLETED"
        if active:
            stage_rank = {
                "ESCAPE": 0, "PURSUIT": 1, "INTERCEPT": 2,
                "ENCIRCLEMENT": 3, "GAP_REPAIR": 4,
                "STABLE_CONTAINMENT": 5,
            }
            # Report the earliest unresolved incident. Per-target cards still
            # show advanced incidents, while the global stepper can only move
            # forward once every live threat has crossed the phase boundary.
            return min(
                (item.mission_stage for item in active),
                key=lambda stage: stage_rank.get(stage, 0),
            )
        if any(item.state in {"CAPTURED", "SECURED"} for item in self.threats):
            return "STABLE_CONTAINMENT"
        return "ESCORTING"

    def _reported_stage(self) -> str:
        raw = self._mission_stage()
        # The global stepper describes the earliest unresolved incident, not
        # the most advanced ring ever observed.  A monotonic high-water latch
        # previously kept GAP_REPAIR visible when a later threat was still in
        # pursuit (and could even have 0+0 members). Per-threat containment
        # stages remain latched independently, so reporting the live minimum
        # here does not weaken any completion criterion.
        self._reported_mission_stage = raw
        return self._reported_mission_stage

    def step(self) -> RuntimeFrame:
        self.sequence += 1
        initial, self._initial_frame_pending = self._initial_frame_pending, False
        if initial:
            self._start_parallel_response()
        if not initial and self._terminal_status is None:
            self._advance_protected()
            self._retarget_attackers()
            self._advance_threats()
            self._synchronize_guard_roles()
            self._redeploy_surplus_to_convoy()
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
        containment = {
            index: self._live_containment(index)
            for index, threat in enumerate(self.threats)
            if threat.forced or threat.state in {"CAPTURED", "SECURED"}
        }
        visually_captured = {
            index for index, snapshot in containment.items()
            if self.threats[index].state in {"CAPTURED", "SECURED"}
            and bool(snapshot["ready"])
        }
        targets = [TargetFrame(item.code, "ESCORT_TARGET", item.x, item.y, 0.0, item.heading, True, f"GUARD-{i + 1:03d}", item.state, 0) for i, item in enumerate(self.protected)]
        targets.extend(TargetFrame(
            item.code, "THREAT_TARGET", item.x, item.y, 0.0, item.heading,
            item.state != "WAITING", f"CAPTURE-{i + 1:03d}",
            (
                item.state
                if item.state not in {"CAPTURED", "SECURED"} or i in visually_captured
                else "RECONFIGURING"
            ),
            3 if item.forced else 2 if item.detected_frame is not None else 1,
        ) for i, item in enumerate(self.threats))
        visible = [item for item in self.threats if item.state != "WAITING"]
        roles: dict[str, int] = {}
        for item in self.vehicles:
            roles[item.role] = roles.get(item.role, 0) + 1
        raw_escort_progress = sum(
            self._escort_route_progress(item)
            for item in self.protected
        ) / len(self.protected)
        # Avoid small backwards percentage changes while the convoy performs a
        # safety detour. This is presentation state only; terminal readiness is
        # always checked against the current physical positions above.
        self._display_escort_progress = max(
            self._display_escort_progress,
            raw_escort_progress,
        )
        escort_progress = self._display_escort_progress
        capture_values: list[float] = []
        capture_groups: list[dict[str, object]] = []
        for index, threat in enumerate(self.threats):
            snapshot = containment.get(index)
            members = self._capture_members(index) if snapshot is None else snapshot["members"]
            visual_ready = index in visually_captured
            if visual_ready:
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
            if not (threat.forced or threat.state in {"CAPTURED", "SECURED"}):
                # Keep the mission panel structurally complete from frame one.
                # An approaching attacker has no assigned ring yet, but it is
                # still one of the configured capture objectives and must not
                # disappear from the denominator or the target list.
                capture_groups.append({
                    "threatCode": threat.code,
                    "state": threat.state,
                    "missionStage": "APPROACH",
                    "stage": 0,
                    "memberCount": len(members),
                    "uavCount": sum(item.kind == "UAV" for item in members),
                    "usvCount": sum(item.kind == "USV" for item in members),
                    "arrivalRatio": 0.0,
                    "maxAngularGapDeg": 360.0,
                    "radialErrorM": None,
                    "holdFrames": 0,
                    "holdRequiredFrames": CAPTURE_HOLD_FRAMES,
                    "stableContainmentFrames": 0,
                    "stableContainmentRequiredFrames": CAPTURE_HOLD_FRAMES,
                    "pursuitDistanceM": 0.0,
                    "requiredPursuitDistanceM": round(threat.required_pursuit_distance, 2),
                    "pursuitProgress": 0.0,
                    "intent": threat.intent,
                    "triggerReason": threat.auto_capture_reason,
                    "gapFillerCode": "",
                    "gapCenterDeg": 0.0,
                    "interceptAttempts": threat.intercept_attempts,
                    "slotReplanCount": self._ring_replans.get(index, 0),
                })
            if threat.forced or threat.state in {"CAPTURED", "SECURED"}:
                assert snapshot is not None
                contract = snapshot["contract"]
                canonical_contract = snapshot["canonicalContract"]
                arrival_ratio = float(snapshot["arrivalRatio"])
                max_gap_deg = float(snapshot["maxGapDeg"])
                radial_error = float(snapshot["radialErrorM"])
                capture_groups.append({
                    "threatCode": threat.code,
                    "state": threat.state if visual_ready or threat.state not in {"CAPTURED", "SECURED"} else "RECONFIGURING",
                    "missionStage": threat.mission_stage if visual_ready or threat.state not in {"CAPTURED", "SECURED"} else "STABLE_CONTAINMENT",
                    "stage": threat.capture_stage,
                    "memberCount": len(members),
                    "uavCount": sum(item.kind == "UAV" for item in members),
                    "usvCount": sum(item.kind == "USV" for item in members),
                    "arrivalRatio": round(arrival_ratio, 3),
                    "maxAngularGapDeg": round(max_gap_deg, 2),
                    "radialErrorM": None if math.isinf(radial_error) else round(radial_error, 2),
                    "holdFrames": threat.capture_hold,
                    "holdRequiredFrames": CAPTURE_HOLD_FRAMES,
                    "stableContainmentFrames": threat.capture_hold,
                    "stableContainmentRequiredFrames": CAPTURE_HOLD_FRAMES,
                    "pursuitDistanceM": round(self._pursuit_distance(threat), 2),
                    "requiredPursuitDistanceM": round(threat.required_pursuit_distance, 2),
                    "pursuitProgress": round(min(1.0, self._pursuit_distance(threat) / max(1.0, threat.required_pursuit_distance)), 3),
                    "intent": threat.intent,
                    "triggerReason": threat.auto_capture_reason,
                    "gapFillerCode": threat.gap_filler_code,
                    "gapCenterDeg": round(math.degrees(threat.gap_center_angle) % 360.0, 2),
                    "interceptAttempts": threat.intercept_attempts,
                    "slotReplanCount": self._ring_replans.get(index, 0),
                    "containmentContract": {
                        "ready": bool(snapshot["ready"]),
                        "blocker": "NONE" if visual_ready else contract.blocker,
                        "maxGapDeg": round(max_gap_deg, 2),
                        "maxAllowedGapDeg": round(maximum_capture_gap_deg(len(members)), 2),
                        "arrivalRatio": round(arrival_ratio, 3),
                        "allMembersParticipating": arrival_ratio >= 1.0,
                        "sectorCount": contract.sector_count,
                        "coveredSectors": contract.covered_sectors,
                        "minimumSeparationM": contract.minimum_separation_m,
                        "requiredSeparationM": contract.required_separation_m,
                        "uavCount": contract.uav_count,
                        "usvCount": contract.usv_count,
                        "invalidParticipants": contract.invalid,
                        "stationaryParticipants": contract.stationary,
                        "detachedParticipants": contract.detached,
                    },
                    "canonicalContainmentContract": {
                        "ready": bool(canonical_contract.ready),
                        "blocker": canonical_contract.blocker,
                        "maxGapDeg": round(canonical_contract.maximum_gap_deg, 2),
                        "maxAllowedGapDeg": round(canonical_contract.allowed_gap_deg, 2),
                        "arrivalRatio": round(canonical_contract.arrival_ratio, 3),
                        "maximumSlotErrorM": round(canonical_contract.maximum_slot_error_m, 3),
                        "radialSpreadM": round(canonical_contract.radial_spread_m, 3),
                        "minimumSeparationM": round(canonical_contract.minimum_separation_m, 3),
                        "inwardOrientedUsvCount": canonical_contract.inward_oriented_usv_count,
                        "usvCount": canonical_contract.usv_count,
                        "maximumUsvHeadingErrorDeg": round(
                            canonical_contract.maximum_usv_heading_error_deg, 3
                        ),
                    },
                })
        capture_progress = sum(capture_values) / max(1, len(capture_values))
        post_formation = self._post_mission_formation_status()
        if self._terminal_status == "COMPLETED":
            capture_progress = 1.0
        overall_progress = escort_progress if self.capture_started_frame is None else escort_progress * 0.4 + capture_progress * 0.6
        reported_stage = self._reported_stage()
        # Keep the aggregate percentage consistent with the global stepper.
        # Averaging three completed rings with one early incident previously
        # produced 92% while the screen still (correctly) said PURSUIT.  The
        # cap is presentation-only; per-target progress and every completion
        # contract remain unchanged.
        stage_progress_ceiling = {
            "ESCAPE": 0.49,
            "PURSUIT": 0.69,
            "INTERCEPT": 0.79,
            "ENCIRCLEMENT": 0.89,
            "GAP_REPAIR": 0.97,
            "STABLE_CONTAINMENT": 0.999,
        }
        if self._terminal_status != "COMPLETED":
            overall_progress = min(
                overall_progress,
                stage_progress_ceiling.get(reported_stage, 0.999),
            )
        # Keep the user-facing mission progress monotonic. Temporary
        # containment repairs are reflected by the stage and blocker fields,
        # not by making the completion percentage move backward.
        self._display_progress = max(
            getattr(self, "_display_progress", 0.0),
            min(0.999, overall_progress) if self._terminal_status != "COMPLETED" else 1.0,
        )
        capture_elapsed = 0 if self.capture_started_frame is None else max(0, self.sequence - self.capture_started_frame)
        current_threat_distances = [
            self._distance_to_protected(item)
            for item in self.threats
            if item.state not in {"WAITING", "ESCAPED"}
        ]
        moving_threats = [item for item in self.threats if item.state not in {"WAITING", "ESCAPED"}]
        unresolved_threats = [
            item for item in self.threats
            if item.state not in {"WAITING", "CAPTURED", "SECURED", "ESCAPED"}
        ]
        stage_rank = {
            "ESCAPE": 0, "PURSUIT": 1, "INTERCEPT": 2,
            "ENCIRCLEMENT": 3, "GAP_REPAIR": 4,
            "STABLE_CONTAINMENT": 5,
        }
        stage_subject = min(
            unresolved_threats,
            key=lambda item: (stage_rank.get(item.mission_stage, 0), item.code),
            default=None,
        )
        close_guard_count = sum(item.role == "CLOSE_GUARD" for item in self.vehicles)
        capture_assigned_count = sum(item.assigned_threat is not None for item in self.vehicles)
        mobile_support_count = len(self.vehicles) - close_guard_count - capture_assigned_count
        metrics = {
            "scenarioPlan": self.plan.to_dict(), "protectedCount": self.plan.protected_count,
            "threatCount": self.plan.threat_count, "visibleThreatCount": len(visible),
            "capturedThreatCount": len(visually_captured),
            "escapedThreatCount": sum(item.state == "ESCAPED" for item in self.threats),
            "simultaneousThreatLimit": self.plan.simultaneous_threats, "avoidanceCount": self.avoidance_count,
            "parallelResponseEnabled": self._parallel_response_enabled,
            "parallelResponseStarted": self._parallel_response_started,
            "roles": roles,
            "closeGuardCount": close_guard_count,
            "captureAssignedCount": capture_assigned_count,
            "mobileSupportCount": mobile_support_count,
            "unresolvedThreatCount": len(unresolved_threats),
            "stageSubjectThreatCode": None if stage_subject is None else stage_subject.code,
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
            "firstLineBreachCount": sum(item.breach_until_frame > 0 for item in self.threats),
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
            "missionProgress": round(self._display_progress, 3),
            "progress": round(self._display_progress, 3),
            "captureElapsedFrames": capture_elapsed,
            "convoySupportCount": len(self._convoy_support_members()),
            "convoySupportReady": self._convoy_support_ready(),
            "localOverwatchCount": len(self._post_watch_members()),
            "postMissionFormationReady": bool(post_formation["ready"]),
            "postMissionFormationReadyCount": int(post_formation["readyCount"]),
            "postMissionFormationRequiredCount": int(post_formation["requiredCount"]),
            "postMissionFormationProgress": round(float(post_formation["progress"]), 3),
            "postMissionFormationMaximumErrorM": round(float(post_formation["maximumErrorM"]), 3),
            "postMissionFormationBlockerCode": str(post_formation["blockerCode"]),
            "postMissionSlotReplanCount": self._post_mission_slot_replans,
            "convoySupportStableFrames": self._convoy_support_ready_frames,
            "convoySupportRequiredStableFrames": POST_MISSION_STABLE_FRAMES,
            "protectedArrivalReady": self._protected_arrival_ready,
            "capturedRingsReady": self._captured_rings_ready,
            "terminalBlocker": self._terminal_blocker,
            "simulationElapsedSeconds": round(max(0, self.sequence - 1) * DT, 1),
            "captureGroups": capture_groups,
            "missionStage": reported_stage,
            "stageSequence": ["ESCAPE", "PURSUIT", "INTERCEPT", "ENCIRCLEMENT", "GAP_REPAIR", "STABLE_CONTAINMENT", "COMPLETED"],
            "terminalReason": self._terminal_reason,
            "worldBounds": list(self.safe_bounds),
        }
        return RuntimeFrame(
            self.run_id, self.code, self.sequence, int(time.time() * 1000), self._phase(),
            agents, targets, metrics, route=[], obstacles=[], terminalStatus=self._terminal_status,
        )
