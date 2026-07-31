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
from app.navigation import TASK_CENTER_SCENE_MAP, SceneSafetyFilter
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
            # The Task Center maps three native units to one scene metre.
            # Surface craft finish on a 22 m ring; UAVs finish on a 30 m
            # triangle at 26 m altitude.  The two layers remain readable in
            # both the fixed 2-D frame and Unity's fixed experiment camera.
            source.CAPTURE_RADIUS = 135
            source.CAPTURE_FORMATION_USV_RADIUS = 66
            source.CAPTURE_FORMATION_UAV_RADIUS = 90
            source.CAPTURE_FORMATION_UAV_ALTITUDE = 75
            source.CAPTURE_FORMATION_PHASE = -math.pi / 2
            source.TARGET_RUN_NUM = 70
            # The vendor defaults are algorithm-scale values, not render-safe
            # world speeds.  At 10 frames/s they previously produced 13-22
            # Unity units/s and looked like teleportation.  These limits keep
            # a visible transit phase before the fleet closes the ring.
            source.V_MAX_UAV = 2.0
            source.V_MAX_USV = 0.9
            target_behavior = str(self.config.get("target_behavior", self.config.get("targetBehavior", "MOVING"))).upper()
            source.TARGET_SPEED = 0.35 if target_behavior != "STATIC" else 0
            source.TARGET_IS_STATIC = 1 if source.TARGET_SPEED == 0 else 0
            source.UAV_Z_MIN, source.UAV_Z_MAX = 18, 54
            self.source = source
            self.env = source.SwarmEnv3D()
            self._reset_positions()
        self.safety = SceneSafetyFilter(TASK_CENTER_SCENE_MAP)
        self.previous_scene: Dict[str, Tuple[float, float, float]] = {}
        self.avoidance_count = 0
        self.captured_at_sequence: int | None = None
        self.formation_ready_at_sequence: int | None = None
        target = self._to_scene(self.env.targets[0, :3], "TARGET")
        self.initial_mean_distance = float(np.mean([
            math.hypot(self._to_scene(raw[:3], "UAV" if int(raw[6]) == 0 else "USV")[0] - target[0],
                       self._to_scene(raw[:3], "UAV" if int(raw[6]) == 0 else "USV")[1] - target[1])
            for raw in self.env.agents
        ]))

    def _reset_positions(self) -> None:
        # A deliberately wide deployment makes the approach phase observable.
        # Same-domain craft start at least 31 m apart and travel roughly
        # 42-68 m before settling into their assigned formation slots.
        positions = np.asarray([
            [15, 45, 55], [15, 150, 65], [15, 255, 75],
            [2, 48, 0], [2, 150, 0], [2, 252, 0],
        ], dtype=float)
        self.env.agents[:, :3] = positions
        self.env.agents[:, 3] = 0
        self.env.targets[0, :5] = np.asarray([180, 150, 0, self.source.TARGET_SPEED, math.pi / 2])

    def _to_scene(self, position: np.ndarray, kind: str) -> Tuple[float, float, float]:
        # One uniform horizontal scale keeps the algorithm's circular capture
        # geometry circular in both Task Center 2-D and Unity 3-D.
        x = (float(position[0]) - 150.0) / 3.0
        y = (float(position[1]) - 150.0) / 3.0
        z = 0.0 if kind != "UAV" else 9.0 + float(position[2]) / 4.4
        return x, y, z

    def _to_internal(self, position: Tuple[float, float, float], kind: str) -> np.ndarray:
        x, y, z = position
        return np.asarray([x * 3.0 + 150.0, y * 3.0 + 150.0, 0.0 if kind != "UAV" else max(18.0, (z - 9.0) * 4.4)])

    def step(self) -> RuntimeFrame:
        self.sequence += 1
        with contextlib.redirect_stdout(sys.stderr):
            self.env.step()

        # The protected vessel is inactive in capture mode. Keep it clear of
        # every USV approach corridor so the capture experiment is not bent by
        # an unrelated static hull.
        escort_scene = (45.0, -28.0, 0.0)
        target_scene = self._to_scene(self.env.targets[0, :3], "TARGET")
        target_previous = self.previous_scene.get("TARGET", target_scene)
        safe_target = self.safety.constrain(
            target_previous,
            target_scene,
            "TARGET",
            (escort_scene,),
            self.safety.required_separation(
                "CAPTURE_TARGET",
                "ESCORT_TARGET",
                0.0,
                0.0,
            ),
        )
        self.previous_scene["TARGET"] = (safe_target.x, safe_target.y, safe_target.z)
        self.env.targets[0, :3] = self._to_internal((safe_target.x, safe_target.y, 0.0), "TARGET")

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
            scene = (safe.x, safe.y, safe.z)
            capped = False
            if previous_scene is not None:
                dx = scene[0] - previous_scene[0]
                dy = scene[1] - previous_scene[1]
                distance = math.hypot(dx, dy)
                max_step = 0.35 if kind == "UAV" else 0.18
                if distance > max_step + 1e-9:
                    scale = max_step / distance
                    scene = (
                        previous_scene[0] + dx * scale,
                        previous_scene[1] + dy * scale,
                        scene[2],
                    )
                    capped = True
            if safe.adjusted or capped:
                self.avoidance_count += 1
                self.env.agents[index, :3] = self._to_internal(scene, kind)
            self.previous_scene[code] = scene
            heading = self.stabilize_heading(
                code,
                previous_scene,
                scene,
                math.degrees(float(raw[4])) % 360.0,
                3.0 if kind == "UAV" else 1.5,
            )
            agents.append(AgentFrame(code, kind, *scene, heading, "ENCIRCLEMENT"))
        captured = 0 in self.env.permanently_captured
        if captured and self.captured_at_sequence is None:
            self.captured_at_sequence = self.sequence
        mean_distance = float(np.mean([
            math.hypot(agent.x - safe_target.x, agent.y - safe_target.y)
            for agent in agents
        ]))
        usv_radii = [
            math.hypot(agent.x - safe_target.x, agent.y - safe_target.y)
            for agent in agents
            if agent.type == "USV"
        ]
        uav_radii = [
            math.hypot(agent.x - safe_target.x, agent.y - safe_target.y)
            for agent in agents
            if agent.type == "UAV"
        ]
        formation_ready = (
            captured
            and len(usv_radii) == 3
            and len(uav_radii) == 3
            and all(abs(radius - 22.0) <= 1.0 for radius in usv_radii)
            and all(abs(radius - 30.0) <= 1.2 for radius in uav_radii)
        )
        if formation_ready and self.formation_ready_at_sequence is None:
            self.formation_ready_at_sequence = self.sequence
        elif not formation_ready:
            self.formation_ready_at_sequence = None
        phase = (
            "CAPTURED"
            if formation_ready
            else ("TRANSIT" if mean_distance > 35.0 else "ENCIRCLEMENT")
        )
        metrics = {
            "progress": 1.0 if captured else round(min(0.95, max(0.0, 1.0 - mean_distance / max(1.0, self.initial_mean_distance))), 3),
            "captured": captured,
            "formationReady": formation_ready,
            "captureAgents": len(
                self.env.guarding_agents.get(0, set())
                if captured
                else self.env.target_captors.get(0, set())
            ),
            "requiredCaptureAgents": 6,
            "avoidanceCount": self.avoidance_count,
            "totalDistance": round(float(self.env.total_travel_distance), 3),
            "meanDistanceToTarget": round(mean_distance, 3),
            "captureRadius": 45.0,
            "usvFormationRadius": 22.0,
            "uavFormationRadius": 30.0,
            "uavFormationAltitude": 26.0,
            "minimumUsvSpacing": round(
                self.safety.required_separation("USV", "USV"),
                2,
            ),
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
            terminalStatus=(
                "COMPLETED"
                if formation_ready
                and self.formation_ready_at_sequence is not None
                and self.sequence >= self.formation_ready_at_sequence + 20
                else None
            ),
        )
