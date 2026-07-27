"""Interactive 2D maritime escort/guard simulation.

The standalone program models a mixed team of six UAVs and four USVs around
an escorted maritime target.  In the interactive window, a left mouse click
places the enemy at that exact world coordinate (subject only to a small
minimum safety radius around the escorted target).  One platform is pinned to
an interior point of the own-target/enemy line segment on every active frame,
three nearby platforms form a compact threat-facing arc, and all remaining
platforms are reassigned to a minimum-travel escort arc without crossing the
escorted target.

Run interactively and click the sea area to place the enemy::

    python 护航守卫2_鼠标点击版.py

Run a headless verification/snapshot with a legacy initial direction::

    MPLBACKEND=Agg python 护航守卫2_鼠标点击版.py \
        --scene front_left --headless-frames 50 --save-snapshot snapshot.png
"""
from __future__ import annotations

import argparse
import itertools
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

EPS = 1e-12
SCENES: Tuple[str, ...] = (
    "front",
    "front_right",
    "right",
    "back_right",
    "back",
    "back_left",
    "left",
    "front_left",
)
SCENE_LABELS: Dict[str, str] = {
    "front": "正前方",
    "front_right": "右前方",
    "right": "正右方",
    "back_right": "右后方",
    "back": "正后方",
    "back_left": "左后方",
    "left": "正左方",
    "front_left": "左前方",
}
def normalize(v: np.ndarray, fallback: np.ndarray | None = None) -> np.ndarray:
    """Return a unit vector, or a normalized fallback for a zero vector."""
    arr = np.asarray(v, dtype=float)
    norm = float(np.linalg.norm(arr))
    if norm <= EPS:
        if fallback is None:
            return np.zeros_like(arr)
        fb = np.asarray(fallback, dtype=float)
        fb_norm = float(np.linalg.norm(fb))
        return fb / fb_norm if fb_norm > EPS else np.zeros_like(arr)
    return arr / norm


def rotate90(v: np.ndarray) -> np.ndarray:
    """Rotate a 2-D vector 90 degrees counter-clockwise."""
    arr = np.asarray(v, dtype=float)
    return np.array([-arr[1], arr[0]], dtype=float)


def local_direction(scene: str, forward: np.ndarray) -> np.ndarray:
    """Return an eight-way threat direction relative to ``forward``."""
    if scene not in SCENES:
        raise ValueError(f"Unknown scene {scene!r}; expected one of {SCENES}")
    fwd = normalize(forward, np.array([1.0, 0.0]))
    left = rotate90(fwd)
    mapping = {
        "front": fwd,
        "front_right": normalize(fwd - left),
        "right": -left,
        "back_right": normalize(-fwd - left),
        "back": -fwd,
        "back_left": normalize(-fwd + left),
        "left": left,
        "front_left": normalize(fwd + left),
    }
    return mapping[scene]


def threat_label(scene: str) -> str:
    """Return the Chinese label for an eight-way threat scene."""
    try:
        return SCENE_LABELS[scene]
    except KeyError as exc:
        raise ValueError(f"Unknown scene {scene!r}") from exc


def compute_blocker_point(
    own: np.ndarray,
    enemy: np.ndarray,
    ratio: float = 0.38,
    r_min: float = 2.2,
    r_max: float = 4.0,
    fallback_direction: np.ndarray | None = None,
) -> Tuple[np.ndarray, float]:
    """Return a strict interior blocker point and line parameter ``t``.

    For non-coincident targets, the result is ``own + t*(enemy-own)`` with
    ``0 < t < 1``.  If the enemy is closer than ``r_min``, the radius is
    compressed to stay just inside the segment.  Coincident targets use a
    virtual unit segment along ``fallback_direction`` because an actual line
    segment does not exist in that degenerate case.
    """
    if not (0.0 < ratio < 1.0):
        raise ValueError("ratio must be in (0, 1)")
    if not (0.0 <= r_min <= r_max):
        raise ValueError("expected 0 <= r_min <= r_max")

    own = np.asarray(own, dtype=float)
    enemy = np.asarray(enemy, dtype=float)
    delta = enemy - own
    distance = float(np.linalg.norm(delta))
    if distance <= EPS:
        direction = normalize(
            np.array([1.0, 0.0]) if fallback_direction is None else fallback_direction,
            np.array([1.0, 0.0]),
        )
        distance = 1.0
        delta = direction

    requested = float(np.clip(ratio * distance, r_min, r_max))
    strict_lower = distance * 1e-9
    strict_upper = distance * (1.0 - 1e-9)
    radius = min(max(strict_lower, requested), strict_upper)
    t = radius / distance
    point = own + t * delta
    return point, float(t)


@dataclass
class Platform:
    """A UAV or USV in the mixed escort team."""

    identifier: str
    kind: str
    position: np.ndarray
    max_speed: float
    gain: float
    role: str = "escort"
    goal: Optional[np.ndarray] = None

    def move_toward(self, goal: np.ndarray, dt: float = 1.0) -> None:
        """Move toward ``goal`` using proportional control and a speed cap."""
        goal = np.asarray(goal, dtype=float)
        velocity = self.gain * (goal - self.position)
        speed = float(np.linalg.norm(velocity))
        if speed > self.max_speed:
            velocity = velocity * (self.max_speed / (speed + EPS))
        self.position = self.position + velocity * dt
        self.goal = goal.copy()


