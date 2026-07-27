from __future__ import annotations

import importlib
import math
import time
from typing import Dict, List, Tuple

import numpy as np

from app.adapters.base import AlgorithmAdapter
from app.navigation import SceneSafetyFilter
from app.schemas import AgentFrame, RuntimeFrame, TargetFrame


class EscortAdapter(AlgorithmAdapter):
    code = "ESCORT_GUARD"

    def __init__(self, run_id: int, config: Dict[str, object] | None = None) -> None:
        super().__init__(run_id, config)
        source = importlib.import_module("app.vendor.escort_guard_source")
        self.source = source
        speed_setting = self.config.get("escort_speed", self.config.get("escortSpeed", "LOW"))
        if isinstance(speed_setting, str) and speed_setting.upper() in {"LOW", "MEDIUM"}:
            cruise_speed = {"LOW": 0.075, "MEDIUM": 0.10}[speed_setting.upper()]
        else:
            cruise_speed = min(0.11, max(0.05, float(speed_setting)))
        threat_direction = str(self.config.get("threat_direction", self.config.get("threatDirection", "front_right")))
        self.sim = source.EscortGuardSimulator(
            scene=threat_direction,
            avoidance_mode="auto",
            threat_active=False,
            seed=int(self.config.get("seed", 42)),
            num_uav=3,
            num_usv=3,
            total_forward_guards=3,
            cruise_speed=cruise_speed,
            own_max_speed=cruise_speed * 1.2,
            safe_distance=0.9,
        )
        # Start clear of the shore-base footprint; the visual is hidden in the
        # Task Center, while its collision area remains active.
        self.route = [
            (-16.0, -20.0), (-4.0, -22.0), (10.0, -19.0), (24.0, -12.0),
            (29.0, 0.0), (27.0, 12.0), (18.0, 20.0), (7.0, 21.0),
        ]
        self.route_index = 1
        start = np.asarray(self.route[0], dtype=float)
        offset = start - self.sim.own_position
        self.sim.own_position += offset
        self.sim.own_goal += offset
        self.sim.enemy_position += offset
        for platform in self.sim.platforms:
            platform.position += offset
            if platform.goal is not None:
                platform.goal += offset
        self.safety = SceneSafetyFilter()
        self.previous: Dict[str, Tuple[float, float, float]] = {}
        self.avoidance_count = 0
        self.manual_threat: Tuple[float, float] | None = None

    def place_threat(self, x: float, y: float) -> None:
        self.manual_threat = (float(x), float(y))
        self.sim.activate_threat_at(np.asarray(self.manual_threat, dtype=float))

    def _advance_route(self) -> None:
        waypoint = np.asarray(self.route[self.route_index], dtype=float)
        delta = waypoint - self.sim.own_position
        distance = float(np.linalg.norm(delta))
        if distance < 0.8 and self.route_index < len(self.route) - 1:
            self.route_index += 1
            waypoint = np.asarray(self.route[self.route_index], dtype=float)
            delta = waypoint - self.sim.own_position
            distance = float(np.linalg.norm(delta))
        direction = self.source.normalize(delta, np.asarray([1.0, 0.0]))
        self.sim.forward = direction
        if not self.sim.threat_active:
            # The simulator advances the protected vessel exactly once in its
            # step.  The old adapter advanced it here as well, doubling speed.
            self.sim.own_goal = waypoint
        else:
            self.sim.own_goal = waypoint + self.sim.avoid_direction * min(2.5, self.sim.avoid_distance * 0.45)

    def _apply_safety(self, fixed: Dict[str, Tuple[str, Tuple[float, float, float]]]) -> List[AgentFrame]:
        proposals: Dict[str, Tuple[str, Tuple[float, float, float]]] = {}
        platforms: Dict[str, object] = {}
        for platform in self.sim.platforms:
            code_no = int(platform.identifier[1:])
            code = f"{platform.kind}-{code_no:02d}"
            z = 14.0 + code_no * 1.5 if platform.kind == "UAV" else 0.0
            proposals[code] = (platform.kind, (float(platform.position[0]), float(platform.position[1]), z))
            platforms[code] = platform

        resolved = self.safety.resolve_group(proposals, self.previous, fixed)
        result: List[AgentFrame] = []
        for code, platform in platforms.items():
            safe = resolved[code]
            previous = self.previous.get(code)
            if safe.adjusted:
                self.avoidance_count += 1
                platform.position = np.asarray([safe.x, safe.y], dtype=float)
            heading = self.stabilize_heading(
                code,
                previous,
                (safe.x, safe.y, safe.z),
                math.degrees(math.atan2(float(self.sim.forward[1]), float(self.sim.forward[0]))) % 360.0,
                6.0 if platform.kind == "UAV" else 3.5,
            )
            self.previous[code] = (safe.x, safe.y, safe.z)
            result.append(AgentFrame(code, platform.kind, safe.x, safe.y, safe.z, heading, platform.role.upper()))
        return result

    def step(self) -> RuntimeFrame:
        self.sequence += 1
        self._advance_route()
        threat_frame = int(self.config.get("threat_frame", self.config.get("threatFrame", 70)))
        if self.sequence == threat_frame and not self.sim.threat_active:
            threat = self.manual_threat or (self.sim.own_position[0] + 10.0, self.sim.own_position[1] + 8.0)
            self.sim.activate_threat_at(np.asarray(threat, dtype=float))
        elif self.sim.threat_active:
            delta = self.sim.own_position - self.sim.enemy_position
            distance = float(np.linalg.norm(delta))
            if distance > 5.0:
                self.sim.enemy_position += self.source.normalize(delta) * 0.035
            self.sim._refresh_blocker_point()
            self.sim._update_avoidance_goal()
        self.sim.step()

        own = (float(self.sim.own_position[0]), float(self.sim.own_position[1]), 0.0)
        own_safe = self.safety.constrain(self.previous.get("ESCORT_TARGET", own), own, "ESCORT_TARGET", (), 0.0)
        self.sim.own_position = np.asarray([own_safe.x, own_safe.y], dtype=float)
        self.previous["ESCORT_TARGET"] = (own_safe.x, own_safe.y, 0.0)
        escort_heading = math.degrees(math.atan2(float(self.sim.forward[1]), float(self.sim.forward[0]))) % 360.0
        targets = [TargetFrame("ESCORT_TARGET", "ESCORT_TARGET", own_safe.x, own_safe.y, 0.0, escort_heading)]
        fixed: Dict[str, Tuple[str, Tuple[float, float, float]]] = {
            "ESCORT_TARGET": ("ESCORT_TARGET", (own_safe.x, own_safe.y, 0.0)),
        }
        if self.sim.threat_active:
            enemy = (float(self.sim.enemy_position[0]), float(self.sim.enemy_position[1]), 0.0)
            enemy_safe = self.safety.constrain(self.previous.get("TARGET", enemy), enemy, "THREAT_TARGET", (), 0.0)
            self.sim.enemy_position = np.asarray([enemy_safe.x, enemy_safe.y], dtype=float)
            self.previous["TARGET"] = (enemy_safe.x, enemy_safe.y, 0.0)
            targets.append(TargetFrame("TARGET", "THREAT_TARGET", enemy_safe.x, enemy_safe.y, 0.0))
            fixed["TARGET"] = ("THREAT_TARGET", (enemy_safe.x, enemy_safe.y, 0.0))

        agents = self._apply_safety(fixed)

        at_end = self.route_index == len(self.route) - 1 and np.linalg.norm(np.asarray(self.route[-1]) - self.sim.own_position) < 1.2
        phase = "COMPLETED" if at_end else ("THREAT_RESPONSE" if self.sim.threat_active else "ESCORTING")
        route_progress = (self.route_index - 1) / max(1, len(self.route) - 1)
        metrics = {
            "progress": 1.0 if at_end else round(min(0.98, route_progress), 3),
            "strictBlocking": bool(self.sim.strict_blocking_satisfied()) if self.sim.threat_active else False,
            "coreGuard": self.sim.status()["core_guard"],
            "avoidanceCount": self.avoidance_count,
            "threatActive": self.sim.threat_active,
        }
        return RuntimeFrame(
            self.run_id, self.code, self.sequence, int(time.time() * 1000), phase,
            agents, targets, metrics,
            route=[[x, y] for x, y in self.route],
            obstacles=[],
            terminalStatus="COMPLETED" if at_end else None,
        )
