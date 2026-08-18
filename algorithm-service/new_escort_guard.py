"""单目标随机环绕的 UAV/USV 三维护航守卫仿真。

运行示例：

    python 护航守卫10_三维单目标随机环绕_Python39.py
    python 护航守卫10_三维单目标随机环绕_Python39.py --sensor-radius 12
    python 护航守卫10_三维单目标随机环绕_Python39.py --reserve-count 2

每架 UAV 在创建时获得 10–50 的随机固定高度，USV、敌方目标和我方
高价值目标严格保持在 z=0。目标进入感知范围并完成守卫编队后，按随机
角度段进行顺时针或逆时针环绕。按 N 只重置敌方目标的位置与任务状态，
不会重置我方目标、UAV/USV 的当前位置或 UAV 高度。
"""
import argparse
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union

import numpy as np

# ---------------------------------------------------------------------------
# 用户可直接修改的编队参数
# ---------------------------------------------------------------------------
NUM_UAV = 3
NUM_USV = 3
ESCORT_RESERVE_COUNT = 0  # 允许设置为 0 或 2

WORLD_X_MIN = -80.0
WORLD_X_MAX = 80.0
WORLD_Y_MIN = -50.0
WORLD_Y_MAX = 50.0
OWN_START_X = -52.0
OWN_START_Y = 0.0

LOCAL_UAV_SIZE = 220.0
LOCAL_USV_SIZE = 220.0
GLOBAL_UAV_SIZE = 28.0
GLOBAL_USV_SIZE = 34.0
GLOBAL_ENEMY_SCALE = 0.45

SUPPORT_GUARD_RADIUS = 4.2
SUPPORT_ARC_HALF_ANGLE_DEG = 65.0
SUPPORT_ARC_REAR_OFFSET_DEG = 180.0

DEFAULT_SENSOR_RADIUS = 12.0

UAV_ALTITUDE_MIN = 0.0
UAV_ALTITUDE_MAX = 7.0
VIEW_Z_MIN = 0.0
VIEW_Z_MAX = 55.0

RANDOM_ORBIT_MIN_ANGLE_DEG = 25.0
RANDOM_ORBIT_MAX_ANGLE_DEG = 120.0
RANDOM_ORBIT_MIN_SPEED = 0.012
RANDOM_ORBIT_MAX_SPEED = 0.024
RANDOM_ORBIT_REVERSE_PROBABILITY = 0.65

WING_ARRIVAL_TOLERANCE = 0.35
WING_READY_RATIO = 0.80

EPS = 1e-12
DETECTED_STATES = {"detected", "forming", "orbiting"}
STATE_LABELS = {
    "waiting": "等待出现",
    "approaching": "接近中",
    "detected": "已感知",
    "forming": "守卫编队中",
    "orbiting": "环绕机动",
}


def horizontal(value: np.ndarray) -> np.ndarray:
    """Return the horizontal x/y components of a 2-D or 3-D vector."""
    arr = np.asarray(value, dtype=float)
    if arr.shape[0] < 2:
        raise ValueError("a position/vector must contain at least x and y")
    return arr[:2].copy()


def point3(value: np.ndarray, altitude: float = 0.0) -> np.ndarray:
    """Build a three-dimensional position from horizontal coordinates."""
    xy = horizontal(value)
    return np.array([xy[0], xy[1], float(altitude)], dtype=float)


def with_altitude(value: np.ndarray, altitude: float) -> np.ndarray:
    """Copy a position and force its z coordinate to the requested altitude."""
    return point3(value, altitude)


def horizontal_distance(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(horizontal(a) - horizontal(b)))


def normalize(v: np.ndarray, fallback: Optional[np.ndarray] = None) -> np.ndarray:
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
    arr = np.asarray(v, dtype=float)
    return np.array([-arr[1], arr[0]], dtype=float)


def wrapped_angle_distance(a: float, b: float) -> float:
    return abs((a - b + math.pi) % (2.0 * math.pi) - math.pi)


def compute_blocker_point(
    own: np.ndarray,
    enemy: np.ndarray,
    ratio: float = 0.38,
    r_min: float = 2.2,
    r_max: float = 4.0,
    fallback_direction: Optional[np.ndarray] = None,
) -> Tuple[np.ndarray, float]:
    """计算严格位于敌我水平连线内部、海拔为 0 的动态核心阻断点。"""
    if not (0.0 < ratio < 1.0):
        raise ValueError("ratio must be in (0, 1)")
    if not (0.0 <= r_min <= r_max):
        raise ValueError("expected 0 <= r_min <= r_max")
    own_xy = horizontal(own)
    enemy_xy = horizontal(enemy)
    delta = enemy_xy - own_xy
    distance = float(np.linalg.norm(delta))
    if distance <= EPS:
        delta = normalize(
            np.array([1.0, 0.0]) if fallback_direction is None else horizontal(fallback_direction),
            np.array([1.0, 0.0]),
        )
        distance = 1.0
    requested = float(np.clip(ratio * distance, r_min, r_max))
    radius = min(max(distance * 1e-9, requested), distance * (1.0 - 1e-9))
    t = radius / distance
    return point3(own_xy + t * delta, 0.0), float(t)


@dataclass
class Platform:
    identifier: str
    kind: str
    position: np.ndarray
    max_speed: float
    gain: float
    altitude: float
    role: str = "escort"
    goal: Optional[np.ndarray] = None
    assigned_threat_id: Optional[int] = None


@dataclass
class ThreatTask:
    threat_id: int
    spawn_frame: int
    spawn_angle: float
    spawn_radius: float
    position: np.ndarray
    state: str = "waiting"
    current_speed_limit: float = 0.0
    detected_frame: Optional[int] = None
    blocker_point: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=float))
    blocker_t: float = math.nan
    guard_quota: int = 0
    core_guard_index: Optional[int] = None
    wing_guard_indices: List[int] = field(default_factory=list)
    wing_slot_by_index: Dict[int, int] = field(default_factory=dict)
    core_motion_state: str = "idle"
    core_dispatch_origin: Optional[np.ndarray] = None
    core_dispatch_initial_distance: float = 0.0
    core_trajectory: List[np.ndarray] = field(default_factory=list)
    controlled_radius: float = 0.0
    controlled_angle: float = 0.0
    orbit_direction: int = 1
    orbit_segment_angle: float = 0.0
    orbit_segment_remaining: float = 0.0
    orbit_angular_speed_current: float = 0.0
    orbit_segment_count: int = 0
    orbit_direction_changes: int = 0