class EscortGuardSimulator:
    """Mixed UAV/USV maritime escort controller and 2-D kinematic simulation."""

    def __init__(
        self,
        scene: str = "front",
        avoidance_mode: str = "auto",
        *,
        threat_active: bool = True,
        seed: int = 42,
        num_uav: int = 6,
        num_usv: int = 6,
        total_forward_guards: int = 5,
        ring_radius: float = 4,
        guard_arc_radius: float = 5.2,
        guard_arc_half_angle_deg: float = 28.0,
        minimum_guard_spacing: float = 1.15,
        enemy_distance: float = 10.5,
        minimum_enemy_click_distance: float = 3.0,
        blocker_ratio: float = 0.38,
        blocker_r_min: float = 2.2,
        blocker_r_max: float = 4.0,
        avoid_distance: float = 4.8,
        forward_shift: float = 2.2,
        own_max_speed: float = 0.12,
        own_gain: float = 0.10,
        cruise_speed: float = 0.025,
        safe_distance: float = 0.75,
        repulsion_gain: float = 0.025,
        escort_inner_radius: float = 1.25,
        escort_clearance_deg: float = 20.0,
        dt: float = 1.0,
    ) -> None:
        if scene not in SCENES:
            raise ValueError(f"Unknown scene {scene!r}")
        if avoidance_mode not in {"auto", "left", "right"}:
            raise ValueError("avoidance_mode must be auto, left, or right")
        if num_uav < 0 or num_usv < 0 or num_uav + num_usv < 1:
            raise ValueError("At least one platform is required")
        if total_forward_guards < 1:
            raise ValueError("At least one forward guard is required")

        self.seed = int(seed)
        self.rng = np.random.default_rng(self.seed)
        self.num_uav = int(num_uav)
        self.num_usv = int(num_usv)
        self.total_forward_guards = min(
            int(total_forward_guards), self.num_uav + self.num_usv
        )
        self.ring_radius = float(ring_radius)
        self.guard_arc_radius = float(guard_arc_radius)
        if self.guard_arc_radius <= 0.0:
            raise ValueError("guard_arc_radius must be positive")
        self.guard_arc_half_angle = math.radians(float(guard_arc_half_angle_deg))
        if not (0.0 <= self.guard_arc_half_angle < math.pi):
            raise ValueError("guard_arc_half_angle_deg must be in [0, 180)")
        self.minimum_guard_spacing = float(minimum_guard_spacing)
        if self.minimum_guard_spacing < 0.0:
            raise ValueError("minimum_guard_spacing must be non-negative")
        if self.minimum_guard_spacing > 2.0 * self.guard_arc_radius:
            raise ValueError(
                "minimum_guard_spacing cannot exceed the guard arc diameter"
            )
        self.enemy_distance = float(enemy_distance)
        self.minimum_enemy_click_distance = float(minimum_enemy_click_distance)
        if self.minimum_enemy_click_distance <= 0.0:
            raise ValueError("minimum_enemy_click_distance must be positive")
        self.blocker_ratio = float(blocker_ratio)
        self.blocker_r_min = float(blocker_r_min)
        self.blocker_r_max = float(blocker_r_max)
        self.avoid_distance = float(avoid_distance)
        self.forward_shift = float(forward_shift)
        self.own_max_speed = float(own_max_speed)
        self.own_gain = float(own_gain)
        self.cruise_speed = float(cruise_speed)
        self.safe_distance = float(safe_distance)
        self.repulsion_gain = float(repulsion_gain)
        self.escort_inner_radius = float(escort_inner_radius)
        if self.escort_inner_radius <= 0.0:
            raise ValueError("escort_inner_radius must be positive")
        self.escort_clearance = math.radians(float(escort_clearance_deg))
        if not (0.0 <= self.escort_clearance < math.pi / 2.0):
            raise ValueError("escort_clearance_deg must be in [0, 90)")
        self.dt = float(dt)

        self.forward = np.array([1.0, 0.0], dtype=float)
        self.own_position = np.zeros(2, dtype=float)
        self.own_goal = self.own_position.copy()
        self.scene = scene
        self.avoidance_mode = avoidance_mode
        self.avoid_direction = np.zeros(2, dtype=float)
        self.enemy_position = self.own_position + local_direction(scene, self.forward) * self.enemy_distance
        self.threat_active = False
        self.paused = False
        self.frame = 0
        self.reset_count = 0
        self.phase = "正常护航"
        self.emergency_deployment = False

        self.platforms: List[Platform] = self._create_mixed_ring()
        self.core_guard_index: Optional[int] = None
        self.wing_guard_indices: List[int] = []
        self._wing_slot_by_index: Dict[int, int] = {}
        # Non-guard platforms are assigned once to a compact escort arc.
        # Anchors preserve each platform's original half-plane, while slot
        # offsets define the minimum-distance target formation.
        self._escort_anchor_by_index: Dict[int, np.ndarray] = {}
        self._escort_slot_by_index: Dict[int, int] = {}
        self._escort_slot_offsets: Dict[int, np.ndarray] = {}
        self._escort_goal_offsets: List[np.ndarray] = []
        self._blocker_point = self.own_position.copy()
        self._blocker_t = math.nan

        if threat_active:
            self.activate_threat(scene)

    @property
    def forward_guard_indices(self) -> List[int]:
        result: List[int] = []
        if self.core_guard_index is not None:
            result.append(self.core_guard_index)
        result.extend(self.wing_guard_indices)
        return result

    @property
    def blocker_point(self) -> np.ndarray:
        return self._blocker_point.copy()

    def _create_mixed_ring(self) -> List[Platform]:
        """Create six UAVs and four USVs interleaved around a ring by default."""
        kinds: List[str] = []
        remaining_uav, remaining_usv = self.num_uav, self.num_usv
        prefer_uav = True
        while remaining_uav + remaining_usv:
            if prefer_uav and remaining_uav > 0 or remaining_usv == 0:
                kinds.append("UAV")
                remaining_uav -= 1
            else:
                kinds.append("USV")
                remaining_usv -= 1
            prefer_uav = not prefer_uav

        rotation = float(self.rng.uniform(-0.10, 0.10))
        angles = np.linspace(0.0, 2.0 * math.pi, len(kinds), endpoint=False) + rotation
        uav_no = usv_no = 0
        platforms: List[Platform] = []
        for angle, kind in zip(angles, kinds):
            position = self.own_position + self.ring_radius * np.array(
                [math.cos(angle), math.sin(angle)], dtype=float
            )
            if kind == "UAV":
                uav_no += 1
                identifier = f"U{uav_no}"
                max_speed, gain = 0.28, 0.24
            else:
                usv_no += 1
                identifier = f"S{usv_no}"
                max_speed, gain = 0.15, 0.14
            platforms.append(
                Platform(
                    identifier=identifier,
                    kind=kind,
                    position=position,
                    max_speed=max_speed,
                    gain=gain,
                )
            )
        return platforms

    def _threat_geometry(self) -> Tuple[np.ndarray, np.ndarray, float]:
        delta = self.enemy_position - self.own_position
        distance = float(np.linalg.norm(delta))
        direction = normalize(delta, local_direction(self.scene, self.forward))
        return delta, direction, distance

    def _refresh_blocker_point(self) -> None:
        self._blocker_point, self._blocker_t = compute_blocker_point(
            self.own_position,
            self.enemy_position,
            ratio=self.blocker_ratio,
            r_min=self.blocker_r_min,
            r_max=self.blocker_r_max,
            fallback_direction=local_direction(self.scene, self.forward),
        )

    def _resolve_avoid_direction(self) -> np.ndarray:
        left = rotate90(normalize(self.forward, np.array([1.0, 0.0])))
        if self.avoidance_mode == "left":
            return left
        if self.avoidance_mode == "right":
            return -left
        _, threat_dir, _ = self._threat_geometry()
        lateral = float(np.dot(threat_dir, left))
        if lateral > 0.15:
            return -left  # threat on left -> avoid right
        if lateral < -0.15:
            return left   # threat on right -> avoid left
        return -left      # front/back -> stable default: right

    def _update_avoidance_goal(self) -> None:
        self.avoid_direction = self._resolve_avoid_direction()
        self.own_goal = (
            self.own_position
            + self.avoid_distance * self.avoid_direction
            + self.forward_shift * normalize(self.forward, np.array([1.0, 0.0]))
        )

    def activate_threat(self, scene: Optional[str] = None) -> None:
        """Activate a legacy eight-way threat for CLI/headless operation."""
        if scene is not None:
            if scene not in SCENES:
                raise ValueError(f"Unknown scene {scene!r}")
            self.scene = scene
        direction = local_direction(self.scene, self.forward)
        target = self.own_position + direction * self.enemy_distance
        self.activate_threat_at(target)

    def activate_threat_at(self, position: np.ndarray) -> np.ndarray:
        """Place the enemy at a continuous world coordinate and replan.

        A click outside ``minimum_enemy_click_distance`` is preserved exactly.
        A click inside that radius is projected radially outward.  A click at
        the escorted target itself uses the current forward direction as a
        deterministic fallback.  The returned array is the actual placed
        coordinate after this safety projection.
        """
        requested = np.asarray(position, dtype=float)
        if requested.shape != (2,) or not np.all(np.isfinite(requested)):
            raise ValueError("position must be a finite two-dimensional coordinate")

        delta = requested - self.own_position
        distance = float(np.linalg.norm(delta))
        direction = normalize(delta, normalize(self.forward, np.array([1.0, 0.0])))
        if distance < self.minimum_enemy_click_distance:
            requested = self.own_position + direction * self.minimum_enemy_click_distance

        self.enemy_position = requested.copy()
        self.threat_active = True
        self.phase = "鼠标指定威胁，紧急阻断部署"
        self.emergency_deployment = True
        self._refresh_blocker_point()
        self._replan_guards()
        self._update_avoidance_goal()
        self._enforce_core_blocker()
        return self.enemy_position.copy()

    def set_threat_scene(self, scene: str) -> None:
        """Switch to a legacy eight-way threat direction and redeploy."""
        self.activate_threat(scene)

    def threat_bearing_label(self) -> str:
        """Describe the actual continuous enemy bearing relative to heading."""
        if not self.threat_active:
            return "未放置（请左键点击海面）"
        _, direction, _ = self._threat_geometry()
        fwd = normalize(self.forward, np.array([1.0, 0.0]))
        left = rotate90(fwd)
        angle = math.degrees(
            math.atan2(float(np.dot(direction, left)), float(np.dot(direction, fwd)))
        )
        if angle < 0.0:
            angle += 360.0
        sector = int(((angle + 22.5) % 360.0) // 45.0)
        labels = (
            "正前方", "左前方", "正左方", "左后方",
            "正后方", "右后方", "正右方", "右前方",
        )
        return f"{labels[sector]}（{angle:.1f}°）"

    def set_avoidance_mode(self, mode: str) -> None:
        if mode not in {"auto", "left", "right"}:
            raise ValueError("mode must be auto, left, or right")
        self.avoidance_mode = mode
        if self.threat_active:
            self._update_avoidance_goal()

    def toggle_pause(self) -> bool:
        self.paused = not self.paused
        return self.paused

    def reset(self) -> None:
        """Reinitialize the mixed ring and preserve the current clicked threat."""
        was_active = self.threat_active
        previous_enemy = self.enemy_position.copy()
        self.reset_count += 1
        self.rng = np.random.default_rng(self.seed + self.reset_count)
        self.own_position = np.zeros(2, dtype=float)
        self.own_goal = self.own_position.copy()
        self.platforms = self._create_mixed_ring()
        self.core_guard_index = None
        self.wing_guard_indices = []
        self._wing_slot_by_index = {}
        self._escort_anchor_by_index = {}
        self._escort_slot_by_index = {}
        self._escort_slot_offsets = {}
        self._escort_goal_offsets = []
        self.frame = 0
        self.paused = False
        self.phase = "正常护航"
        self.threat_active = False
        self.enemy_position = self.own_position + local_direction(self.scene, self.forward) * self.enemy_distance
        if was_active:
            self.activate_threat_at(previous_enemy)

    def _nearest_forward_candidates(self) -> List[int]:
        """Select the platforms currently nearest to the enemy target.

        Selection is performed once when a threat is activated or switched.
        The selected set is then kept stable so that platforms do not swap
        roles repeatedly while the formation is moving.
        """
        ranked = sorted(
            range(len(self.platforms)),
            key=lambda index: float(
                np.linalg.norm(self.platforms[index].position - self.enemy_position)
            ),
        )
        return ranked[: self.total_forward_guards]

    def _select_core_guard(self, candidates: Optional[Sequence[int]] = None) -> int:
        """Choose the selected forward platform closest to the blocker point."""
        pool = list(range(len(self.platforms))) if candidates is None else list(candidates)
        if not pool:
            raise RuntimeError("No candidate is available for the core guard")
        return min(
            pool,
            key=lambda index: (
                float(np.linalg.norm(self.platforms[index].position - self._blocker_point)),
                index,
            ),
        )

    def _effective_guard_arc_half_angle(self, wing_count: int) -> float:
        """Return the tightest safe half-angle for ``wing_count`` arc guards.

        The configured half-angle controls compactness.  When that angle would
        place adjacent target slots closer than ``minimum_guard_spacing``, the
        arc expands only as much as required to preserve the safety distance.
        """
        if wing_count <= 1:
            return 0.0
        if self.minimum_guard_spacing <= EPS:
            return self.guard_arc_half_angle
        ratio = self.minimum_guard_spacing / (2.0 * self.guard_arc_radius)
        ratio = float(np.clip(ratio, 0.0, 1.0))
        minimum_step = 2.0 * math.asin(ratio)
        minimum_half_angle = 0.5 * (wing_count - 1) * minimum_step
        return max(self.guard_arc_half_angle, minimum_half_angle)

    def _wing_goals(self) -> List[np.ndarray]:
        """Generate a compact threat-facing arc with safe adjacent spacing."""
        wing_count = max(0, self.total_forward_guards - 1)
        if wing_count == 0:
            return []
        _, threat_dir, _ = self._threat_geometry()
        lateral = rotate90(threat_dir)
        half_angle = self._effective_guard_arc_half_angle(wing_count)
        if wing_count == 1:
            angles: Iterable[float] = [0.0]
        else:
            angles = np.linspace(-half_angle, half_angle, wing_count)
        return [
            self.own_position
            + self.guard_arc_radius
            * (math.cos(phi) * threat_dir + math.sin(phi) * lateral)
            for phi in angles
        ]

    def _select_and_assign_wings(self, candidates: Sequence[int]) -> None:
        """Assign already-selected nearby guards to arc slots by minimum distance."""
        goals = self._wing_goals()
        count = min(len(goals), len(candidates))
        if count == 0:
            self.wing_guard_indices = []
            self._wing_slot_by_index = {}
            return
        goals = goals[:count]

        best_cost = math.inf
        best_assignment: Optional[Tuple[int, ...]] = None
        for selected in itertools.permutations(candidates, count):
            cost = sum(
                float(np.linalg.norm(self.platforms[index].position - goals[slot]))
                for slot, index in enumerate(selected)
            )
            if cost < best_cost - EPS:
                best_cost = cost
                best_assignment = selected

        assert best_assignment is not None
        self.wing_guard_indices = list(best_assignment)
        self._wing_slot_by_index = {
            index: slot for slot, index in enumerate(best_assignment)
        }

    def _generate_escort_goal_offsets(self, count: int) -> List[np.ndarray]:
        """Generate a compact escort arc outside the threat-facing sector."""
        if count <= 0:
            return []
        _, threat_dir, _ = self._threat_geometry()
        lateral = rotate90(threat_dir)
        start = self.guard_arc_half_angle + self.escort_clearance
        end = 2.0 * math.pi - self.guard_arc_half_angle - self.escort_clearance
        if count == 1:
            angles: Iterable[float] = [(start + end) / 2.0]
        else:
            angles = np.linspace(start, end, count)
        return [
            self.ring_radius
            * (math.cos(phi) * threat_dir + math.sin(phi) * lateral)
            for phi in angles
        ]

    def _escort_goals(self) -> List[np.ndarray]:
        """Return current absolute escort-slot positions in slot order."""
        return [self.own_position + offset for offset in self._escort_goal_offsets]

    def _assign_escort_slots(self) -> None:
        """Minimize total re-formation distance without crossing own target.

        The straight-line motion of every escort member is constrained to a
        half-plane defined by its position when the threat is detected.  For
        equal-radius formations, a positive dot product between the current
        and destination relative vectors also keeps the connecting segment
        away from the escorted target's center.
        """
        escort_indices = [
            index
            for index in range(len(self.platforms))
            if index not in self.forward_guard_indices
        ]
        self._escort_anchor_by_index = {
            index: (self.platforms[index].position - self.own_position).copy()
            for index in escort_indices
        }
        self._escort_goal_offsets = self._generate_escort_goal_offsets(
            len(escort_indices)
        )
        self._escort_slot_by_index = {}
        self._escort_slot_offsets = {}
        if not escort_indices:
            return

        best_cost = math.inf
        best_assignment: Optional[Tuple[int, ...]] = None
        for assignment in itertools.permutations(escort_indices):
            total = 0.0
            feasible = True
            for slot, index in enumerate(assignment):
                anchor = self._escort_anchor_by_index[index]
                offset = self._escort_goal_offsets[slot]
                if float(np.dot(anchor, offset)) <= EPS:
                    feasible = False
                    break
                goal = self.own_position + offset
                total += float(
                    np.linalg.norm(self.platforms[index].position - goal)
                )
            if feasible and total < best_cost - EPS:
                best_cost = total
                best_assignment = assignment

        if best_assignment is None:
            # Defensive fallback for unusual team sizes: choose the assignment
            # with the smallest distance plus a large center-crossing penalty.
            for assignment in itertools.permutations(escort_indices):
                total = 0.0
                for slot, index in enumerate(assignment):
                    anchor = self._escort_anchor_by_index[index]
                    offset = self._escort_goal_offsets[slot]
                    crossing_penalty = 1e6 if float(np.dot(anchor, offset)) <= EPS else 0.0
                    goal = self.own_position + offset
                    total += crossing_penalty + float(
                        np.linalg.norm(self.platforms[index].position - goal)
                    )
                if total < best_cost - EPS:
                    best_cost = total
                    best_assignment = assignment

        assert best_assignment is not None
        for slot, index in enumerate(best_assignment):
            self._escort_slot_by_index[index] = slot
            self._escort_slot_offsets[index] = self._escort_goal_offsets[slot].copy()

    def _replan_guards(self) -> None:
        """Plan nearest forward guards and minimum-movement escort slots."""
        for platform in self.platforms:
            platform.role = "escort"

        nearest = self._nearest_forward_candidates()
        self.core_guard_index = self._select_core_guard(nearest)
        self.platforms[self.core_guard_index].role = "core"

        wing_candidates = [index for index in nearest if index != self.core_guard_index]
        self._select_and_assign_wings(wing_candidates)
        for index in self.wing_guard_indices:
            self.platforms[index].role = "wing"

        self._assign_escort_slots()

    def _normal_ring_goals(self) -> List[np.ndarray]:
        count = len(self.platforms)
        return [
            self.own_position
            + self.ring_radius
            * np.array([math.cos(phi), math.sin(phi)], dtype=float)
            for phi in np.linspace(0.0, 2.0 * math.pi, count, endpoint=False)
        ]

    def _desired_goals(self) -> Dict[int, np.ndarray]:
        if not self.threat_active:
            return {i: goal for i, goal in enumerate(self._normal_ring_goals())}

        result: Dict[int, np.ndarray] = {}
        wing_goals = self._wing_goals()
        for index, slot in self._wing_slot_by_index.items():
            if slot < len(wing_goals):
                result[index] = wing_goals[slot]

        # Remaining platforms move to the precomputed escort slots.  The
        # assignment is fixed for the current threat response, so the group
        # reforms once with minimum total travel and then translates with the
        # escorted target without repeated role or slot swapping.
        for index, offset in self._escort_slot_offsets.items():
            result[index] = self.own_position + offset
        return result

    def _move_own_target(self) -> None:
        velocity = self.own_gain * (self.own_goal - self.own_position)
        speed = float(np.linalg.norm(velocity))
        if speed > self.own_max_speed:
            velocity *= self.own_max_speed / (speed + EPS)
        self.own_position = self.own_position + velocity * self.dt
        if float(np.linalg.norm(self.own_goal - self.own_position)) < 0.10:
            # Continue progressing along the planned heading after the lateral
            # maneuver has essentially completed.
            self.own_goal = self.own_goal + normalize(self.forward) * self.cruise_speed

    def _repulsion_velocity(self, index: int) -> np.ndarray:
        if index == self.core_guard_index:
            return np.zeros(2, dtype=float)
        current = self.platforms[index].position
        repulsion = np.zeros(2, dtype=float)
        for other_index, other in enumerate(self.platforms):
            if other_index == index:
                continue
            diff = current - other.position
            distance = float(np.linalg.norm(diff))
            if EPS < distance < self.safe_distance:
                repulsion += (
                    self.repulsion_gain
                    * (1.0 / distance - 1.0 / self.safe_distance)
                    * diff
                    / distance
                )
        return repulsion

    def _preserve_escort_side(self, index: int, proposed: np.ndarray) -> np.ndarray:
        """Keep a non-guard platform on its original side of the own target.

        The anchor defines a half-plane through the escorted target.  A
        proposed step is projected back into that half-plane and outside a
        small central exclusion radius, which prevents crossing through the
        escorted target during formation adjustment.
        """
        anchor = self._escort_anchor_by_index.get(index)
        if anchor is None:
            return proposed
        anchor_unit = normalize(anchor, np.array([1.0, 0.0]))
        relative = np.asarray(proposed, dtype=float) - self.own_position
        radius = float(np.linalg.norm(relative))
        signed = float(np.dot(relative, anchor_unit))

        if signed <= EPS:
            relative = anchor_unit * max(self.escort_inner_radius, radius)
        elif radius < self.escort_inner_radius:
            relative = normalize(relative, anchor_unit) * self.escort_inner_radius

        # Numerical guard: retain a strictly positive projection.
        if float(np.dot(relative, anchor_unit)) <= EPS:
            relative = anchor_unit * max(self.escort_inner_radius, float(np.linalg.norm(relative)))
        return self.own_position + relative

    def _move_non_core_platforms(self, goals: Dict[int, np.ndarray]) -> None:
        next_positions: Dict[int, np.ndarray] = {}
        for index, platform in enumerate(self.platforms):
            if index == self.core_guard_index:
                continue
            goal = goals.get(index, platform.position)
            velocity = platform.gain * (goal - platform.position)
            velocity += self._repulsion_velocity(index)
            speed = float(np.linalg.norm(velocity))
            if speed > platform.max_speed:
                velocity *= platform.max_speed / (speed + EPS)
            proposed = platform.position + velocity * self.dt
            if platform.role == "escort":
                proposed = self._preserve_escort_side(index, proposed)
            next_positions[index] = proposed
            platform.goal = np.asarray(goal, dtype=float).copy()
        for index, position in next_positions.items():
            self.platforms[index].position = position

    def _enforce_core_blocker(self) -> None:
        if not self.threat_active:
            return
        if self.core_guard_index is None or self.core_guard_index >= len(self.platforms):
            self._refresh_blocker_point()
            self.core_guard_index = self._select_core_guard()
            self._replan_guards()
        self._refresh_blocker_point()
        core = self.platforms[self.core_guard_index]
        core.position = self._blocker_point.copy()
        core.goal = self._blocker_point.copy()
        core.role = "core"

    def step(self) -> None:
        """Advance one frame while preserving the strict blocker invariant."""
        if self.paused:
            return
        self.frame += 1
        if not self.threat_active:
            self.phase = "正常护航"
            self.own_position += normalize(self.forward) * self.cruise_speed * self.dt
            goals = self._desired_goals()
            self._move_non_core_platforms(goals)
            return

        self.phase = "最近守卫成弧、其余成员最小移动重编队"
        self._move_own_target()
        self._refresh_blocker_point()
        goals = self._desired_goals()
        self._move_non_core_platforms(goals)
        # Constraint priority: the core is projected after every other update.
        self._enforce_core_blocker()
        self.emergency_deployment = False

    def blocking_error(self) -> float:
        if not self.threat_active or self.core_guard_index is None:
            return math.inf
        point, _ = compute_blocker_point(
            self.own_position,
            self.enemy_position,
            ratio=self.blocker_ratio,
            r_min=self.blocker_r_min,
            r_max=self.blocker_r_max,
            fallback_direction=local_direction(self.scene, self.forward),
        )
        return float(np.linalg.norm(self.platforms[self.core_guard_index].position - point))

    def blocker_segment_parameter(self) -> float:
        if not self.threat_active or self.core_guard_index is None:
            return math.nan
        delta = self.enemy_position - self.own_position
        denominator = float(np.dot(delta, delta))
        if denominator <= EPS:
            return math.nan
        core_delta = self.platforms[self.core_guard_index].position - self.own_position
        return float(np.dot(core_delta, delta) / denominator)

    def strict_blocking_satisfied(self, tolerance: float = 1e-9) -> bool:
        t = self.blocker_segment_parameter()
        return bool(self.blocking_error() < tolerance and 0.0 < t < 1.0)

    def status(self) -> Dict[str, object]:
        core_name = (
            self.platforms[self.core_guard_index].identifier
            if self.core_guard_index is not None
            else None
        )
        return {
            "frame": self.frame,
            "scene": self.scene,
            "threat_label": self.threat_bearing_label(),
            "enemy_position": self.enemy_position.copy(),
            "avoidance_mode": self.avoidance_mode,
            "phase": self.phase,
            "paused": self.paused,
            "core_guard": core_name,
            "blocking_error": self.blocking_error(),
            "blocker_t": self.blocker_segment_parameter(),
            "strict_blocking": self.strict_blocking_satisfied(),
            "uav_count": sum(p.kind == "UAV" for p in self.platforms),
            "usv_count": sum(p.kind == "USV" for p in self.platforms),
        }


class EscortGuardVisualizer:
    """Matplotlib mouse placement, animation, and keyboard mode controller."""

    def __init__(self, simulator: EscortGuardSimulator) -> None:
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
        from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon

        self.plt = plt
        self.FancyArrowPatch = FancyArrowPatch
        self.FancyBboxPatch = FancyBboxPatch
        self.Polygon = Polygon
        self.sim = simulator
        self.animation = None
        self.view_half_width = 19.0
        self.view_half_height = 12.0

        preferred_fonts = [
            "Microsoft YaHei",
            "SimHei",
            "Noto Sans CJK SC",
            "Arial Unicode MS",
            "DejaVu Sans",
        ]
        # Register a common Linux CJK font when present.  Windows normally
        # resolves Microsoft YaHei directly, so this branch is only a robust
        # fallback for headless/Linux execution.
        noto_path = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc")
        if noto_path.exists():
            try:
                font_manager.fontManager.addfont(str(noto_path))
                preferred_fonts.insert(
                    0, font_manager.FontProperties(fname=str(noto_path)).get_name()
                )
            except (OSError, RuntimeError, ValueError):
                pass
        plt.rcParams["font.sans-serif"] = preferred_fonts
        plt.rcParams["axes.unicode_minus"] = False

        self.fig, self.ax = plt.subplots(figsize=(12.5, 8.0))
        self.ax.set_aspect("equal", adjustable="box")
        self._center_view_on_own_target()
        self.ax.set_facecolor("#dff4f7")
        self.ax.grid(alpha=0.25, linestyle="--")
        self.ax.set_xlabel("X / 海里（示意）")
        self.ax.set_ylabel("Y / 海里（示意）")

        self.uav_scatter = self.ax.scatter(
            [], [], marker="o", s=260, zorder=5, label="UAV"
        )
        self.usv_scatter = self.ax.scatter(
            [], [], marker="s", s=260, zorder=5, label="USV"
        )
        self.enemy_patch = Polygon(
            np.zeros((3, 2)), closed=True, facecolor="#e53935", edgecolor="#8b0000", zorder=6
        )
        self.ax.add_patch(self.enemy_patch)
        self.own_patch = FancyBboxPatch(
            (-1.6, -0.55),
            3.2,
            1.1,
            boxstyle="round,pad=0.18,rounding_size=0.18",
            facecolor="#4472c4",
            edgecolor="#203864",
            linewidth=1.8,
            zorder=6,
        )
        self.ax.add_patch(self.own_patch)
        self.own_text = self.ax.text(
            0.0,
            0.0,
            "我方护航目标",
            ha="center",
            va="center",
            color="white",
            weight="bold",
            fontsize=11,
            zorder=7,
        )
        self.enemy_text = self.ax.text(
            0.0,
            0.0,
            "敌方目标",
            ha="center",
            va="center",
            color="white",
            weight="bold",
            fontsize=9,
            zorder=7,
        )
        (self.threat_line,) = self.ax.plot(
            [], [], "--", color="#d62728", linewidth=1.8, zorder=2, label="敌我连线"
        )
        (self.guard_arc_line,) = self.ax.plot(
            [], [], color="#f0ad00", linewidth=2.0, alpha=0.85, zorder=2, label="防护弧"
        )
        (self.blocker_cross,) = self.ax.plot(
            [], [], marker="x", markersize=12, markeredgewidth=2.6, color="#7f0000", zorder=8,
            label="严格阻断点"
        )
        self.heading_arrow = FancyArrowPatch(
            (0.0, 0.0),
            (2.5, 0.0),
            arrowstyle="-|>",
            mutation_scale=18,
            linewidth=2.0,
            color="#1f4e79",
            zorder=4,
        )
        self.ax.add_patch(self.heading_arrow)
        self.platform_labels = [
            self.ax.text(0.0, 0.0, "", ha="center", va="bottom", fontsize=8, zorder=9)
            for _ in self.sim.platforms
        ]
        self.status_text = self.ax.text(
            0.985,
            0.985,
            "",
            transform=self.ax.transAxes,
            ha="right",
            va="top",
            fontsize=10,
            bbox=dict(facecolor="white", alpha=0.9, edgecolor="#6c757d", boxstyle="round,pad=0.5"),
            zorder=12,
        )
        self.help_text = self.ax.text(
            0.015,
            0.015,
            "左键点击海面：在点击位置放置/移动敌方目标\n"
            "A：自动避让   L/R：左/右避让   Space：暂停/继续\n"
            "N：重置编队   Esc：关闭",
            transform=self.ax.transAxes,
            ha="left",
            va="bottom",
            fontsize=9,
            bbox=dict(facecolor="white", alpha=0.82, edgecolor="#90a4ae"),
            zorder=12,
        )
        self.ax.legend(loc="lower right", framealpha=0.9)
        self.fig.canvas.mpl_connect("key_press_event", self.on_key)
        self.fig.canvas.mpl_connect("button_press_event", self.on_click)
        self._refresh_artists()

    def _center_view_on_own_target(self) -> None:
        """Keep the escorted target exactly at the center of the viewport."""
        own_x, own_y = self.sim.own_position
        self.ax.set_xlim(own_x - self.view_half_width, own_x + self.view_half_width)
        self.ax.set_ylim(own_y - self.view_half_height, own_y + self.view_half_height)

    @staticmethod
    def _role_style(platform: Platform) -> Tuple[str, str, float]:
        if platform.role == "core":
            return "#ffbf00", "#b00020", 3.0
        if platform.role == "wing":
            return "#ffd966", "#8a6d00", 1.8
        return "#86c56f", "#275d38", 1.4

    def _update_platform_scatter(self, kind: str, artist) -> None:
        entries = [(i, p) for i, p in enumerate(self.sim.platforms) if p.kind == kind]
        if not entries:
            artist.set_offsets(np.empty((0, 2)))
            return
        positions = np.array([p.position for _, p in entries])
        facecolors, edgecolors, widths = zip(*(self._role_style(p) for _, p in entries))
        artist.set_offsets(positions)
        artist.set_facecolors(facecolors)
        artist.set_edgecolors(edgecolors)
        artist.set_linewidths(widths)

    def _arc_polyline(self) -> np.ndarray:
        if not self.sim.threat_active:
            return np.empty((0, 2))
        _, direction, _ = self.sim._threat_geometry()
        lateral = rotate90(direction)
        wing_count = max(0, self.sim.total_forward_guards - 1)
        half_angle = self.sim._effective_guard_arc_half_angle(wing_count)
        phis = np.linspace(-half_angle, half_angle, 80)
        return np.array(
            [
                self.sim.own_position
                + self.sim.guard_arc_radius
                * (math.cos(phi) * direction + math.sin(phi) * lateral)
                for phi in phis
            ]
        )

    def _refresh_artists(self) -> Tuple[object, ...]:
        self._center_view_on_own_target()
        self._update_platform_scatter("UAV", self.uav_scatter)
        self._update_platform_scatter("USV", self.usv_scatter)

        for text, platform in zip(self.platform_labels, self.sim.platforms):
            text.set_position(platform.position + np.array([0.0, 0.34]))
            text.set_text(platform.identifier)
            text.set_color("#8b0000" if platform.role == "core" else "#1f2933")
            text.set_weight("bold" if platform.role == "core" else "normal")

        own_x, own_y = self.sim.own_position
        self.own_patch.set_x(own_x - 1.6)
        self.own_patch.set_y(own_y - 0.55)
        self.own_text.set_position((own_x, own_y))

        enemy_x, enemy_y = self.sim.enemy_position
        tri = np.array(
            [
                [enemy_x, enemy_y + 0.60],
                [enemy_x - 0.52, enemy_y - 0.40],
                [enemy_x + 0.52, enemy_y - 0.40],
            ]
        )
        self.enemy_patch.set_xy(tri)
        self.enemy_text.set_position((enemy_x, enemy_y - 0.05))
        self.enemy_patch.set_visible(self.sim.threat_active)
        self.enemy_text.set_visible(self.sim.threat_active)

        if self.sim.threat_active:
            self.threat_line.set_data([own_x, enemy_x], [own_y, enemy_y])
            blocker = self.sim.blocker_point
            self.blocker_cross.set_data([blocker[0]], [blocker[1]])
            arc = self._arc_polyline()
            self.guard_arc_line.set_data(arc[:, 0], arc[:, 1])
        else:
            self.threat_line.set_data([], [])
            self.blocker_cross.set_data([], [])
            self.guard_arc_line.set_data([], [])

        heading_start = self.sim.own_position + np.array([0.0, -1.2])
        heading_end = heading_start + normalize(self.sim.forward) * 2.2
        self.heading_arrow.set_positions(heading_start, heading_end)

        status = self.sim.status()
        blocking = "满足" if status["strict_blocking"] else "未满足"
        emergency = "（紧急瞬时部署）" if self.sim.emergency_deployment else ""
        enemy_coordinate = (
            f"({status['enemy_position'][0]:.2f}, {status['enemy_position'][1]:.2f})"
            if self.sim.threat_active
            else "未放置"
        )
        self.status_text.set_text(
            f"威胁方位：{status['threat_label']}\n"
            f"敌方坐标：{enemy_coordinate}\n"
            f"阶段：{status['phase']}\n"
            f"避让：{status['avoidance_mode']}\n"
            f"核心守卫：{status['core_guard']} {emergency}\n"
            f"严格阻断：{blocking}\n"
            f"误差：{status['blocking_error']:.2e}\n"
            f"线段参数 t：{status['blocker_t']:.4f}\n"
            f"UAV/USV：{status['uav_count']}/{status['usv_count']}\n"
            f"{'已暂停' if status['paused'] else '运行中'}"
        )
        self.ax.set_title(
            "海上混合 UAV/USV 护航守卫仿真（左键点击放置敌方目标）",
            fontsize=16,
            weight="bold",
        )
        return (
            self.uav_scatter,
            self.usv_scatter,
            self.enemy_patch,
            self.own_patch,
            self.own_text,
            self.enemy_text,
            self.threat_line,
            self.guard_arc_line,
            self.blocker_cross,
            self.heading_arrow,
            self.status_text,
            *self.platform_labels,
        )

    def update(self, _frame: int) -> Tuple[object, ...]:
        self.sim.step()
        return self._refresh_artists()

    def on_click(self, event) -> None:
        """Place the enemy at a left-clicked data coordinate inside the axes."""
        button = getattr(event.button, "value", event.button)
        if event.inaxes is not self.ax or button != 1:
            return
        if event.xdata is None or event.ydata is None:
            return
        coordinate = np.array([event.xdata, event.ydata], dtype=float)
        if not np.all(np.isfinite(coordinate)):
            return
        self.sim.activate_threat_at(coordinate)
        self._refresh_artists()
        self.fig.canvas.draw_idle()

    def on_key(self, event) -> None:
        key = (event.key or "").lower()
        if key == "a":
            self.sim.set_avoidance_mode("auto")
        elif key == "l":
            self.sim.set_avoidance_mode("left")
        elif key == "r":
            self.sim.set_avoidance_mode("right")
        elif key in {" ", "space"}:
            self.sim.toggle_pause()
        elif key == "n":
            self.sim.reset()
        elif key in {"escape", "esc"}:
            self.plt.close(self.fig)
            return
        else:
            return
        self._refresh_artists()
        self.fig.canvas.draw_idle()

    def show(self, interval_ms: int = 55) -> None:
        from matplotlib.animation import FuncAnimation

        self.animation = FuncAnimation(
            self.fig,
            self.update,
            interval=interval_ms,
            blit=False,
            cache_frame_data=False,
        )
        self.plt.show()

    def save_snapshot(self, path: str | Path, dpi: int = 150) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        self._refresh_artists()
        self.fig.savefig(output, dpi=dpi, bbox_inches="tight")
        return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", choices=SCENES, default="front", help="initial threat direction")
    parser.add_argument(
        "--avoidance",
        choices=("auto", "left", "right"),
        default="auto",
        help="avoidance mode",
    )
    parser.add_argument(
        "--headless-frames",
        type=int,
        default=0,
        metavar="N",
        help="run N simulation frames without opening an interactive window",
    )
    parser.add_argument(
        "--save-snapshot",
        type=str,
        default=None,
        metavar="PATH",
        help="save the final 2-D scene to a PNG/PDF/SVG file",
    )
    parser.add_argument("--seed", type=int, default=42)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.headless_frames < 0:
        raise SystemExit("--headless-frames must be non-negative")

    if args.headless_frames or args.save_snapshot:
        import matplotlib

        matplotlib.use("Agg")

    scripted_run = bool(args.headless_frames or args.save_snapshot)
    sim = EscortGuardSimulator(
        scene=args.scene,
        avoidance_mode=args.avoidance,
        threat_active=scripted_run,
        seed=args.seed,
    )

    if args.headless_frames:
        for _ in range(args.headless_frames):
            sim.step()
            if not sim.strict_blocking_satisfied():
                raise RuntimeError(
                    f"strict blocker invariant failed: error={sim.blocking_error():.3e}, "
                    f"t={sim.blocker_segment_parameter():.9f}"
                )

    if args.save_snapshot:
        visualizer = EscortGuardVisualizer(sim)
        output = visualizer.save_snapshot(args.save_snapshot)
        print(f"Snapshot saved: {output.resolve()}")

    if args.headless_frames:
        status = sim.status()
        print(
            "Headless verification passed: "
            f"scene={status['scene']}, frames={args.headless_frames}, "
            f"core={status['core_guard']}, error={status['blocking_error']:.3e}, "
            f"t={status['blocker_t']:.6f}"
        )
        return 0

    print(
        "鼠标左键点击海面放置敌方目标；A/L/R 切换避让，"
        "Space 暂停，N 重置，Esc 退出。"
    )
    visualizer = EscortGuardVisualizer(sim)
    visualizer.show()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())