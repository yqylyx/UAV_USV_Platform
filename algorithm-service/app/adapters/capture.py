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
from app.navigation import TASK_CENTER_SCENE_MAP, SafePoint, SceneSafetyFilter
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
            source.UAV_COUNT = max(1, min(100, int(self.config.get("uavCount", 3))))
            source.USV_COUNT = max(1, min(100, int(self.config.get("usvCount", 3))))
            source.TARGET_COUNT = max(1, min(1, int(self.config.get("targetCount", 1))))
            source.MIN_CAPTURE_AGENTS = min(6, source.UAV_COUNT + source.USV_COUNT)
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
            self._initial_frame_pending = True
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
        # Build a layout matching the configured fleet size. The previous
        # six-row fixture worked for 3+3 only and caused a broadcasting error
        # as soon as the algorithm created a larger agent array.
        def grid_positions(
            count: int,
            x_min: float,
            x_max: float,
            z_min: float,
            z_step: float,
        ) -> List[List[float]]:
            columns = max(1, int(math.ceil(math.sqrt(count))))
            rows = max(1, int(math.ceil(count / columns)))
            positions: List[List[float]] = []
            for index in range(count):
                row, column = divmod(index, columns)
                x = x_min if columns == 1 else x_min + (x_max - x_min) * column / (columns - 1)
                # Keep the generated fleet inside the Task Center safety
                # bounds after _to_scene() converts native coordinates by
                # (value - 150) / 3.  The old 25..275 range became
                # -41.67..41.67 and pinned edge UAVs to the boundary.
                y = 45.0 if rows == 1 else 45.0 + 210.0 * row / (rows - 1)
                positions.append([x, y, z_min + (index % 4) * z_step])
            return positions

        positions = np.asarray(
            grid_positions(self.source.UAV_COUNT, 0.0, 150.0, 45.0, 8.0)
            + grid_positions(self.source.USV_COUNT, 150.0, 300.0, 0.0, 0.0),
            dtype=float,
        )
        initial_poses = self.initial_pose_map()
        for index in range(self.source.UAV_COUNT + self.source.USV_COUNT):
            kind = "UAV" if index < self.source.UAV_COUNT else "USV"
            number = index + 1 if kind == "UAV" else index - self.source.UAV_COUNT + 1
            code = f"{kind}-{number:03d}"
            pose = initial_poses.get(code)
            if pose is None:
                continue
            east, north, up = self.initial_pose_to_local(pose)
            positions[index, 0] = east * 3.0 + 150.0
            positions[index, 1] = north * 3.0 + 150.0
            if kind == "UAV":
                positions[index, 2] = max(18.0, (up - 9.0) * 4.4)
        self.env.agents[:, :3] = positions
        self.env.agents[:, 3] = 0
        target_pose = (
            initial_poses.get("TARGET-001")
            or initial_poses.get("TARGET")
        )
        if target_pose is not None:
            east, north, _ = self.initial_pose_to_local(target_pose)
            target_x = east * 3.0 + 150.0
            target_y = north * 3.0 + 150.0
        else:
            target_x, target_y = 180.0, 150.0
        self.env.targets[0, :5] = np.asarray(
            [target_x, target_y, 0, self.source.TARGET_SPEED, math.pi / 2]
        )

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
        initial_frame = self._initial_frame_pending
        self._initial_frame_pending = False
        initial_snapshot = initial_frame and bool(self.initial_pose_map())
        if not initial_frame:
            with contextlib.redirect_stdout(sys.stderr):
                self.env.step()

        # The protected vessel is inactive in capture mode. Keep it clear of
        # every USV approach corridor so the capture experiment is not bent by
        # an unrelated static hull.
        escort_scene = (45.0, -28.0, 0.0)
        target_scene = self._to_scene(self.env.targets[0, :3], "TARGET")
        if initial_snapshot:
            safe_target = SafePoint(*target_scene, False)
        else:
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
                code = f"UAV-{uav_no:03d}"
            else:
                usv_no += 1
                code = f"USV-{usv_no:03d}"
            proposals[code] = (kind, self._to_scene(raw[:3], kind))
            rows[code] = (index, raw)

        resolved = {} if initial_snapshot else self.safety.resolve_group(
            proposals,
            self.previous_scene,
            {
                "TARGET": ("CAPTURE_TARGET", (safe_target.x, safe_target.y, 0.0)),
                "ESCORT_TARGET": ("ESCORT_TARGET", escort_scene),
            },
        )
        for code, (index, raw) in rows.items():
            kind = proposals[code][0]
            previous_scene = self.previous_scene.get(code)
            if initial_snapshot:
                scene = proposals[code][1]
                adjusted = False
            else:
                safe = resolved[code]
                scene = (safe.x, safe.y, safe.z)
                adjusted = safe.adjusted
            capped = False
            if not initial_snapshot and previous_scene is not None:
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
            if adjusted or capped:
                self.avoidance_count += 1
                self.env.agents[index, :3] = self._to_internal(scene, kind)
            self.previous_scene[code] = scene
            initial_pose = self.initial_pose_map().get(code)
            if initial_snapshot and initial_pose is not None:
                heading = float(initial_pose.get("headingDeg", 0.0)) % 360.0
                self._stable_headings[code] = heading
            else:
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
                TargetFrame(
                    "TARGET",
                    "CAPTURE_TARGET",
                    safe_target.x,
                    safe_target.y,
                    0.0,
                    (
                        float(self.initial_pose_map().get("TARGET-001", {}).get("headingDeg", 0.0)) % 360.0
                        if initial_snapshot
                        else math.degrees(float(self.env.targets[0, 4])) % 360.0
                    ),
                ),
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