class EscortGuardSimulator:
    """单个移动威胁的感知、编队和随机环绕持续盯防控制器。"""

    def __init__(
        self,
        *,
        sensor_radius: float = DEFAULT_SENSOR_RADIUS,
        seed: int = 42,
        num_uav: int = NUM_UAV,
        num_usv: int = NUM_USV,
        escort_reserve_count: int = ESCORT_RESERVE_COUNT,
        ring_radius: float = 4.0,
        guard_arc_radius: float = 5.2,
        support_guard_radius: float = SUPPORT_GUARD_RADIUS,
        support_arc_half_angle_deg: float = SUPPORT_ARC_HALF_ANGLE_DEG,
        support_arc_rear_offset_deg: float = SUPPORT_ARC_REAR_OFFSET_DEG,
        guard_arc_half_angle_deg: float = 32.0,
        max_guard_arc_half_angle_deg: float = 75.0,
        minimum_guard_spacing: float = 1.05,
        blocker_ratio: float = 0.38,
        blocker_r_min: float = 2.2,
        blocker_r_max: float = 4.0,
        core_arrival_tolerance: float = 0.24,
        wing_arrival_tolerance: float = WING_ARRIVAL_TOLERANCE,
        wing_ready_ratio: float = WING_READY_RATIO,
        enemy_approach_speed: float = 0.10,
        enemy_forming_speed: float = 0.14,
        enemy_controlled_speed: float = 0.30,
        enemy_min_radius: float = 6.6,
        random_orbit_min_angle_deg: float = RANDOM_ORBIT_MIN_ANGLE_DEG,
        random_orbit_max_angle_deg: float = RANDOM_ORBIT_MAX_ANGLE_DEG,
        random_orbit_min_speed: float = RANDOM_ORBIT_MIN_SPEED,
        random_orbit_max_speed: float = RANDOM_ORBIT_MAX_SPEED,
        random_orbit_reverse_probability: float = RANDOM_ORBIT_REVERSE_PROBABILITY,
        avoidance_mode: str = "auto",
        avoid_distance: float = 3.8,
        forward_shift: float = 2.2,
        own_max_speed: float = 0.075,
        own_gain: float = 0.08,
        cruise_speed: float = 0.035,
        safe_distance: float = 0.75,
        repulsion_gain: float = 0.025,
        own_target_avoid_radius: float = 2.0,
        core_trail_length: int = 240,
        dt: float = 1.0,
    ) -> None:
        platform_count = int(num_uav) + int(num_usv)
        if num_uav < 0 or num_usv < 0 or platform_count < 6:
            raise ValueError("The UAV/USV total must be at least 6")
        if escort_reserve_count not in {0, 2}:
            raise ValueError("escort_reserve_count must be 0 or 2")
        if support_guard_radius <= own_target_avoid_radius:
            raise ValueError("support_guard_radius must exceed the own-target safety radius")
        if not (0.0 <= support_arc_half_angle_deg < 180.0):
            raise ValueError("support_arc_half_angle_deg must be in [0, 180)")
        if sensor_radius <= max(guard_arc_radius, support_guard_radius, own_target_avoid_radius):
            raise ValueError("sensor_radius must exceed guard and safety radii")
        if not (0.0 < wing_ready_ratio <= 1.0):
            raise ValueError("wing_ready_ratio must be in (0, 1]")
        if not (0.0 < random_orbit_min_angle_deg <= random_orbit_max_angle_deg <= 360.0):
            raise ValueError("random orbit angles must satisfy 0 < min <= max <= 360")
        if not (0.0 < random_orbit_min_speed <= random_orbit_max_speed):
            raise ValueError("random orbit speeds must satisfy 0 < min <= max")
        if not (0.0 <= random_orbit_reverse_probability <= 1.0):
            raise ValueError("random_orbit_reverse_probability must be in [0, 1]")

        self.seed = int(seed)
        self.reset_count = 0
        self.rng = np.random.default_rng(self.seed)
        self.num_uav = int(num_uav)
        self.num_usv = int(num_usv)
        self.enemy_count = 1
        self.spawn_mode = "single_random_direction"
        self.enemy_motion = "random_segment_orbit"
        self.sensor_radius = float(sensor_radius)
        self.escort_reserve_count = int(escort_reserve_count)
        self.ring_radius = float(ring_radius)
        self.guard_arc_radius = float(guard_arc_radius)
        self.support_guard_radius = float(support_guard_radius)
        self.support_arc_half_angle = math.radians(float(support_arc_half_angle_deg))
        self.support_arc_rear_offset = math.radians(float(support_arc_rear_offset_deg))
        self.guard_arc_half_angle = math.radians(float(guard_arc_half_angle_deg))
        self.max_guard_arc_half_angle = math.radians(float(max_guard_arc_half_angle_deg))
        self.minimum_guard_spacing = float(minimum_guard_spacing)
        self.blocker_ratio = float(blocker_ratio)
        self.blocker_r_min = float(blocker_r_min)
        self.blocker_r_max = float(blocker_r_max)
        self.core_arrival_tolerance = float(core_arrival_tolerance)
        self.wing_arrival_tolerance = float(wing_arrival_tolerance)
        self.wing_ready_ratio = float(wing_ready_ratio)
        self.enemy_approach_speed = float(enemy_approach_speed)
        self.enemy_forming_speed = float(enemy_forming_speed)
        self.enemy_controlled_speed = float(enemy_controlled_speed)
        self.enemy_min_radius = float(enemy_min_radius)
        self.random_orbit_min_angle = math.radians(float(random_orbit_min_angle_deg))
        self.random_orbit_max_angle = math.radians(float(random_orbit_max_angle_deg))
        self.random_orbit_min_speed = float(random_orbit_min_speed)
        self.random_orbit_max_speed = float(random_orbit_max_speed)
        self.random_orbit_reverse_probability = float(random_orbit_reverse_probability)
        self.avoidance_mode = avoidance_mode
        self.avoid_distance = float(avoid_distance)
        self.forward_shift = float(forward_shift)
        self.own_max_speed = float(own_max_speed)
        self.own_gain = float(own_gain)
        self.cruise_speed = float(cruise_speed)
        self.safe_distance = float(safe_distance)
        self.repulsion_gain = float(repulsion_gain)
        self.own_target_avoid_radius = float(own_target_avoid_radius)
        self._own_target_route_margin = max(0.08, 0.03 * self.own_target_avoid_radius)
        self.core_trail_length = int(core_trail_length)
        self.dt = float(dt)
        self.world_x_min = float(WORLD_X_MIN)
        self.world_x_max = float(WORLD_X_MAX)
        self.world_y_min = float(WORLD_Y_MIN)
        self.world_y_max = float(WORLD_Y_MAX)
        self.initial_own_position = np.array([OWN_START_X, OWN_START_Y, 0.0], dtype=float)
        if not (
            self.world_x_min + self.ring_radius < self.initial_own_position[0] < self.world_x_max - self.ring_radius
            and self.world_y_min + self.ring_radius < self.initial_own_position[1] < self.world_y_max - self.ring_radius
        ):
            raise ValueError("The initial escort position must leave room for the escort ring")

        self.forward = np.array([1.0, 0.0], dtype=float)
        self.own_position = self.initial_own_position.copy()
        self.own_goal = self.own_position.copy()
        self.avoid_direction = np.zeros(2, dtype=float)
        self.frame = 0
        self.paused = False
        self.phase = "正常护航"
        # self.last_message = "敌方目标尚未进入感知范围"

        self.last_message = "当前没有敌方目标，请按 N 键随机生成"

        self.platforms = self._create_mixed_ring()
        # self.threats = self._create_threat_schedule()

        # 初始化时没有敌方目标，按 N 键后再随机生成
        self.threats: List[ThreatTask] = []

        self.reserve_guard_indices: List[int] = []
        self._reserve_slot_offsets: Dict[int, np.ndarray] = {}
        self._reserve_slot_by_index: Dict[int, int] = {}
        self.support_guard_indices: List[int] = []
        self._support_slot_by_index: Dict[int, int] = {}
        self._last_detected_ids: Tuple[int, ...] = ()
        self._own_target_bypass_side: Dict[int, int] = {}

    @property
    def max_targets(self) -> int:
        return 1

    @property
    def threat_count(self) -> int:
        return len(self.threats)

    @property
    def spawned_threats(self) -> List[ThreatTask]:
        return [task for task in self.threats if task.state != "waiting"]

    @property
    def detected_threats(self) -> List[ThreatTask]:
        return [task for task in self.threats if task.state in DETECTED_STATES]

    @property
    def threat_active(self) -> bool:
        return bool(self.detected_threats)

    @property
    def forward_guard_indices(self) -> List[int]:
        result: List[int] = []
        for task in self.detected_threats:
            if task.core_guard_index is not None:
                result.append(task.core_guard_index)
            result.extend(task.wing_guard_indices)
        return result

    def get_threat(self, threat_id: int) -> ThreatTask:
        for task in self.threats:
            if task.threat_id == threat_id:
                return task
        raise KeyError(f"Unknown threat id {threat_id}")

    def _create_mixed_ring(self) -> List[Platform]:
        kinds: List[str] = []
        uav_left, usv_left = self.num_uav, self.num_usv
        prefer_uav = True
        while uav_left + usv_left:
            if (prefer_uav and uav_left > 0) or usv_left == 0:
                kinds.append("UAV")
                uav_left -= 1
            else:
                kinds.append("USV")
                usv_left -= 1
            prefer_uav = not prefer_uav
        rotation = float(self.rng.uniform(-0.10, 0.10))
        angles = np.linspace(0.0, 2.0 * math.pi, len(kinds), endpoint=False) + rotation
        result: List[Platform] = []
        uav_no = usv_no = 0
        for angle, kind in zip(angles, kinds):
            horizontal_position = horizontal(self.own_position) + self.ring_radius * np.array(
                [math.cos(angle), math.sin(angle)], dtype=float
            )
            if kind == "UAV":
                uav_no += 1
                altitude = float(self.rng.uniform(UAV_ALTITUDE_MIN, UAV_ALTITUDE_MAX))
                position = point3(horizontal_position, altitude)
                result.append(Platform(f"U{uav_no}", kind, position, 0.28, 0.42, altitude))
            else:
                usv_no += 1
                altitude = 0.0
                position = point3(horizontal_position, altitude)
                result.append(Platform(f"S{usv_no}", kind, position, 0.15, 0.32, altitude))
        return result

    def _create_threat_schedule(self) -> List[ThreatTask]:
        """Create exactly one target at a uniformly random bearing."""
        angle = float(self.rng.uniform(0.0, 2.0 * math.pi))
        radius = float(self.rng.uniform(self.sensor_radius + 4.0, self.sensor_radius + 8.0))
        position = point3(
            horizontal(self.own_position)
            + radius * np.array([math.cos(angle), math.sin(angle)], dtype=float),
            0.0,
        )
        return [
            ThreatTask(
                threat_id=1,
                spawn_frame=0,
                spawn_angle=angle,
                spawn_radius=radius,
                position=position,
            )
        ]

    def _start_random_orbit_segment(self, task: ThreatTask) -> None:
        """Choose the next random angular segment and clockwise/counterclockwise direction."""
        previous_direction = task.orbit_direction
        if task.orbit_segment_count == 0:
            new_direction = int(self.rng.choice(np.array([-1, 1], dtype=int)))
        elif float(self.rng.random()) < self.random_orbit_reverse_probability:
            new_direction = -previous_direction
        else:
            new_direction = previous_direction
        if task.orbit_segment_count > 0 and new_direction != previous_direction:
            task.orbit_direction_changes += 1
        task.orbit_direction = new_direction
        task.orbit_segment_angle = float(
            self.rng.uniform(self.random_orbit_min_angle, self.random_orbit_max_angle)
        )
        task.orbit_segment_remaining = task.orbit_segment_angle
        task.orbit_angular_speed_current = float(
            self.rng.uniform(self.random_orbit_min_speed, self.random_orbit_max_speed)
        )
        task.orbit_segment_count += 1

    def reset(self) -> None:
        """只重置敌方目标；保留我方目标、平台位置和 UAV 固定高度。"""
        self.reset_count += 1
        for platform in self.platforms:
            platform.role = "escort"
            platform.goal = platform.position.copy()
            platform.assigned_threat_id = None
            # 双重约束高度，防止外部修改后重置造成高度漂移。
            platform.position[2] = platform.altitude if platform.kind == "UAV" else 0.0

        self.reserve_guard_indices = []
        self._reserve_slot_offsets = {}
        self._reserve_slot_by_index = {}
        self.support_guard_indices = []
        self._support_slot_by_index = {}
        self._last_detected_ids = ()
        self._own_target_bypass_side = {}
        self.avoid_direction = np.zeros(2, dtype=float)

        angle = float(self.rng.uniform(0.0, 2.0 * math.pi))
        radius = float(self.rng.uniform(self.sensor_radius + 4.0, self.sensor_radius + 8.0))
        position = point3(
            horizontal(self.own_position)
            + radius * np.array([math.cos(angle), math.sin(angle)], dtype=float),
            0.0,
        )
        self.threats = [
            ThreatTask(
                threat_id=1,
                spawn_frame=self.frame,
                spawn_angle=angle,
                spawn_radius=radius,
                position=position,
                state="approaching",
                current_speed_limit=self.enemy_approach_speed,
            )
        ]
        self.phase = "正常护航"
        self.last_message = "仅敌方目标位置已重置；我方编队与 UAV 高度保持不变"

    def toggle_pause(self) -> bool:
        self.paused = not self.paused
        return self.paused

    def _spawn_due_threats(self) -> None:
        for task in self.threats:
            if task.state == "waiting" and self.frame >= task.spawn_frame:
                task.position = point3(
                    horizontal(self.own_position)
                    + task.spawn_radius
                    * np.array([math.cos(task.spawn_angle), math.sin(task.spawn_angle)], dtype=float),
                    0.0,
                )
                task.state = "approaching"
                task.current_speed_limit = self.enemy_approach_speed
                self.last_message = f"敌方目标 T{task.threat_id} 已从随机方向出现"

    def _move_point_toward(
        self, current: np.ndarray, desired: np.ndarray, speed_limit: float
    ) -> np.ndarray:
        current_arr = np.asarray(current, dtype=float)
        desired_arr = np.asarray(desired, dtype=float)
        delta = horizontal(desired_arr) - horizontal(current_arr)
        distance = float(np.linalg.norm(delta))
        max_step = max(0.0, float(speed_limit)) * self.dt
        result = current_arr.copy()
        if distance <= max_step + EPS:
            result[:2] = horizontal(desired_arr)
        else:
            result[:2] = horizontal(current_arr) + delta * (max_step / (distance + EPS))
        result[2] = current_arr[2] if current_arr.shape[0] >= 3 else 0.0
        return result

    def _move_enemy(self, task: ThreatTask) -> None:
        if task.state == "waiting":
            task.current_speed_limit = 0.0
            task.position[2] = 0.0
            return
        relative = horizontal(task.position) - horizontal(self.own_position)
        direction = normalize(relative, np.array([1.0, 0.0]))
        if task.state == "approaching":
            task.current_speed_limit = self.enemy_approach_speed
            desired = with_altitude(self.own_position, 0.0)
            task.position = self._move_point_toward(task.position, desired, task.current_speed_limit)
            task.position = self._clip_position_to_world(task.position, margin=0.2)
            task.position[2] = 0.0
            return
        if task.state in {"detected", "forming"}:
            task.current_speed_limit = self.enemy_forming_speed
            target_radius = self._controlled_track_radius(task)
            desired = point3(horizontal(self.own_position) + direction * target_radius, 0.0)
            task.position = self._move_point_toward(task.position, desired, task.current_speed_limit)
            task.position = self._clip_position_to_world(task.position, margin=0.2)
            task.position[2] = 0.0
            return
        task.current_speed_limit = self.enemy_controlled_speed
        if task.state == "orbiting":
            if task.orbit_segment_remaining <= EPS:
                self._start_random_orbit_segment(task)
            angular_step = min(
                task.orbit_segment_remaining,
                task.orbit_angular_speed_current * self.dt,
            )
            task.controlled_angle += task.orbit_direction * angular_step
            task.orbit_segment_remaining = max(0.0, task.orbit_segment_remaining - angular_step)
            desired = point3(
                horizontal(self.own_position)
                + task.controlled_radius
                * np.array([math.cos(task.controlled_angle), math.sin(task.controlled_angle)], dtype=float),
                0.0,
            )
            task.position = self._move_point_toward(task.position, desired, task.current_speed_limit)
            task.position = self._clip_position_to_world(task.position, margin=0.2)
            task.position[2] = 0.0
            if task.orbit_segment_remaining <= EPS:
                self._start_random_orbit_segment(task)
            return

    def _detect_new_threats(self) -> bool:
        changed = False
        for task in self.threats:
            if task.state != "approaching":
                continue
            distance = horizontal_distance(task.position, self.own_position)
            if distance <= self.sensor_radius + EPS:
                task.state = "detected"
                task.detected_frame = self.frame
                changed = True
                self.last_message = f"感知到敌方目标 T{task.threat_id}，触发守卫机制"
        return changed

    def _threat_geometry(self, task: ThreatTask) -> Tuple[np.ndarray, np.ndarray, float]:
        delta = horizontal(task.position) - horizontal(self.own_position)
        distance = float(np.linalg.norm(delta))
        return delta, normalize(delta, self.forward), distance

    def _refresh_task_blocker(self, task: ThreatTask) -> None:
        task.blocker_point, task.blocker_t = compute_blocker_point(
            self.own_position,
            task.position,
            ratio=self.blocker_ratio,
            r_min=self.blocker_r_min,
            r_max=self.blocker_r_max,
            fallback_direction=self.forward,
        )

    def _refresh_all_blockers(self) -> None:
        for task in self.detected_threats:
            self._refresh_task_blocker(task)

    @staticmethod
    def _minimum_cost_assignment(cost_matrix: np.ndarray) -> List[int]:
        """使用 O(n^3) 匈牙利算法完成矩形最小代价唯一分配。"""
        costs = np.asarray(cost_matrix, dtype=float)
        if costs.ndim != 2:
            raise ValueError("cost_matrix must be two-dimensional")
        rows, columns = costs.shape
        if rows == 0:
            return []
        if rows > columns:
            raise ValueError("there must be at least as many candidates as slots")
        if not np.all(np.isfinite(costs)):
            raise ValueError("cost_matrix must contain only finite values")

        # 经典势函数形式的匈牙利算法；数组使用 1-based 索引以保持公式清晰。
        u = np.zeros(rows + 1, dtype=float)
        v = np.zeros(columns + 1, dtype=float)
        matched_row = np.zeros(columns + 1, dtype=int)
        predecessor = np.zeros(columns + 1, dtype=int)

        for row in range(1, rows + 1):
            matched_row[0] = row
            min_value = np.full(columns + 1, math.inf, dtype=float)
            used = np.zeros(columns + 1, dtype=bool)
            column0 = 0
            while True:
                used[column0] = True
                active_row = matched_row[column0]
                delta = math.inf
                column1 = 0
                for column in range(1, columns + 1):
                    if used[column]:
                        continue
                    reduced = costs[active_row - 1, column - 1] - u[active_row] - v[column]
                    if reduced < min_value[column] - EPS:
                        min_value[column] = reduced
                        predecessor[column] = column0
                    if min_value[column] < delta - EPS:
                        delta = min_value[column]
                        column1 = column
                for column in range(columns + 1):
                    if used[column]:
                        u[matched_row[column]] += delta
                        v[column] -= delta
                    else:
                        min_value[column] -= delta
                column0 = column1
                if matched_row[column0] == 0:
                    break
            while True:
                column1 = predecessor[column0]
                matched_row[column0] = matched_row[column1]
                column0 = column1
                if column0 == 0:
                    break

        assignment = [-1] * rows
        for column in range(1, columns + 1):
            row = matched_row[column]
            if row != 0:
                assignment[row - 1] = column - 1
        if any(column < 0 for column in assignment):
            raise RuntimeError("minimum-cost assignment is incomplete")
        return assignment

    def guard_quota_per_detected_target(self) -> Dict[int, int]:
        tasks = self.detected_threats
        if not tasks:
            return {}
        available = len(self.platforms) - self.escort_reserve_count
        direct_quota = max(1, available // 2)
        return {tasks[0].threat_id: direct_quota}

    def _select_reserve_guards(self) -> List[int]:
        tasks = self.detected_threats
        if not tasks:
            return []
        scores = []
        for index, platform in enumerate(self.platforms):
            costs = [
                horizontal_distance(platform.position, task.blocker_point)
                / (platform.max_speed + EPS)
                for task in tasks
            ]
            scores.append((min(costs), index))
        return [index for _, index in sorted(scores, reverse=True)[: self.escort_reserve_count]]

    def _guard_arc_geometry(self, task: ThreatTask) -> Tuple[float, float]:
        """Return the single forward guard arc used for the only threat."""
        wing_count = max(0, task.guard_quota - 1)
        if wing_count <= 1:
            return self.guard_arc_radius, 0.0
        half_angle = min(
            self.max_guard_arc_half_angle,
            max(self.guard_arc_half_angle, math.radians(8.0) * (wing_count - 1)),
        )
        angular_step = 2.0 * half_angle / max(wing_count - 1, 1)
        radius = self.guard_arc_radius
        if self.minimum_guard_spacing > EPS:
            radius = max(
                radius,
                self.minimum_guard_spacing
                / (2.0 * max(math.sin(angular_step / 2.0), 1e-6)),
            )
        return radius, half_angle

    def wing_goals(self, task_or_id: Union[ThreatTask, int]) -> List[np.ndarray]:
        task = task_or_id if isinstance(task_or_id, ThreatTask) else self.get_threat(task_or_id)
        wing_count = max(0, task.guard_quota - 1)
        if wing_count == 0:
            return []
        _, threat_dir, _ = self._threat_geometry(task)
        lateral = rotate90(threat_dir)
        radius, half_angle = self._guard_arc_geometry(task)
        angles: Iterable[float]
        if wing_count == 1:
            angles = [0.0]
        else:
            angles = np.linspace(-half_angle, half_angle, wing_count)
        return [
            point3(
                horizontal(self.own_position)
                + radius * (math.cos(phi) * threat_dir + math.sin(phi) * lateral),
                0.0,
            )
            for phi in angles
        ]

    def support_goals(
        self, task_or_id: Union[ThreatTask, int], count: Optional[int] = None
    ) -> List[np.ndarray]:
        """Return a rear support arc on the sea plane that rotates with the threat."""
        task = task_or_id if isinstance(task_or_id, ThreatTask) else self.get_threat(task_or_id)
        support_count = len(self.support_guard_indices) if count is None else int(count)
        if support_count <= 0:
            return []
        _, threat_dir, _ = self._threat_geometry(task)
        center_dir = np.array(
            [
                math.cos(self.support_arc_rear_offset) * threat_dir[0]
                - math.sin(self.support_arc_rear_offset) * threat_dir[1],
                math.sin(self.support_arc_rear_offset) * threat_dir[0]
                + math.cos(self.support_arc_rear_offset) * threat_dir[1],
            ],
            dtype=float,
        )
        lateral = rotate90(center_dir)
        angles: Iterable[float]
        if support_count == 1:
            angles = [0.0]
        else:
            angles = np.linspace(-self.support_arc_half_angle, self.support_arc_half_angle, support_count)
        return [
            point3(
                horizontal(self.own_position)
                + self.support_guard_radius
                * (math.cos(phi) * center_dir + math.sin(phi) * lateral),
                0.0,
            )
            for phi in angles
        ]

    def _current_reserve_goal_offsets(self) -> List[np.ndarray]:
        if not self.reserve_guard_indices:
            return []
        threat_dir = self.composite_threat_direction()
        rear = -threat_dir
        lateral = rotate90(rear)
        if len(self.reserve_guard_indices) == 1:
            return [self.ring_radius * rear]
        return [
            self.ring_radius * normalize(rear + 0.55 * lateral),
            self.ring_radius * normalize(rear - 0.55 * lateral),
        ]

    def _current_reserve_goals(self) -> Dict[int, np.ndarray]:
        offsets = self._current_reserve_goal_offsets()
        result: Dict[int, np.ndarray] = {}
        for index, slot in self._reserve_slot_by_index.items():
            if slot < len(offsets):
                platform = self.platforms[index]
                result[index] = point3(horizontal(self.own_position) + offsets[slot], platform.altitude)
        return result

    def _assign_reserve_slots(self) -> None:
        self._reserve_slot_offsets = {}
        self._reserve_slot_by_index = {}
        if not self.reserve_guard_indices:
            return
        offsets = self._current_reserve_goal_offsets()
        candidates = self.reserve_guard_indices
        cost = np.zeros((len(offsets), len(candidates)), dtype=float)
        for row, offset in enumerate(offsets):
            goal = point3(horizontal(self.own_position) + offset, 0.0)
            for col, index in enumerate(candidates):
                cost[row, col] = horizontal_distance(self.platforms[index].position, goal)
        assignment = self._minimum_cost_assignment(cost)
        for slot, column in enumerate(assignment):
            index = candidates[column]
            self._reserve_slot_by_index[index] = slot
            self._reserve_slot_offsets[index] = offsets[slot]

    def _begin_core_dispatch(self, task: ThreatTask) -> None:
        if task.core_guard_index is None:
            task.core_motion_state = "idle"
            return
        core = self.platforms[task.core_guard_index]
        task.core_dispatch_origin = core.position.copy()
        task.core_dispatch_initial_distance = horizontal_distance(core.position, task.blocker_point)
        task.core_trajectory = [core.position.copy()]
        task.core_motion_state = "moving"

    def _replan_detected_guards(self) -> None:
        self._own_target_bypass_side = {}
        for platform in self.platforms:
            platform.role = "escort"
            platform.assigned_threat_id = None
        tasks = self.detected_threats
        for task in self.threats:
            if task not in tasks:
                task.guard_quota = 0
                task.core_guard_index = None
                task.wing_guard_indices = []
                task.wing_slot_by_index = {}
        if not tasks:
            self.reserve_guard_indices = []
            self._reserve_slot_offsets = {}
            self._reserve_slot_by_index = {}
            self.support_guard_indices = []
            self._support_slot_by_index = {}
            self._last_detected_ids = ()
            return

        self._refresh_all_blockers()
        quotas = self.guard_quota_per_detected_target()
        for task in tasks:
            task.guard_quota = quotas[task.threat_id]
            task.core_guard_index = None
            task.wing_guard_indices = []
            task.wing_slot_by_index = {}

        self.reserve_guard_indices = self._select_reserve_guards()
        reserve_set = set(self.reserve_guard_indices)
        candidates = [i for i in range(len(self.platforms)) if i not in reserve_set]

        core_cost = np.zeros((len(tasks), len(candidates)), dtype=float)
        for row, task in enumerate(tasks):
            for col, index in enumerate(candidates):
                platform = self.platforms[index]
                core_cost[row, col] = horizontal_distance(platform.position, task.blocker_point) / (
                    platform.max_speed + EPS
                )
        core_columns = self._minimum_cost_assignment(core_cost)
        used = set(reserve_set)
        for task, column in zip(tasks, core_columns):
            index = candidates[column]
            task.core_guard_index = index
            used.add(index)

        slot_records: List[Tuple[ThreatTask, int, np.ndarray]] = []
        for task in tasks:
            for slot, goal in enumerate(self.wing_goals(task)):
                slot_records.append((task, slot, goal))
        wing_candidates = [i for i in range(len(self.platforms)) if i not in used]
        if slot_records:
            wing_cost = np.zeros((len(slot_records), len(wing_candidates)), dtype=float)
            for row, (_, _, goal) in enumerate(slot_records):
                for col, index in enumerate(wing_candidates):
                    wing_cost[row, col] = horizontal_distance(self.platforms[index].position, goal)
            wing_columns = self._minimum_cost_assignment(wing_cost)
            for record, column in zip(slot_records, wing_columns):
                task, slot, _ = record
                index = wing_candidates[column]
                task.wing_guard_indices.append(index)
                task.wing_slot_by_index[index] = slot
                used.add(index)

        self.support_guard_indices = []
        self._support_slot_by_index = {}
        if len(tasks) == 1:
            task = tasks[0]
            support_candidates = [i for i in range(len(self.platforms)) if i not in used]
            support_goals = self.support_goals(task, count=len(support_candidates))
            if support_candidates:
                support_cost = np.zeros((len(support_goals), len(support_candidates)), dtype=float)
                for row, goal in enumerate(support_goals):
                    for col, index in enumerate(support_candidates):
                        support_cost[row, col] = horizontal_distance(self.platforms[index].position, goal)
                support_columns = self._minimum_cost_assignment(support_cost)
                for slot, column in enumerate(support_columns):
                    index = support_candidates[column]
                    self.support_guard_indices.append(index)
                    self._support_slot_by_index[index] = slot
                    used.add(index)

        for index in self.reserve_guard_indices:
            reserve = self.platforms[index]
            reserve.role = "reserve"
            reserve.assigned_threat_id = tasks[0].threat_id
        for index in self.support_guard_indices:
            support = self.platforms[index]
            support.role = "support"
            support.assigned_threat_id = tasks[0].threat_id
        for task in tasks:
            assert task.core_guard_index is not None
            core = self.platforms[task.core_guard_index]
            core.role = "core"
            core.assigned_threat_id = task.threat_id
            for index in task.wing_guard_indices:
                wing = self.platforms[index]
                wing.role = "wing"
                wing.assigned_threat_id = task.threat_id
            self._begin_core_dispatch(task)
            if task.state == "detected":
                task.state = "forming"
        self._assign_reserve_slots()
        self._last_detected_ids = tuple(sorted(task.threat_id for task in tasks))

    def _synchronize_guard_plan(self) -> None:
        ids = tuple(sorted(task.threat_id for task in self.detected_threats))
        if ids != self._last_detected_ids:
            self._replan_detected_guards()

    def composite_threat_direction(self) -> np.ndarray:
        tasks = self.detected_threats
        if not tasks:
            return normalize(self.forward, np.array([1.0, 0.0]))
        combined = np.zeros(2, dtype=float)
        nearest_direction = normalize(self.forward)
        nearest_distance = math.inf
        for task in tasks:
            _, direction, distance = self._threat_geometry(task)
            combined += direction / max(distance, 1.0) ** 2
            if distance < nearest_distance:
                nearest_distance = distance
                nearest_direction = direction
        return normalize(combined, nearest_direction)

    def _resolve_avoid_direction(self) -> np.ndarray:
        left = rotate90(normalize(self.forward, np.array([1.0, 0.0])))
        if self.avoidance_mode == "left":
            return left
        if self.avoidance_mode == "right":
            return -left
        lateral = float(np.dot(self.composite_threat_direction(), left))
        if lateral > 0.05:
            return -left
        if lateral < -0.05:
            return left
        return -left

    def _truncate_own_step_for_platforms(
        self, start: np.ndarray, end: np.ndarray
    ) -> np.ndarray:
        """连续缩短我方目标水平航步，避免移动中心主动穿入任一平台。"""
        start_xy = horizontal(start)
        end_xy = horizontal(end)
        direction = end_xy - start_xy
        a = float(np.dot(direction, direction))
        if a <= EPS:
            return point3(start_xy, 0.0)
        allowed = 1.0
        radius = self.own_target_avoid_radius
        for platform in self.platforms:
            relative = start_xy - horizontal(platform.position)
            start_distance = float(np.linalg.norm(relative))
            if start_distance < radius - 1e-9:
                allowed = 0.0
                continue
            closest_parameter = float(np.clip(-np.dot(relative, direction) / a, 0.0, 1.0))
            closest = relative + closest_parameter * direction
            if float(np.linalg.norm(closest)) >= radius - 1e-10:
                continue
            b = 2.0 * float(np.dot(relative, direction))
            c = float(np.dot(relative, relative) - radius**2)
            discriminant = max(0.0, b * b - 4.0 * a * c)
            root = math.sqrt(discriminant)
            roots = sorted(
                value
                for value in ((-b - root) / (2.0 * a), (-b + root) / (2.0 * a))
                if 0.0 <= value <= 1.0
            )
            if roots:
                allowed = min(allowed, max(0.0, roots[0] - 1e-8))
        return point3(start_xy + allowed * direction, 0.0)

    def _clip_position_to_world(self, position: np.ndarray, margin: float = 0.0) -> np.ndarray:
        result = np.asarray(position, dtype=float).copy()
        result[0] = float(np.clip(result[0], self.world_x_min + margin, self.world_x_max - margin))
        result[1] = float(np.clip(result[1], self.world_y_min + margin, self.world_y_max - margin))
        if result.shape[0] < 3:
            result = point3(result, 0.0)
        return result

    def _move_own_target(self) -> None:
        if not self.detected_threats:
            velocity = normalize(self.forward) * self.cruise_speed
            self.avoid_direction = np.zeros(2, dtype=float)
        else:
            self.avoid_direction = self._resolve_avoid_direction()
            desired_velocity = normalize(self.forward) * self.forward_shift + self.avoid_direction * self.avoid_distance
            velocity = self.own_gain * desired_velocity
        speed = float(np.linalg.norm(velocity))
        if speed > self.own_max_speed:
            velocity *= self.own_max_speed / (speed + EPS)
        proposed = point3(horizontal(self.own_position) + velocity * self.dt, 0.0)
        self.own_position = self._truncate_own_step_for_platforms(self.own_position, proposed)
        self.own_position = self._clip_position_to_world(self.own_position, margin=0.8)
        self.own_position[2] = 0.0
        self.own_goal = point3(horizontal(self.own_position) + velocity, 0.0)

    def _normal_ring_goals(self) -> Dict[int, np.ndarray]:
        count = len(self.platforms)
        result: Dict[int, np.ndarray] = {}
        for index, phi in enumerate(np.linspace(0.0, 2.0 * math.pi, count, endpoint=False)):
            platform = self.platforms[index]
            result[index] = point3(
                horizontal(self.own_position)
                + self.ring_radius * np.array([math.cos(phi), math.sin(phi)], dtype=float),
                platform.altitude,
            )
        return result

    def _desired_non_core_goals(self) -> Dict[int, np.ndarray]:
        if not self.detected_threats:
            return self._normal_ring_goals()

        result = self._normal_ring_goals()
        for core_index in self._core_guard_indices():
            result.pop(core_index, None)
        for task in self.detected_threats:
            goals = self.wing_goals(task)
            for index, slot in task.wing_slot_by_index.items():
                if slot < len(goals):
                    result[index] = with_altitude(goals[slot], self.platforms[index].altitude)

        if len(self.detected_threats) == 1 and self.support_guard_indices:
            task = self.detected_threats[0]
            support_goals = self.support_goals(task)
            for index, slot in self._support_slot_by_index.items():
                if slot < len(support_goals):
                    result[index] = with_altitude(support_goals[slot], self.platforms[index].altitude)

        result.update(self._current_reserve_goals())
        return result

    def _core_guard_indices(self) -> set[int]:
        return {
            task.core_guard_index
            for task in self.detected_threats
            if task.core_guard_index is not None
        }

    def _repulsion_velocity(self, index: int) -> np.ndarray:
        if index in self._core_guard_indices():
            return np.zeros(2, dtype=float)
        current = horizontal(self.platforms[index].position)
        repulsion = np.zeros(2, dtype=float)
        for other_index, other in enumerate(self.platforms):
            if other_index == index:
                continue
            diff = current - horizontal(other.position)
            distance = float(np.linalg.norm(diff))
            if EPS < distance < self.safe_distance:
                repulsion += (
                    self.repulsion_gain
                    * (1.0 / distance - 1.0 / self.safe_distance)
                    * diff
                    / distance
                )
        return repulsion

    @property
    def own_target_route_radius(self) -> float:
        return self.own_target_avoid_radius + self._own_target_route_margin

    def _segment_intersects_own_target_circle(
        self, start: np.ndarray, end: np.ndarray, radius: Optional[float] = None
    ) -> bool:
        start_xy = horizontal(start)
        end_xy = horizontal(end)
        center = horizontal(self.own_position)
        protected_radius = self.own_target_avoid_radius if radius is None else float(radius)
        segment = end_xy - start_xy
        denominator = float(np.dot(segment, segment))
        if denominator <= EPS:
            return float(np.linalg.norm(start_xy - center)) < protected_radius - EPS
        parameter = float(np.clip(np.dot(center - start_xy, segment) / denominator, 0.0, 1.0))
        closest = start_xy + parameter * segment
        return float(np.linalg.norm(closest - center)) < protected_radius - EPS

    @staticmethod
    def _directed_arc_delta(start_angle: float, end_angle: float, side: int) -> float:
        if side > 0:
            return float((end_angle - start_angle) % (2.0 * math.pi))
        return float((start_angle - end_angle) % (2.0 * math.pi))

    def _bypass_path_length(self, current: np.ndarray, goal: np.ndarray, side: int) -> float:
        center = horizontal(self.own_position)
        radius = self.own_target_route_radius
        p = horizontal(current) - center
        g = horizontal(goal) - center
        pd = max(float(np.linalg.norm(p)), radius)
        gd = max(float(np.linalg.norm(g)), radius)
        pa = math.atan2(p[1], p[0])
        ga = math.atan2(g[1], g[0])
        p_alpha = math.acos(float(np.clip(radius / pd, 0.0, 1.0)))
        g_alpha = math.acos(float(np.clip(radius / gd, 0.0, 1.0)))
        start_tangent = pa + side * p_alpha
        end_tangent = ga - side * g_alpha
        arc = self._directed_arc_delta(start_tangent, end_tangent, side)
        return (
            math.sqrt(max(0.0, pd * pd - radius * radius))
            + radius * arc
            + math.sqrt(max(0.0, gd * gd - radius * radius))
        )

    def _choose_bypass_side(self, index: int, current: np.ndarray, goal: np.ndarray) -> int:
        existing = self._own_target_bypass_side.get(index)
        if existing in {-1, 1}:
            return existing
        ccw = self._bypass_path_length(current, goal, 1)
        cw = self._bypass_path_length(current, goal, -1)
        side = (1 if index % 2 == 0 else -1) if abs(ccw - cw) <= 1e-9 else (1 if ccw < cw else -1)
        self._own_target_bypass_side[index] = side
        return side

    def _truncate_step_before_safety_circle(self, start: np.ndarray, end: np.ndarray) -> np.ndarray:
        if not self._segment_intersects_own_target_circle(start, end):
            return np.asarray(end, dtype=float).copy()
        altitude = float(np.asarray(start, dtype=float)[2])
        start_xy = horizontal(start)
        end_xy = horizontal(end)
        direction = end_xy - start_xy
        a = float(np.dot(direction, direction))
        if a <= EPS:
            return point3(start_xy, altitude)
        relative = start_xy - horizontal(self.own_position)
        b = 2.0 * float(np.dot(relative, direction))
        c = float(np.dot(relative, relative) - self.own_target_avoid_radius**2)
        disc = max(0.0, b * b - 4.0 * a * c)
        root = math.sqrt(disc)
        roots = [(-b - root) / (2.0 * a), (-b + root) / (2.0 * a)]
        valid = [value for value in roots if 0.0 <= value <= 1.0]
        if not valid:
            return point3(start_xy, altitude)
        return point3(start_xy + max(0.0, min(valid) - 1e-8) * direction, altitude)

    def _safe_route_waypoint(
        self, index: int, current: np.ndarray, goal: np.ndarray, max_step: float
    ) -> np.ndarray:
        """在水平面绕过安全圆，同时保留平台固定高度。"""
        altitude = self.platforms[index].altitude
        center = horizontal(self.own_position)
        route_radius = self.own_target_route_radius
        current_xy = horizontal(current)
        goal_xy = horizontal(goal)
        current_relative = current_xy - center
        goal_relative = goal_xy - center
        current_distance = float(np.linalg.norm(current_relative))
        goal_distance = float(np.linalg.norm(goal_relative))

        if goal_distance < route_radius:
            goal_relative = normalize(goal_relative, current_relative) * route_radius
            goal_xy = center + goal_relative

        goal3 = point3(goal_xy, altitude)
        if current_distance >= route_radius - 1e-8 and not self._segment_intersects_own_target_circle(current, goal3, route_radius):
            self._own_target_bypass_side.pop(index, None)
            return goal3

        side = self._choose_bypass_side(index, current, goal3)
        radial = normalize(current_relative, -goal_relative)
        tangent = side * rotate90(radial)
        radial_error = current_distance - route_radius
        if radial_error > max(0.25, 1.5 * max_step):
            steering = tangent - 0.85 * radial
        else:
            correction = float(np.clip(-2.5 * radial_error / max(max_step, 1e-6), -1.4, 1.8))
            steering = tangent + correction * radial
        return point3(current_xy + normalize(steering, tangent) * max_step, altitude)

    def _move_platform_safely(
        self, index: int, goal: np.ndarray, *, include_repulsion: bool = False
    ) -> None:
        platform = self.platforms[index]
        current = platform.position.copy()
        goal3 = with_altitude(goal, platform.altitude)
        max_step = platform.max_speed * self.dt
        waypoint = self._safe_route_waypoint(index, current, goal3, max_step)
        velocity = platform.gain * (horizontal(waypoint) - horizontal(current))
        if include_repulsion and index not in self._own_target_bypass_side:
            velocity += self._repulsion_velocity(index)
        speed = float(np.linalg.norm(velocity))
        if speed > platform.max_speed:
            velocity *= platform.max_speed / (speed + EPS)
        proposed = point3(horizontal(current) + velocity * self.dt, platform.altitude)
        proposed = self._truncate_step_before_safety_circle(current, proposed)
        platform.position = self._clip_position_to_world(proposed, margin=0.2)
        platform.position[2] = platform.altitude if platform.kind == "UAV" else 0.0
        platform.goal = goal3.copy()

    def _move_platforms(self) -> None:
        cores = self._core_guard_indices()
        goals = self._desired_non_core_goals()
        for index, platform in enumerate(self.platforms):
            if index in cores:
                continue
            self._move_platform_safely(index, goals.get(index, platform.position), include_repulsion=True)
        for task in self.detected_threats:
            if task.core_guard_index is None:
                continue
            core_index = task.core_guard_index
            core_goal = with_altitude(task.blocker_point, self.platforms[core_index].altitude)
            self._move_platform_safely(core_index, core_goal)
            core = self.platforms[core_index]
            core.role = "core"
            core.assigned_threat_id = task.threat_id
            task.core_trajectory.append(core.position.copy())
            if len(task.core_trajectory) > self.core_trail_length:
                task.core_trajectory = task.core_trajectory[-self.core_trail_length :]
            task.core_motion_state = "holding" if self.core_guard_arrived(task.threat_id) else "moving"

    def core_remaining_distance(self, threat_id: int) -> float:
        task = self.get_threat(threat_id)
        if task.core_guard_index is None:
            return math.inf
        return horizontal_distance(self.platforms[task.core_guard_index].position, task.blocker_point)

    def core_guard_arrived(self, threat_id: int) -> bool:
        task = self.get_threat(threat_id)
        if task.core_guard_index is None:
            return False
        return self.core_remaining_distance(threat_id) <= self.core_arrival_tolerance

    def wing_arrival_ratio(self, threat_id: int) -> float:
        task = self.get_threat(threat_id)
        goals = self.wing_goals(task)
        if not task.wing_guard_indices:
            return 1.0
        arrived = 0
        for index in task.wing_guard_indices:
            slot = task.wing_slot_by_index[index]
            if slot < len(goals):
                error = horizontal_distance(self.platforms[index].position, goals[slot])
                if error <= self.wing_arrival_tolerance:
                    arrived += 1
        return arrived / len(task.wing_guard_indices)

    def formation_ready(self, threat_id: int) -> bool:
        task = self.get_threat(threat_id)
        return bool(
            task.state in {"detected", "forming", "orbiting"}
            and self.core_guard_arrived(threat_id)
            and self.wing_arrival_ratio(threat_id) + EPS >= self.wing_ready_ratio
        )

    def _controlled_track_radius(self, task: ThreatTask) -> float:
        """Return the single controlled orbit radius."""
        return float(
            max(
                self.enemy_min_radius,
                min(self.enemy_min_radius + 1.4, self.sensor_radius - 0.6),
            )
        )

    def controlled_track_error(self, task_or_id: Union[ThreatTask, int]) -> float:
        task = task_or_id if isinstance(task_or_id, ThreatTask) else self.get_threat(task_or_id)
        distance = horizontal_distance(task.position, self.own_position)
        return abs(distance - self._controlled_track_radius(task))

    def target_on_controlled_track(
        self, task_or_id: Union[ThreatTask, int], tolerance: Optional[float] = None
    ) -> bool:
        """Return whether a target has reached its assigned radial track."""
        tol = (
            max(
                1e-8,
                self.own_max_speed * self.dt
                + self.enemy_forming_speed * self.dt * 0.05,
            )
            if tolerance is None
            else float(tolerance)
        )
        return self.controlled_track_error(task_or_id) <= tol + EPS

    def _enter_controlled_motion(self, task: ThreatTask) -> None:
        relative = horizontal(task.position) - horizontal(self.own_position)
        task.controlled_radius = self._controlled_track_radius(task)
        task.controlled_angle = math.atan2(relative[1], relative[0])
        task.state = "orbiting"
        task.orbit_segment_count = 0
        task.orbit_direction_changes = 0
        self._start_random_orbit_segment(task)
        direction_label = "逆时针" if task.orbit_direction > 0 else "顺时针"
        self.last_message = f"T1 守卫队形形成，开始随机分段环绕；当前方向：{direction_label}"

    def _update_control_transitions(self) -> None:
        for task in self.detected_threats:
            if (
                task.state in {"detected", "forming"}
                and self.formation_ready(task.threat_id)
                and self.target_on_controlled_track(task)
            ):
                self._enter_controlled_motion(task)

    def threat_bearing_label(self, task: ThreatTask) -> str:
        _, direction, _ = self._threat_geometry(task)
        left = rotate90(normalize(self.forward))
        angle = math.degrees(math.atan2(float(np.dot(direction, left)), float(np.dot(direction, self.forward))))
        if angle < 0.0:
            angle += 360.0
        labels = ("正前方", "左前方", "正左方", "左后方", "正后方", "右后方", "正右方", "右前方")
        sector = int(((angle + 22.5) % 360.0) // 45.0)
        return f"{labels[sector]}（{angle:.1f}°）"

    def step(self) -> None:
        if self.paused:
            return
        self.frame += 1
        self._spawn_due_threats()

        # 先让敌方目标按当前状态运动，再执行感知判定。
        for task in self.threats:
            self._move_enemy(task)
        detection_changed = self._detect_new_threats()
        if detection_changed:
            self._replan_detected_guards()
        else:
            self._synchronize_guard_plan()

        self._move_own_target()
        self._refresh_all_blockers()
        self._move_platforms()
        self._update_control_transitions()

        detected = len(self.detected_threats)
        approaching = sum(task.state == "approaching" for task in self.threats)
        controlled = sum(task.state == "orbiting" for task in self.threats)
        if detected == 0:
            self.phase = f"正常护航：{approaching} 个远距离目标正在接近"
        elif controlled == detected:
            self.phase = f"持续动态盯防：{controlled} 个目标处于受控机动"
        else:
            self.phase = f"守卫编队形成中：已感知 {detected} 个目标"

    def status(self) -> Dict[str, object]:
        records = []
        for task in self.threats:
            distance = horizontal_distance(task.position, self.own_position)
            records.append(
                {
                    "threat_id": task.threat_id,
                    "state": task.state,
                    "state_label": STATE_LABELS[task.state],
                    "spawn_frame": task.spawn_frame,
                    "position": task.position.copy(),
                    "distance": distance,
                    "detected": task.state in DETECTED_STATES,
                    "motion": "随机角度分段环绕",
                    "orbit_direction": ("逆时针" if task.orbit_direction > 0 else "顺时针"),
                    "orbit_segment_angle_deg": math.degrees(task.orbit_segment_angle),
                    "orbit_segment_remaining_deg": math.degrees(task.orbit_segment_remaining),
                    "orbit_segment_count": task.orbit_segment_count,
                    "orbit_direction_changes": task.orbit_direction_changes,
                    "bearing": self.threat_bearing_label(task) if task.state != "waiting" else "未出现",
                    "guard_quota": task.guard_quota,
                    "guard_track_radius": (
                        self._guard_arc_geometry(task)[0]
                        if task.state in DETECTED_STATES else 0.0
                    ),
                    "core_guard": (
                        self.platforms[task.core_guard_index].identifier
                        if task.core_guard_index is not None else None
                    ),
                    "wing_ready_ratio": self.wing_arrival_ratio(task.threat_id) if task.state in DETECTED_STATES else 0.0,
                    "core_ready": self.core_guard_arrived(task.threat_id) if task.state in DETECTED_STATES else False,
                }
            )
        return {
            "frame": self.frame,
            "phase": self.phase,
            "message": self.last_message,
            "paused": self.paused,
            "sensor_radius": self.sensor_radius,
            "enemy_count": self.enemy_count,
            "spawn_mode": self.spawn_mode,
            "detected_count": len(self.detected_threats),
            "reserve_count": len(self.reserve_guard_indices),
            "support_count": len(self.support_guard_indices),
            "normal_escort_count": max(
                0,
                len(self.platforms)
                - len(self.forward_guard_indices)
                - len(self.support_guard_indices)
                - len(self.reserve_guard_indices),
            ),
            "uav_count": self.num_uav,
            "usv_count": self.num_usv,
            "threats": records,
        }


class EscortGuardVisualizer:
    """局部与全局双三维视图。运动控制仍在水平面，Z 轴显示固定高度。"""

    FRIEND_UAV_COLOR = "#00acc1"
    FRIEND_USV_COLOR = "#43a047"
    OWN_TARGET_COLOR = "#0d47a1"
    ENEMY_COLOR = "#e53935"
    CORE_EDGE_COLOR = "#ffca28"
    NORMAL_EDGE_COLOR = "#1f2933"
    SEA_COLOR = "#81d4fa"

    def __init__(self, simulator: EscortGuardSimulator) -> None:
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
        from matplotlib.lines import Line2D

        self.plt = plt
        self.Line2D = Line2D
        self.sim = simulator
        self.animation = None
        self.min_view_half_width = 19.0
        self.min_view_half_height = 12.0
        self.view_padding = 2.5
        self.view_aspect_ratio = self.min_view_half_width / self.min_view_half_height

        preferred_fonts = [
            "Microsoft YaHei",
            "SimHei",
            "Noto Sans CJK SC",
            "Arial Unicode MS",
            "DejaVu Sans",
        ]
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

        self.fig = plt.figure(figsize=(18, 8.8))
        self.local_ax = self.fig.add_subplot(1, 2, 1, projection="3d")
        self.global_ax = self.fig.add_subplot(1, 2, 2, projection="3d")
        self.global_ax.view_init(elev=90.0, azim=-90.0)
        # self.global_ax.set_proj_type("ortho")
        self.ax = self.local_ax
        self.fig.subplots_adjust(
            wspace=0.04, left=0.035, right=0.985, top=0.91, bottom=0.07
        )
        self.fig.canvas.mpl_connect("key_press_event", self.on_key)
        self._refresh_artists()

    def _scene_points_for_view(self) -> np.ndarray:
        points: List[np.ndarray] = [self.sim.own_position.copy()]
        points.extend(platform.position.copy() for platform in self.sim.platforms)
        for task in self.sim.spawned_threats:
            points.append(task.position.copy())
            if task.state in DETECTED_STATES:
                points.append(task.blocker_point.copy())
        return np.asarray(points, dtype=float)

    def _local_limits(self) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        points = self._scene_points_for_view()
        own_xy = horizontal(self.sim.own_position)
        relative = points[:, :2] - own_xy if len(points) else np.zeros((1, 2))
        max_x = float(np.max(np.abs(relative[:, 0]))) if len(relative) else 0.0
        max_y = float(np.max(np.abs(relative[:, 1]))) if len(relative) else 0.0
        half_width = max(self.min_view_half_width, max_x + self.view_padding)
        half_height = max(self.min_view_half_height, max_y + self.view_padding)
        if half_width / half_height < self.view_aspect_ratio:
            half_width = half_height * self.view_aspect_ratio
        else:
            half_height = half_width / self.view_aspect_ratio
        x, y = own_xy
        return (x - half_width, x + half_width), (y - half_height, y + half_height)

    @staticmethod
    def _set_line3d(line, points: np.ndarray) -> None:
        if points.size == 0:
            line.set_data_3d([], [], [])
            return
        line.set_data_3d(points[:, 0], points[:, 1], points[:, 2])

    def _guard_arc_polyline(self, task: ThreatTask) -> np.ndarray:
        if task.state not in DETECTED_STATES or task.guard_quota <= 1:
            return np.empty((0, 3))
        _, direction, _ = self.sim._threat_geometry(task)
        lateral = rotate90(direction)
        radius, half_angle = self.sim._guard_arc_geometry(task)
        phis = np.linspace(-half_angle, half_angle, 90)
        return np.array(
            [
                point3(
                    horizontal(self.sim.own_position)
                    + radius
                    * (math.cos(phi) * direction + math.sin(phi) * lateral),
                    0.0,
                )
                for phi in phis
            ]
        )

    def _support_arc_polyline(self) -> np.ndarray:
        if len(self.sim.detected_threats) != 1 or not self.sim.support_guard_indices:
            return np.empty((0, 3))
        task = self.sim.detected_threats[0]
        _, threat_dir, _ = self.sim._threat_geometry(task)
        center_dir = np.array(
            [
                math.cos(self.sim.support_arc_rear_offset) * threat_dir[0]
                - math.sin(self.sim.support_arc_rear_offset) * threat_dir[1],
                math.sin(self.sim.support_arc_rear_offset) * threat_dir[0]
                + math.cos(self.sim.support_arc_rear_offset) * threat_dir[1],
            ],
            dtype=float,
        )
        lateral = rotate90(center_dir)
        phis = np.linspace(
            -self.sim.support_arc_half_angle,
            self.sim.support_arc_half_angle,
            90,
        )
        return np.array(
            [
                point3(
                    horizontal(self.sim.own_position)
                    + self.sim.support_guard_radius
                    * (math.cos(phi) * center_dir + math.sin(phi) * lateral),
                    0.0,
                )
                for phi in phis
            ]
        )

    def _draw_sea_and_boundary(
        self,
        ax,
        x_limits: Tuple[float, float],
        y_limits: Tuple[float, float],
    ) -> None:
        x0, x1 = x_limits
        y0, y1 = y_limits
        xx, yy = np.meshgrid(np.array([x0, x1]), np.array([y0, y1]))
        zz = np.zeros_like(xx)
        ax.plot_surface(
            xx,
            yy,
            zz,
            color=self.SEA_COLOR,
            alpha=0.10,
            shade=False,
            linewidth=0,
            zorder=0,
        )
        bx = [x0, x1, x1, x0, x0]
        by = [y0, y0, y1, y1, y0]
        ax.plot(bx, by, [0.0] * 5, color="#455a64", linewidth=1.3, alpha=0.75)

    def _platform_style(self, platform: Platform) -> Tuple[str, str, float, str]:
        if platform.kind == "UAV":
            face = self.FRIEND_UAV_COLOR
            marker = "o"
            base_size = 86.0
        else:
            face = self.FRIEND_USV_COLOR
            marker = "s"
            base_size = 82.0
        if platform.role == "core":
            return face, self.CORE_EDGE_COLOR, base_size * 1.45, marker
        if platform.role == "wing":
            return face, "#f9a825", base_size * 1.10, marker
        if platform.role == "support":
            return face, "#1565c0", base_size, marker
        if platform.role == "reserve":
            return face, "#2e7d32", base_size, marker
        return face, self.NORMAL_EDGE_COLOR, base_size, marker

    def _draw_platforms(self, ax, *, local: bool) -> None:
        size_scale = 1.0 if local else 0.55
        label_offset = 1.7 if local else 1.1
        for platform in self.sim.platforms:
            x, y, z = platform.position
            face, edge, size, marker = self._platform_style(platform)
            ax.scatter(
                [x],
                [y],
                [z],
                marker=marker,
                s=size * size_scale,
                c=[face],
                edgecolors=[edge],
                linewidths=2.2 if platform.role == "core" else 1.2,
                depthshade=True,
                zorder=8,
            )
            if platform.kind == "UAV":
                ax.plot(
                    [x, x],
                    [y, y],
                    [0.0, z],
                    linestyle="--",
                    linewidth=0.9,
                    color=self.FRIEND_UAV_COLOR,
                    alpha=0.42,
                    zorder=2,
                )
                ax.scatter(
                    [x], [y], [0.0], marker=".", s=18 * size_scale,
                    c=[self.FRIEND_UAV_COLOR], alpha=0.48, zorder=3
                )
            suffix = f"/T{platform.assigned_threat_id}" if platform.assigned_threat_id else ""
            altitude_text = f"\n{z:.1f}" if platform.kind == "UAV" else ""
            ax.text(
                x,
                y,
                z + label_offset,
                # platform.identifier + suffix + altitude_text,
                platform.identifier,
                ha="center",
                va="bottom",
                fontsize=7.2 if local else 5.4,
                color="#263238",
                weight="bold" if platform.role == "core" else "normal",
                zorder=10,
            )

    def _draw_common_scene(self, ax, *, local: bool) -> None:
        own_x, own_y, own_z = self.sim.own_position
        ax.scatter(
            [own_x], [own_y], [own_z], marker="o", s=160 if local else 85,
            c=[self.OWN_TARGET_COLOR], edgecolors=["#082d65"], linewidths=1.6,
            depthshade=True, zorder=9
        )
        ax.text(
            own_x, own_y, own_z + 1.6,
            "高价值目标", ha="center", va="bottom",
            fontsize=8 if local else 5.8, color=self.OWN_TARGET_COLOR, weight="bold"
        )

        circle_angles = np.linspace(0.0, 2.0 * math.pi, 180)
        sensor_x = own_x + self.sim.sensor_radius * np.cos(circle_angles)
        sensor_y = own_y + self.sim.sensor_radius * np.sin(circle_angles)
        ax.plot(
            sensor_x, sensor_y, np.zeros_like(sensor_x),
            linestyle="--", linewidth=1.5, color="#1976d2", alpha=0.68,
            label="感知范围"
        )

        heading_end = horizontal(self.sim.own_position) + normalize(self.sim.forward) * 3.0
        # ax.plot(
        #     [own_x, heading_end[0]], [own_y, heading_end[1]], [0.4, 0.4],
        #     color="#1f4e79", linewidth=2.0
        # )
        if self.sim.detected_threats:
            avoid_end = horizontal(self.sim.own_position) + self.sim.avoid_direction * 3.0
            # ax.plot(
            #     [own_x, avoid_end[0]], [own_y, avoid_end[1]], [0.7, 0.7],
            #     color="#00695c", linewidth=2.0, linestyle="--"
            # )

        self._draw_platforms(ax, local=local)

        for task in self.sim.spawned_threats:
            x, y, z = task.position
            ax.scatter(
                [x], [y], [z], marker="^", s=145 if local else 80,
                c=[self.ENEMY_COLOR], edgecolors=["#7f0000"], linewidths=1.5,
                depthshade=True, zorder=9
            )
            ax.text(
                x, y, z + 1.4,
                f"敌方 T{task.threat_id}\n{STATE_LABELS[task.state]}",
                ha="center", va="bottom", fontsize=7.5 if local else 5.3,
                color="#8b0000", weight="bold"
            )
            if task.state in DETECTED_STATES:
                # ax.plot(
                #     [own_x, x], [own_y, y], [0.0, 0.0],
                #     linestyle="--", linewidth=1.4,
                #     color=self.ENEMY_COLOR, alpha=0.75
                # )
                bx, by, bz = task.blocker_point
                ax.scatter(
                    [bx], [by], [bz], marker="x", s=85 if local else 45,
                    c=[self.CORE_EDGE_COLOR], linewidths=2.2, zorder=10
                )
                arc = self._guard_arc_polyline(task)
                if len(arc):
                    ax.plot(
                        arc[:, 0], arc[:, 1], arc[:, 2],
                        color="#f57c00", linewidth=2.0, alpha=0.82
                    )

        support_arc = self._support_arc_polyline()
        if len(support_arc):
            ax.plot(
                support_arc[:, 0], support_arc[:, 1], support_arc[:, 2],
                color="#1565c0", linestyle="-.", linewidth=1.8, alpha=0.80
            )

    def _status_lines(self) -> List[str]:
        status = self.sim.status()
        lines = [
            f"帧：{status['frame']}｜UAV/USV：{status['uav_count']}/{status['usv_count']}",
            f"阶段：{status['phase']}",
            f"已感知：{status['detected_count']}｜直接守卫：{sum(item['guard_quota'] for item in status['threats'])}",
            f"动态支援：{status['support_count']}｜预留：{status['reserve_count']}",
            "UAV 高度：固定随机 10–50｜USV 高度：0",
        ]
        for item in status["threats"]:
            if item["state"] == "orbiting":
                lines.append(
                    f"T1 {item['orbit_direction']}｜本段 {item['orbit_segment_angle_deg']:.0f}°"
                    f"｜剩余 {item['orbit_segment_remaining_deg']:.0f}°"
                )
            else:
                lines.append(f"T1 {item['state_label']}｜距离 {item['distance']:.2f}")
        lines.append("运行中" if not status["paused"] else "已暂停")
        return lines

    def _configure_axis(self, ax, *, local: bool) -> None:
        ax.cla()
        if local:
            x_limits, y_limits = self._local_limits()
            title = "局部 3D 视图（跟随我方高价值目标）"
            box_aspect = (1.65, 1.05, 1.0)
        else:
            # own_x, own_y = self.sim.own_position[:2]
            # # own_x, own_y = self.sim.world_x_min, self.sim.world_x_max
            # th = 0.8
            # x_limits = (own_x - 28.0 * th, own_x + 28.0 * th)
            # y_limits = (own_y - 18.0 * th, own_y + 18.0 * th)
            x_limits = (self.sim.world_x_min, self.sim.world_x_max)
            y_limits = (self.sim.world_y_min, self.sim.world_y_max)
            title = "全局 3D 视图（固定长方体空间）"
            box_aspect = (1.75, 1.10, 0.72)

        self._draw_sea_and_boundary(ax, x_limits, y_limits)
        self._draw_common_scene(ax, local=local)
        ax.set_xlim(*x_limits)
        ax.set_ylim(*y_limits)
        ax.set_zlim(VIEW_Z_MIN, VIEW_Z_MAX)
        ax.set_xlabel("X / 海里（示意）", labelpad=8)
        ax.set_ylabel("Y / 海里（示意）", labelpad=8)
        ax.set_zlabel("高度 Z", labelpad=7)
        ax.set_title(title, fontsize=12.5, weight="bold", pad=14)
        # ax.view_init(elev=24.0, azim=-58.0)
        ax.set_box_aspect(box_aspect)
        ax.grid(True, alpha=0.28, linestyle="--")

        status_text = "\n".join(self._status_lines()) if local else (
            "固定全局空间\n"
            f"X：[{self.sim.world_x_min:.0f}, {self.sim.world_x_max:.0f}]\n"
            f"Y：[{self.sim.world_y_min:.0f}, {self.sim.world_y_max:.0f}]\n"
            f"Z：[{VIEW_Z_MIN:.0f}, {VIEW_Z_MAX:.0f}]\n"
            "N：仅重置敌方目标"
        )
        ax.text2D(
            0.985, 0.985, status_text,
            transform=ax.transAxes, ha="right", va="top", fontsize=8.2,
            bbox=dict(facecolor="white", alpha=0.88, edgecolor="#78909c", boxstyle="round,pad=0.42")
        )
        ax.text2D(
            0.015, 0.015,
            "Space：暂停/继续   N：仅重置敌方目标   Esc：关闭",
            transform=ax.transAxes, ha="left", va="bottom", fontsize=8.0,
            bbox=dict(facecolor="white", alpha=0.80, edgecolor="#90a4ae")
        )

        legend_handles = [
            self.Line2D([0], [0], marker="o", color="none", markerfacecolor=self.FRIEND_UAV_COLOR,
                        markeredgecolor=self.NORMAL_EDGE_COLOR, markersize=8, label="我方 UAV"),
            self.Line2D([0], [0], marker="s", color="none", markerfacecolor=self.FRIEND_USV_COLOR,
                        markeredgecolor=self.NORMAL_EDGE_COLOR, markersize=8, label="我方 USV"),
            self.Line2D([0], [0], marker="D", color="none", markerfacecolor=self.OWN_TARGET_COLOR,
                        markeredgecolor="#082d65", markersize=8, label="高价值目标"),
            self.Line2D([0], [0], marker="^", color="none", markerfacecolor=self.ENEMY_COLOR,
                        markeredgecolor="#7f0000", markersize=8, label="敌方"),
            self.Line2D([0], [0], marker="o", color="none", markerfacecolor=self.FRIEND_UAV_COLOR,
                        markeredgecolor=self.CORE_EDGE_COLOR, markeredgewidth=2, markersize=8, label="核心守卫"),
        ]
        ax.legend(handles=legend_handles, loc="lower right", fontsize=7.5, framealpha=0.9)

    def _refresh_artists(self) -> Tuple[object, ...]:
        self._configure_axis(self.local_ax, local=True)
        self._configure_axis(self.global_ax, local=False)
        self.fig.suptitle(
            "单目标随机环绕 UAV/USV 三维护航守卫仿真",
            fontsize=15,
            weight="bold",
        )
        return tuple()

    def update(self, _frame: int) -> Tuple[object, ...]:
        self.sim.step()
        return self._refresh_artists()

    def on_key(self, event) -> None:
        key = (event.key or "").lower()
        if key in {" ", "space"}:
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

    def save_snapshot(self, path: Union[str, Path], dpi: int = 150) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        self._refresh_artists()
        self.fig.savefig(output, dpi=dpi, bbox_inches="tight")
        return output

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sensor-radius", type=float, default=DEFAULT_SENSOR_RADIUS)
    parser.add_argument("--reserve-count", type=int, choices=(0, 2), default=ESCORT_RESERVE_COUNT, help="是否保留 2 个贴身守卫：0 表示不保留，2 表示保留")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--headless-frames", type=int, default=0, metavar="N")
    parser.add_argument("--save-snapshot", type=str, default=None, metavar="PATH")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.headless_frames < 0:
        raise SystemExit("--headless-frames must be non-negative")
    if args.headless_frames or args.save_snapshot:
        import matplotlib
        matplotlib.use("Agg")
    sim = EscortGuardSimulator(
        sensor_radius=args.sensor_radius,
        seed=args.seed,
        num_uav=NUM_UAV,
        num_usv=NUM_USV,
        escort_reserve_count=args.reserve_count,
    )
    for _ in range(args.headless_frames):
        sim.step()
    if args.save_snapshot:
        visualizer = EscortGuardVisualizer(sim)
        output = visualizer.save_snapshot(args.save_snapshot)
        print(f"Snapshot saved: {output.resolve()}")
        visualizer.plt.close(visualizer.fig)
    if args.headless_frames:
        status = sim.status()
        print(
            "Headless dynamic-threat run completed: "
            f"frames={status['frame']}, enemies={status['enemy_count']}, "
            f"detected={status['detected_count']}, phase={status['phase']}, reserve={args.reserve_count}"
        )
        return 0
    print(
        f"UAV={NUM_UAV}, USV={NUM_USV}; 单目标随机方向出现；"
        f"随机环绕角度={RANDOM_ORBIT_MIN_ANGLE_DEG:.0f}°~{RANDOM_ORBIT_MAX_ANGLE_DEG:.0f}°；"
        f"感知半径={args.sensor_radius}; reserve_count={args.reserve_count}; "
        f"全局画布=[{WORLD_X_MIN},{WORLD_X_MAX}]x[{WORLD_Y_MIN},{WORLD_Y_MAX}]."
    )
    EscortGuardVisualizer(sim).show()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
