from __future__ import annotations

import contextlib
import importlib
import math
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

from app.adapters.base import AlgorithmAdapter
from app.navigation import SceneSafetyFilter
from app.schemas import AgentFrame, RuntimeFrame, TargetFrame


class CaptureAdapter(AlgorithmAdapter):
    code = "GB_SFLA_CS"

    def __init__(self, run_id: int, config: Dict[str, object] | None = None) -> None:
        super().__init__(run_id, config)
        matplotlib_cache = Path(tempfile.gettempdir()) / "uav-usv-matplotlib"
        matplotlib_cache.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("MPLCONFIGDIR", str(matplotlib_cache))
        with contextlib.redirect_stdout(sys.stderr):
            source = importlib.import_module("app.vendor.gb_sfla_cs_source")
            source.SEED = int(self.config.get("seed", 42))
            source.ARENA_SIZE_XY = 300
            source.ARENA_SIZE_Z = 120
            source.UAV_COUNT = 3
            source.USV_COUNT = 3
            source.TARGET_COUNT = 1
            source.MIN_CAPTURE_AGENTS = 6
            # Keep the vendor's three-dimensional capture sphere compatible
            # with the rendered hull clearance.  A radius of 32 put the USV
            # just outside the sphere after the safety solver separated it
            # from the target, so the fleet could surround forever without
            # completing the mission.
            source.CAPTURE_RADIUS = 42
            source.TARGET_RUN_NUM = 70
            # The vendor defaults are algorithm-scale values, not render-safe
            # world speeds.  At 10 frames/s they previously produced 13-22
            # Unity units/s and looked like teleportation.  These limits keep
            # a visible transit phase before the fleet closes the ring.
            source.V_MAX_UAV = 1.8
            source.V_MAX_USV = 1.2
            target_behavior = str(self.config.get("target_behavior", self.config.get("targetBehavior", "MOVING"))).upper()
            source.TARGET_SPEED = 0.55 if target_behavior != "STATIC" else 0
            source.TARGET_IS_STATIC = 1 if source.TARGET_SPEED == 0 else 0
            source.UAV_Z_MIN, source.UAV_Z_MAX = 18, 54
            self.source = source
            self.env = source.SwarmEnv3D()
            self._reset_positions()
        self.safety = SceneSafetyFilter()
        self.previous_scene: Dict[str, Tuple[float, float, float]] = {}
        self.avoidance_count = 0
        target = self._to_scene(self.env.targets[0, :3], "TARGET")
        self.initial_mean_distance = float(np.mean([
            math.hypot(self._to_scene(raw[:3], "UAV" if int(raw[6]) == 0 else "USV")[0] - target[0],
                       self._to_scene(raw[:3], "UAV" if int(raw[6]) == 0 else "USV")[1] - target[1])
            for raw in self.env.agents
        ]))

    def _reset_positions(self) -> None:
        # A real approach leg is part of the demonstration: the mixed fleet
        # departs from the south-west water/air corridor and must traverse the
        # scene before forming the encirclement around the north-east target.
        positions = np.asarray([
            [15, 50, 30], [15, 150, 38], [15, 250, 46],
            [78, 50, 0], [150, 40, 0], [222, 50, 0],
        ], dtype=float)
        self.env.agents[:, :3] = positions
        self.env.agents[:, 3] = 0
        self.env.targets[0, :5] = np.asarray([249, 210, 0, self.source.TARGET_SPEED, math.pi / 2])

    def _to_scene(self, position: np.ndarray, kind: str) -> Tuple[float, float, float]:
        x = (float(position[0]) - 150.0) / 4.5
        y = (float(position[1]) - 150.0) / 5.0
        z = 0.0 if kind != "UAV" else 9.0 + float(position[2]) / 4.5
        return x, y, z

    def _to_internal(self, position: Tuple[float, float, float], kind: str) -> np.ndarray:
        x, y, z = position
        return np.asarray([x * 4.5 + 150.0, y * 5.0 + 150.0, 0.0 if kind != "UAV" else max(18.0, (z - 9.0) * 4.5)])

    def step(self) -> RuntimeFrame:
        self.sequence += 1
        with contextlib.redirect_stdout(sys.stderr):
            self.env.step()

        target_scene = self._to_scene(self.env.targets[0, :3], "TARGET")
        target_previous = self.previous_scene.get("TARGET", target_scene)
        safe_target = self.safety.constrain(target_previous, target_scene, "TARGET", (), 0.0)
        self.previous_scene["TARGET"] = (safe_target.x, safe_target.y, safe_target.z)
        self.env.targets[0, :3] = self._to_internal((safe_target.x, safe_target.y, 0.0), "TARGET")

        escort_scene = (-18.0, -12.0, 0.0)
        proposals: Dict[str, Tuple[str, Tuple[float, float, float]]] = {}
        rows: Dict[str, Tuple[int, np.ndarray]] = {}
        agents: List[AgentFrame] = []
        uav_no = usv_no = 0
        for index, raw in enumerate(self.env.agents):
            kind = "UAV" if int(raw[6]) == 0 else "USV"
            if kind == "UAV":
                uav_no += 1
                code = f"UAV-{uav_no:02d}"
            else:
                usv_no += 1
                code = f"USV-{usv_no:02d}"
            proposals[code] = (kind, self._to_scene(raw[:3], kind))
            rows[code] = (index, raw)

        resolved = self.safety.resolve_group(
            proposals,
            self.previous_scene,
            {
                "TARGET": ("CAPTURE_TARGET", (safe_target.x, safe_target.y, 0.0)),
                "ESCORT_TARGET": ("ESCORT_TARGET", escort_scene),
            },
        )
        for code, (index, raw) in rows.items():
            kind = proposals[code][0]
            safe = resolved[code]
            previous_scene = self.previous_scene.get(code)
            if safe.adjusted:
                self.avoidance_count += 1
                self.env.agents[index, :3] = self._to_internal((safe.x, safe.y, safe.z), kind)
            scene = (safe.x, safe.y, safe.z)
            self.previous_scene[code] = scene
            heading = self.stabilize_heading(
                code,
                previous_scene,
                scene,
                math.degrees(float(raw[4])) % 360.0,
                6.0 if kind == "UAV" else 3.5,
            )
            agents.append(AgentFrame(code, kind, *scene, heading, "ENCIRCLEMENT"))
        captured = 0 in self.env.permanently_captured
        mean_distance = float(np.mean([
            math.hypot(agent.x - safe_target.x, agent.y - safe_target.y)
            for agent in agents
        ]))
        phase = "CAPTURED" if captured else ("TRANSIT" if mean_distance > 15.0 else "ENCIRCLEMENT")
        metrics = {
            "progress": 1.0 if captured else round(min(0.95, max(0.0, 1.0 - mean_distance / max(1.0, self.initial_mean_distance))), 3),
            "captured": captured,
            "captureAgents": len(self.env.target_captors.get(0, set())),
            "requiredCaptureAgents": 6,
            "avoidanceCount": self.avoidance_count,
            "totalDistance": round(float(self.env.total_travel_distance), 3),
            "meanDistanceToTarget": round(mean_distance, 3),
        }
        return RuntimeFrame(
            self.run_id, self.code, self.sequence, int(time.time() * 1000), phase,
            agents,
            [
                TargetFrame("TARGET", "CAPTURE_TARGET", safe_target.x, safe_target.y, 0.0, math.degrees(float(self.env.targets[0, 4])) % 360.0),
                # The protected vessel belongs to the shared scene. It remains
                # stationary during capture and becomes route-driven only in
                # the escort algorithm.
                TargetFrame("ESCORT_TARGET", "ESCORT_TARGET", *escort_scene, 0.0),
            ],
            metrics,
            # Obstacles stay authoritative in the safety solver but are hidden
            # from the clean Task Center 2-D/3-D presentation.
            obstacles=[],
            terminalStatus="COMPLETED" if captured and self.sequence > 12 else None,
        )
