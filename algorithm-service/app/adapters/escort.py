from __future__ import annotations

import importlib
import math
import time
from typing import Dict, List, Tuple

import numpy as np

from app.adapters.base import AlgorithmAdapter
from app.navigation import TASK_CENTER_SCENE_MAP, SceneSafetyFilter
from app.schemas import AgentFrame, RuntimeFrame, TargetFrame


class EscortAdapter(AlgorithmAdapter):
    """Expose the 727 single-threat escort controller as runtime frames.

    The vendor simulator works in the same horizontal coordinate system as the
    Task Center.  Its original radii describe point agents, however, so the
    adapter supplies a Unity-safe formation whose slots already clear the
    rendered craft.  SceneSafetyFilter remains a final guard, not the primary
    formation controller.
    """

    code = "ESCORT_GUARD"
    _NATIVE_TO_SCENE_SCALE = 0.75

    _DIRECTION_ANGLES = {
        "front": 0.0,
        "front_left": math.pi / 4.0,
        "left": math.pi / 2.0,
        "rear_left": 3.0 * math.pi / 4.0,
        "rear": math.pi,
        "rear_right": 5.0 * math.pi / 4.0,
        "right": 3.0 * math.pi / 2.0,
        "front_right": 7.0 * math.pi / 4.0,
    }

    def __init__(self, run_id: int, config: Dict[str, object] | None = None) -> None:
        super().__init__(run_id, config)
        source = importlib.import_module("app.vendor.escort_guard_source")
        self.source = source
        self.safety = SceneSafetyFilter(TASK_CENTER_SCENE_MAP)

        speed_setting = self.config.get("escort_speed", self.config.get("escortSpeed", "LOW"))
        if isinstance(speed_setting, str) and speed_setting.upper() in {"LOW", "MEDIUM"}:
            cruise_speed = {"LOW": 0.075, "MEDIUM": 0.10}[speed_setting.upper()]
        else:
            cruise_speed = min(0.12, max(0.06, float(speed_setting)))

        reserve_count = int(
            self.config.get("reserve_count", self.config.get("reserveCount", 0))
        )
        if reserve_count not in {0, 2}:
            reserve_count = 0

        # The protected vessel is 13.5 m long in Unity.  An 18 m escort ring
        # leaves a visible water gap around it and keeps the three same-domain
        # craft roughly 31 m apart.
        scale = self._NATIVE_TO_SCENE_SCALE
        num_uav = max(1, min(100, int(self.config.get("uavCount", 3))))
        num_usv = max(1, min(100, int(self.config.get("usvCount", 3))))

        self.sim = source.EscortGuardSimulator(
            sensor_radius=26.0 / scale,
            seed=int(self.config.get("seed", 42)),
            num_uav=num_uav,
            num_usv=num_usv,
            escort_reserve_count=reserve_count,
            ring_radius=18.0 / scale,
            guard_arc_radius=20.0 / scale,
            support_guard_radius=18.0 / scale,
            support_arc_half_angle_deg=60.0,
            guard_arc_half_angle_deg=45.0,
            max_guard_arc_half_angle_deg=72.0,
            minimum_guard_spacing=11.0 / scale,
            blocker_ratio=0.45,
            blocker_r_min=14.5 / scale,
            blocker_r_max=17.5 / scale,
            core_arrival_tolerance=0.50 / scale,
            wing_arrival_tolerance=0.70 / scale,
            wing_ready_ratio=1.0,
            enemy_approach_speed=0.10 / scale,
            enemy_forming_speed=0.12 / scale,
            enemy_controlled_speed=0.20 / scale,
            enemy_min_radius=18.0 / scale,
            avoidance_mode="auto",
            avoid_distance=2.5 / scale,
            forward_shift=4.0 / scale,
            own_max_speed=cruise_speed * 1.2 / scale,
            own_gain=0.08,
            cruise_speed=cruise_speed / scale,
            safe_distance=11.0 / scale,
            repulsion_gain=1.8 / (scale * scale),
            own_target_avoid_radius=14.0 / scale,
            dt=1.0,
        )

        # A roughly 157 m open-water patrol route gives the escort experiment a
        # meaningful cruise phase.  Every waypoint leaves room for the complete
        # 18 m guard ring and rendered hull footprints.
        self.route = [
            (-28.0, -12.0),
            (-6.0, -17.0),
            (22.0, -13.0),
            (30.0, 2.0),
            (18.0, 17.0),
            (-8.0, 18.0),
            (-30.0, 8.0),
            (-28.0, -12.0),
        ]
        self.route_index = 1
        self._route_lengths = [
            float(np.linalg.norm(np.asarray(right) - np.asarray(left)))
            for left, right in zip(self.route, self.route[1:])
        ]
        self._route_total_length = max(sum(self._route_lengths), 1e-9)

        start = np.asarray(self.route[0], dtype=float)
        self._transform_simulation_to_scene(start, scale)
        self._configure_threat_schedule()

        self.previous: Dict[str, Tuple[float, float, float]] = {}
        self.avoidance_count = 0
        self.manual_threat: Tuple[float, float] | None = None

    def _transform_simulation_to_scene(
        self,
        scene_origin: np.ndarray,
        scale: float,
    ) -> None:
        """Uniformly scale/translate the native (-52, 0) scene into Unity."""

        native_origin = self.sim.own_position.copy()
        scene_origin = np.asarray(scene_origin, dtype=float)

        def transform(point: np.ndarray) -> np.ndarray:
            return scene_origin + scale * (np.asarray(point, dtype=float) - native_origin)

        self.sim.own_position = transform(self.sim.own_position)
        self.sim.own_goal = transform(self.sim.own_goal)
        self.sim.initial_own_position = scene_origin.copy()
        for platform in self.sim.platforms:
            platform.position = transform(platform.position)
            platform.max_speed *= scale
            if platform.goal is not None:
                platform.goal = transform(platform.goal)
        for task in self.sim.threats:
            task.position = transform(task.position)
            task.blocker_point = transform(task.blocker_point)
            task.spawn_radius *= scale
            task.current_speed_limit *= scale
            task.core_dispatch_initial_distance *= scale
            task.controlled_radius *= scale
            if task.core_dispatch_origin is not None:
                task.core_dispatch_origin = transform(task.core_dispatch_origin)
            task.core_trajectory = [transform(point) for point in task.core_trajectory]

        for name in (
            "sensor_radius",
            "ring_radius",
            "guard_arc_radius",
            "support_guard_radius",
            "minimum_guard_spacing",
            "blocker_r_min",
            "blocker_r_max",
            "core_arrival_tolerance",
            "wing_arrival_tolerance",
            "enemy_approach_speed",
            "enemy_forming_speed",
            "enemy_controlled_speed",
            "enemy_min_radius",
            "avoid_distance",
            "forward_shift",
            "own_max_speed",
            "cruise_speed",
            "safe_distance",
            "own_target_avoid_radius",
            "_own_target_route_margin",
        ):
            setattr(self.sim, name, float(getattr(self.sim, name)) * scale)
        self.sim.repulsion_gain *= scale * scale

        min_x, max_x, min_y, max_y = self.safety.bounds
        self.sim.world_x_min = min_x
        self.sim.world_x_max = max_x
        self.sim.world_y_min = min_y
        self.sim.world_y_max = max_y

    def _configure_threat_schedule(self) -> None:
        threat_frame = max(
            1,
            int(self.config.get("threat_frame", self.config.get("threatFrame", 70))),
        )
        direction_setting = self.config.get(
            "threat_direction", self.config.get("threatDirection")
        )
        for task in self.sim.threats:
            task.spawn_frame = threat_frame
            if direction_setting is None:
                continue
            angle = self._DIRECTION_ANGLES.get(str(direction_setting).lower())
            if angle is None:
                continue
            task.spawn_angle = angle
            task.position = self.sim.own_position + task.spawn_radius * np.asarray(
                [math.cos(angle), math.sin(angle)], dtype=float
            )

    def place_threat(self, x: float, y: float) -> None:
        requested = np.asarray([float(x), float(y)], dtype=float)
        if requested.shape != (2,) or not np.all(np.isfinite(requested)):
            raise ValueError("Threat position must contain two finite coordinates")

        task = self.sim.get_threat(1)
        direction = self.source.normalize(
            requested - self.sim.own_position,
            self.sim.forward,
        )
        minimum_radius = max(
            self.sim.enemy_min_radius,
            self.safety.required_separation(
                "ESCORT_TARGET", "THREAT_TARGET", 0.0, 0.0
            )
            + 0.5,
        )
        if float(np.linalg.norm(requested - self.sim.own_position)) < minimum_radius:
            requested = self.sim.own_position + direction * minimum_radius
        requested = self.sim._clip_position_to_world(requested, margin=0.2)
        safe = self.safety.constrain(
            (float(requested[0]), float(requested[1]), 0.0),
            (float(requested[0]), float(requested[1]), 0.0),
            "THREAT_TARGET",
            (),
            0.0,
        )

        task.position = np.asarray([safe.x, safe.y], dtype=float)
        task.spawn_frame = self.sim.frame
        task.state = "detected"
        task.detected_frame = self.sim.frame
        task.current_speed_limit = self.sim.enemy_forming_speed
        task.controlled_radius = 0.0
        task.orbit_segment_remaining = 0.0
        self.manual_threat = (safe.x, safe.y)
        self.previous["TARGET"] = (safe.x, safe.y, 0.0)
        self.sim.last_message = "已接收人工威胁位置，重新部署守卫编队"
        self.sim._replan_detected_guards()

    def _advance_route(self) -> None:
        waypoint = np.asarray(self.route[self.route_index], dtype=float)
        distance = float(np.linalg.norm(waypoint - self.sim.own_position))
        if distance < 0.9:
            self.route_index = (
                self.route_index + 1
                if self.route_index < len(self.route) - 1
                else 1
            )
            waypoint = np.asarray(self.route[self.route_index], dtype=float)
        self.sim.forward = self.source.normalize(
            waypoint - self.sim.own_position,
            self.sim.forward,
        )
        self.sim.own_goal = waypoint

    def _route_progress(self) -> float:
        if self.route_index >= len(self.route):
            return 1.0
        completed = sum(self._route_lengths[: max(0, self.route_index - 1)])
        segment_length = self._route_lengths[self.route_index - 1]
        remaining = float(
            np.linalg.norm(
                np.asarray(self.route[self.route_index], dtype=float)
                - self.sim.own_position
            )
        )
        completed += max(0.0, min(segment_length, segment_length - remaining))
        return max(0.0, min(1.0, completed / self._route_total_length))

    @staticmethod
    def _platform_code(platform: object) -> str:
        code_no = int(platform.identifier[1:])
        return f"{platform.kind}-{code_no:02d}"

    @staticmethod
    def _platform_altitude(platform: object) -> float:
        if platform.kind != "UAV":
            return 0.0
        return 18.0 + int(platform.identifier[1:]) * 2.0

    def _apply_safety(
        self,
        fixed: Dict[str, Tuple[str, Tuple[float, float, float]]],
    ) -> List[AgentFrame]:
        proposals: Dict[str, Tuple[str, Tuple[float, float, float]]] = {}
        platforms: Dict[str, object] = {}
        for platform in self.sim.platforms:
            code = self._platform_code(platform)
            z = self._platform_altitude(platform)
            proposals[code] = (
                platform.kind,
                (float(platform.position[0]), float(platform.position[1]), z),
            )
            platforms[code] = platform

        resolved = self.safety.resolve_group(
            proposals,
            self.previous,
            fixed,
        )
        result: List[AgentFrame] = []
        for code, platform in platforms.items():
            safe = resolved[code]
            previous = self.previous.get(code)
            scene = (safe.x, safe.y, safe.z)
            capped = False
            if previous is not None:
                dx = scene[0] - previous[0]
                dy = scene[1] - previous[1]
                distance = math.hypot(dx, dy)
                max_step = 0.35 if platform.kind == "UAV" else 0.18
                if distance > max_step + 1e-9:
                    scale = max_step / distance
                    scene = (
                        previous[0] + dx * scale,
                        previous[1] + dy * scale,
                        scene[2],
                    )
                    capped = True
            if safe.adjusted or capped:
                self.avoidance_count += 1
            # Always feed the executed position back into the planner.  Keeping
            # an unprojected hidden state is the main cause of repeated
            # algorithm/safety oscillation.
            platform.position = np.asarray([scene[0], scene[1]], dtype=float)
            heading = self.stabilize_heading(
                code,
                previous,
                scene,
                math.degrees(
                    math.atan2(float(self.sim.forward[1]), float(self.sim.forward[0]))
                )
                % 360.0,
                3.0 if platform.kind == "UAV" else 1.5,
            )
            self.previous[code] = scene
            result.append(
                AgentFrame(
                    code,
                    platform.kind,
                    *scene,
                    heading,
                    platform.role.upper(),
                )
            )
        return result

    def step(self) -> RuntimeFrame:
        self.sequence += 1
        self._advance_route()
        self.sim.step()

        own_raw = (
            float(self.sim.own_position[0]),
            float(self.sim.own_position[1]),
            0.0,
        )
        own_previous = self.previous.get("ESCORT_TARGET", own_raw)
        own_safe = self.safety.constrain(
            own_previous,
            own_raw,
            "ESCORT_TARGET",
            (),
            0.0,
        )
        self.sim.own_position = np.asarray([own_safe.x, own_safe.y], dtype=float)
        own_scene = (own_safe.x, own_safe.y, 0.0)
        self.previous["ESCORT_TARGET"] = own_scene
        escort_heading = self.stabilize_heading(
            "ESCORT_TARGET",
            own_previous,
            own_scene,
            math.degrees(
                math.atan2(float(self.sim.forward[1]), float(self.sim.forward[0]))
            )
            % 360.0,
            3.0,
        )

        targets = [
            TargetFrame(
                "ESCORT_TARGET",
                "ESCORT_TARGET",
                own_safe.x,
                own_safe.y,
                0.0,
                escort_heading,
            )
        ]
        fixed: Dict[str, Tuple[str, Tuple[float, float, float]]] = {
            "ESCORT_TARGET": ("ESCORT_TARGET", own_scene),
        }

        task = self.sim.get_threat(1)
        threat_visible = task.state != "waiting"
        if threat_visible:
            threat_raw = (
                float(task.position[0]),
                float(task.position[1]),
                0.0,
            )
            threat_safe = self.safety.constrain(
                self.previous.get("TARGET", threat_raw),
                threat_raw,
                "THREAT_TARGET",
                (),
                0.0,
            )
            task.position = np.asarray([threat_safe.x, threat_safe.y], dtype=float)
            threat_scene = (threat_safe.x, threat_safe.y, 0.0)
            self.previous["TARGET"] = threat_scene
            threat_heading = math.degrees(
                math.atan2(
                    float(task.position[1] - self.sim.own_position[1]),
                    float(task.position[0] - self.sim.own_position[0]),
                )
            ) % 360.0
            targets.append(
                TargetFrame(
                    "TARGET",
                    "THREAT_TARGET",
                    *threat_scene,
                    threat_heading,
                )
            )
            fixed["TARGET"] = ("THREAT_TARGET", threat_scene)

        self.sim._refresh_all_blockers()
        agents = self._apply_safety(fixed)
        self.sim._refresh_all_blockers()

        detected = task.state in self.source.DETECTED_STATES
        formation_ready = (
            bool(self.sim.formation_ready(task.threat_id)) if detected else False
        )
        status = self.sim.status()
        threat_status = status["threats"][0]

        if task.state == "orbiting":
            phase = "ORBITING"
        elif task.state in {"detected", "forming"}:
            phase = "FORMING"
        elif task.state == "approaching":
            phase = "APPROACHING"
        else:
            phase = "ESCORTING"

        metrics = {
            "progress": round(self._route_progress(), 3),
            "strictBlocking": bool(threat_status["core_ready"]) if detected else False,
            "formationReady": formation_ready,
            "coreGuard": threat_status["core_guard"],
            "wingReadyRatio": round(float(threat_status["wing_ready_ratio"]), 3),
            "avoidanceCount": self.avoidance_count,
            "threatActive": detected,
            "threatVisible": threat_visible,
            "threatState": task.state.upper(),
            "orbitDirection": (
                "COUNTERCLOCKWISE" if task.orbit_direction > 0 else "CLOCKWISE"
            ),
            "orbitSegment": task.orbit_segment_count,
            "escortFormationRadius": 18.0,
            "guardArcRadius": 20.0,
            "minimumUsvSpacing": round(
                self.safety.required_separation("USV", "USV"),
                2,
            ),
        }
        return RuntimeFrame(
            self.run_id,
            self.code,
            self.sequence,
            int(time.time() * 1000),
            phase,
            agents,
            targets,
            metrics,
            route=[[x, y] for x, y in self.route],
            obstacles=[],
            # The new escort controller is a persistent guard process.  Runtime
            # completion remains an explicit operator/backend action.
            terminalStatus=None,
        )
