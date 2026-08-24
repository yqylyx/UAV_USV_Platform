from __future__ import annotations

import math
import time
from typing import Dict, List, Mapping

from app.adapters.base import AlgorithmAdapter
from app.adapters.capture import CaptureAdapter
from app.capture import assess_containment, maximum_capture_gap_deg
from app.navigation import TASK_CENTER_SCENE_MAP, SceneSafetyFilter
from app.scenario import derive_scenario_plan
from app.schemas import AgentFrame, RuntimeFrame, TargetFrame


class AdaptiveCaptureAdapter(AlgorithmAdapter):
    """Coordinate one independent capture solver per hostile target.

    The original vendor solver is single-target.  This coordinator partitions
    both domains into stable teams, keeps each solver's pursuit/ring state
    independent, and merges their frames back to the global device codes used
    by Unity.  Target count follows the same adaptive threat-count contract as
    escort missions instead of being silently forced to one.
    """

    code = "GB_SFLA_CS"
    version = "2.0.0"

    def __init__(self, run_id: int, config: Dict[str, object] | None = None) -> None:
        super().__init__(run_id, config)
        uav_count = max(1, min(128, int(self.config.get("uavCount", 3))))
        usv_count = max(1, min(128, int(self.config.get("usvCount", 3))))
        requested_targets = max(1, int(self.config.get("targetCount", 1)))
        geometric_limit = max(1, (uav_count + usv_count) // 3)
        self.target_count = min(requested_targets, uav_count, usv_count, geometric_limit)
        self.children: List[CaptureAdapter] = []
        self.agent_code_maps: List[Dict[str, str]] = []
        # Child capture solvers operate in the expanded adaptive scenario
        # (roughly 360x280 m for the realtime tiers), not the legacy
        # Task-Center 72x60 m presentation box.  Applying the latter bounds
        # to the merged fleet clamps multi-target agents near the initial
        # staging area, producing the “分组后原地不动” symptom and preventing
        # 9+9 from ever closing its ring.
        plan = derive_scenario_plan(uav_count, usv_count)
        # Keep the complete outer ring inside the coordinator's water area.
        # A fixed +/-190 m vertical bound clipped the north/south slots after
        # a target had completed its visible escape run. Several UAVs were
        # then projected onto the same boundary point, leaving an artificial
        # 90+ degree opening that could never converge.
        half_width = max(320.0, plan.world_width * 0.5 + 120.0)
        half_height = max(260.0, plan.world_height * 0.5 + 120.0)
        self.safety = SceneSafetyFilter({
            "bounds": [-half_width, half_width, -half_height, half_height],
            "obstacles": list(TASK_CENTER_SCENE_MAP.get("obstacles", [])),
        })
        self.previous_scene: Dict[str, tuple[float, float, float]] = {}
        # Hold counters for the collision-safe poses actually emitted to
        # Unity. Child solvers assess before the cross-target safety pass, so
        # their private hold cannot be authoritative for a merged scene.
        self.executed_hold_frames: List[int] = [0 for _ in range(self.target_count)]
        self.executed_post_breakout_stable_frames: List[int] = [0 for _ in range(self.target_count)]
        # Keep the aggregate mission in final verification once any target
        # enters it; staggered target groups must not make the UI oscillate
        # between STABLE_CONTAINMENT and BREAKOUT_TEST.
        self.breakout_test_phase_started = False
        self.display_progress = 0.0
        initial = self.initial_pose_map()

        target_points = [
            initial.get(f"TARGET-{index + 1:03d}")
            for index in range(self.target_count)
        ]
        uav_groups = self._partition_codes(
            "UAV", uav_count, self.target_count, initial, target_points,
        )
        usv_groups = self._partition_codes(
            "USV", usv_count, self.target_count, initial, target_points,
        )
        for target_index in range(self.target_count):
            global_uavs = uav_groups[target_index]
            global_usvs = usv_groups[target_index]
            code_map: Dict[str, str] = {}
            child_poses: List[Dict[str, object]] = []
            for kind, codes in (("UAV", global_uavs), ("USV", global_usvs)):
                for local_index, global_code in enumerate(codes, start=1):
                    local_code = f"{kind}-{local_index:03d}"
                    code_map[local_code] = global_code
                    pose = initial.get(global_code)
                    if pose is not None:
                        copied = dict(pose)
                        copied["deviceCode"] = local_code
                        child_poses.append(copied)
            target_code = f"TARGET-{target_index + 1:03d}"
            target_pose = initial.get(target_code)
            if target_pose is not None:
                copied_target = dict(target_pose)
                copied_target["deviceCode"] = "TARGET-001"
                child_poses.append(copied_target)

            child_config = dict(self.config)
            child_config.update({
                "uavCount": len(global_uavs),
                "usvCount": len(global_usvs),
                "targetCount": 1,
                "seed": int(self.config.get("seed", 42)) + target_index * 997,
                "initialPoses": child_poses,
            })
            child = CaptureAdapter(run_id * 100 + target_index + 1, child_config)
            self.children.append(child)
            self.agent_code_maps.append(code_map)

    @staticmethod
    def _partition_codes(
        kind: str,
        count: int,
        groups: int,
        initial: Mapping[str, Mapping[str, object]],
        target_points: List[Mapping[str, object] | None],
    ) -> List[List[str]]:
        """Build balanced, distance-aware teams instead of round-robin lists.

        The first pass guarantees one member per target where possible.  The
        remaining devices are assigned by distance plus a load penalty so the
        result remains balanced without sending a nearby craft across another
        group's pursuit corridor.
        """
        result: List[List[str]] = [[] for _ in range(groups)]
        codes = [f"{kind}-{index + 1:03d}" for index in range(count)]

        def distance(code: str, group_index: int) -> float:
            pose = initial.get(code)
            target = target_points[group_index]
            if pose is None or target is None:
                return 0.0
            dx = float(pose.get("eastM", 0.0)) - float(target.get("eastM", 0.0))
            dy = float(pose.get("northM", 0.0)) - float(target.get("northM", 0.0))
            return math.hypot(dx, dy)

        unassigned = set(codes)
        for group_index in range(groups):
            if not unassigned:
                break
            chosen = min(unassigned, key=lambda code: (distance(code, group_index), code))
            result[group_index].append(chosen)
            unassigned.remove(chosen)
        while unassigned:
            code = min(unassigned)
            group_index = min(
                range(groups),
                key=lambda index: (
                    len(result[index]),
                    distance(code, index),
                    index,
                ),
            )
            result[group_index].append(code)
            unassigned.remove(code)
        return result

    def set_mission_active(self, active: bool) -> None:
        super().set_mission_active(active)
        for child in self.children:
            child.set_mission_active(active)

    @staticmethod
    def _executed_containment(
        child: CaptureAdapter,
        agents: List[AgentFrame],
        target: TargetFrame,
    ) -> Dict[str, object]:
        """Assess the poses that Unity actually receives after global safety."""
        if len(agents) < 3:
            return {
                "ready": False,
                "targetInside": False,
                "maxGapDeg": 360.0,
                "maxAllowedGapDeg": 0.0,
                "minimumRadiusM": 0.0,
                "maximumRadiusM": 0.0,
                "blocker": "POST_GLOBAL_INSUFFICIENT_AGENTS",
            }
        angles = sorted(
            math.atan2(agent.y - target.y, agent.x - target.x) % (2.0 * math.pi)
            for agent in agents
        )
        max_gap_deg = math.degrees(max(
            (angles[(index + 1) % len(angles)] - angles[index]) % (2.0 * math.pi)
            for index in range(len(angles))
        ))
        radii = [math.hypot(agent.x - target.x, agent.y - target.y) for agent in agents]
        lower_radius = 13.5
        upper_radius = child.outer_formation_radius + 15.0
        max_gap_limit_deg = maximum_capture_gap_deg(len(agents))
        target_inside = max_gap_deg < 180.0 - 1e-6
        visible_chase_complete = (
            child.target_travelled_distance
            >= child.required_pursuit_distance + 20.0
        )
        contract = assess_containment(
            [(agent.x, agent.y, agent.z) for agent in agents],
            (target.x, target.y, target.z),
            required_count=len(agents),
            device_types=[agent.type for agent in agents],
            minimum_type_counts={"UAV": 1, "USV": 1},
            minimum_radius_m=lower_radius,
            maximum_radius_m=upper_radius,
            # Multi-target teams intentionally use concentric UAV/USV layers.
            # Permit that designed layer offset while still bounding detached
            # staging craft and pathological radial outliers.
            maximum_radial_spread_m=max(48.0, upper_radius * 0.40),
            minimum_pairwise_separation_m=7.1,
            tolerance_deg=0.0,
        )
        if not visible_chase_complete:
            blocker = "PURSUIT_DISTANCE"
        elif not contract.ready:
            blocker = f"POST_GLOBAL_{contract.blocker}"
        else:
            blocker = "NONE"
        return {
            "ready": blocker == "NONE",
            "targetInside": contract.target_inside,
            "maxGapDeg": contract.max_gap_deg,
            "maxAllowedGapDeg": contract.allowed_gap_deg,
            "minimumRadiusM": contract.minimum_radius_m,
            "maximumRadiusM": contract.maximum_radius_m,
            "radialSpreadM": contract.radial_spread_m,
            "sectorCount": contract.sector_count,
            "coveredSectors": contract.covered_sectors,
            "minimumSeparationM": contract.minimum_separation_m,
            "requiredSeparationM": contract.required_separation_m,
            "uavCount": contract.uav_count,
            "usvCount": contract.usv_count,
            "invalidParticipants": contract.invalid,
            "stationaryParticipants": contract.stationary,
            "detachedParticipants": contract.detached,
            "participating": contract.participating,
            "required": contract.required,
            "blocker": blocker,
        }

    @staticmethod
    def _gap_repair_proposal(
        child: CaptureAdapter,
        agents: List[AgentFrame],
        target: TargetFrame,
    ) -> tuple[str, tuple[float, float, float], Dict[str, object]] | None:
        """Select one physical craft to close the executed ring's worst gap.

        Child solvers target ideal slots before the coordinator performs
        cross-target collision resolution.  When that final safety pass moves
        one craft, every child continuing at the same speed can preserve the
        new gap forever.  Repair the *executed* geometry with one ETA-selected
        blocker while its neighbours hold their sectors.
        """
        if len(agents) < 3:
            return None
        radii = {
            item.code: math.hypot(item.x - target.x, item.y - target.y)
            for item in agents
        }
        upper_radius = child.outer_formation_radius + 15.0
        farthest = max(agents, key=lambda item: radii[item.code])
        if radii[farthest.code] > upper_radius:
            angle = math.atan2(farthest.y - target.y, farthest.x - target.x)
            speed = 4.0 if farthest.type == "USV" else min(
                15.0, max(5.0, float(child.config.get("uavSpeedMps", 5.0))),
            )
            step = speed * 0.1
            desired_radius = max(13.5, radii[farthest.code] - step)
            return farthest.code, (
                target.x + math.cos(angle) * desired_radius,
                target.y + math.sin(angle) * desired_radius,
                farthest.z,
            ), {
                "gapFillerCode": farthest.code,
                "gapFillerSpeedMps": round(speed, 2),
                "gapRepairMode": "RADIAL_RECOVERY",
            }

        ordered = sorted(
            agents,
            key=lambda item: math.atan2(item.y - target.y, item.x - target.x) % (2.0 * math.pi),
        )
        angles = [
            math.atan2(item.y - target.y, item.x - target.x) % (2.0 * math.pi)
            for item in ordered
        ]
        gaps = [
            (angles[(index + 1) % len(angles)] - angles[index]) % (2.0 * math.pi)
            for index in range(len(angles))
        ]
        gap_index = max(range(len(gaps)), key=gaps.__getitem__)
        allowed = math.radians(maximum_capture_gap_deg(len(agents)))
        # Keep repairing to the geometric limit, even though the final latch
        # allows half a degree of integration noise.  This produces a visibly
        # closed executed ring (important for asymmetric 6+8) instead of
        # accepting the edge of the tolerance band as the resting shape.
        if gaps[gap_index] <= allowed + math.radians(0.02):
            return None

        left_index = gap_index
        right_index = (gap_index + 1) % len(ordered)
        left_other_gap = gaps[(left_index - 1) % len(gaps)]
        right_other_gap = gaps[right_index]
        # Moving the endpoint with the smaller opposite gap increases the
        # better-covered sector and therefore reduces the global maximum.
        use_left = left_other_gap <= right_other_gap
        filler = ordered[left_index if use_left else right_index]
        radius = max(13.5, min(child.outer_formation_radius + 8.0, radii[filler.code]))
        configured = float(child.config.get(
            "usvSpeedMps" if filler.type == "USV" else "uavSpeedMps",
            3.0 if filler.type == "USV" else 5.0,
        ))
        speed = min(4.0, max(configured, 3.6)) if filler.type == "USV" else min(
            15.0, max(configured, 6.5),
        )
        max_arc_step = speed * 0.1 / max(8.0, radius)
        required = min(gaps[gap_index] * 0.48, gaps[gap_index] - allowed + math.radians(2.0))
        angle_step = min(required, max_arc_step)
        desired_angle = angles[left_index] + angle_step if use_left else angles[right_index] - angle_step
        return filler.code, (
            target.x + math.cos(desired_angle) * radius,
            target.y + math.sin(desired_angle) * radius,
            filler.z,
        ), {
            "gapFillerCode": filler.code,
            "gapFillerSpeedMps": round(speed, 2),
            "gapRepairMode": "ANGULAR_INTERCEPT",
            "gapCenterDeg": round(math.degrees(
                (angles[left_index] + gaps[gap_index] * 0.5) % (2.0 * math.pi)
            ), 2),
        }

    def step(self) -> RuntimeFrame:
        self.sequence += 1
        target_centers = [
            child.previous_scene.get("TARGET")
            for child in self.children
        ]
        for index, child in enumerate(self.children):
            child.peer_target_positions = [
                point for other_index, point in enumerate(target_centers)
                if other_index != index and point is not None
            ]
        child_frames = [child.step() for child in self.children]
        agents: List[AgentFrame] = []
        targets: List[TargetFrame] = []
        groups: List[Dict[str, object]] = []
        metrics_list = [frame.metrics for frame in child_frames]

        for index, frame in enumerate(child_frames):
            target_code = f"TARGET-{index + 1:03d}"
            group_id = f"CAPTURE-{index + 1:03d}"
            code_map = self.agent_code_maps[index]
            # A child latches `metrics.captured` at the exact frame where the
            # ring is confirmed; its presentation terminal flag can arrive
            # one polling frame later.  Use the latched signal consistently
            # for group state, progress and aggregate completion so the UI
            # cannot show "stage 3 / hold 0 / ENCIRCLEMENT" for one target.
            child_captured = (
                frame.terminalStatus == "COMPLETED"
                or bool(frame.metrics.get("captured", False))
            )
            for agent in frame.agents:
                agents.append(AgentFrame(
                    code_map.get(agent.code, agent.code), agent.type,
                    agent.x, agent.y, agent.z, agent.heading, agent.role,
                    agent.status, group_id, target_code,
                ))
            target = frame.targets[0]
            raw_stage = int(frame.metrics.get("captureStage", 1) or 1)
            # Stage 3 is reserved for a latched capture.  Older child
            # frames can carry a stale stage value for one poll after a
            # geometry replan; clamp that value so the UI never presents
            # "ENCIRCLEMENT · stage 3/3".
            group_stage = 3 if child_captured else min(2, max(1, raw_stage))
            targets.append(TargetFrame(
                target_code, "CAPTURE_TARGET", target.x, target.y, target.z,
                target.heading, target.visible, group_id,
                "CAPTURED" if child_captured else str(frame.metrics.get("targetBehavior", frame.phase)),
                3,
            ))
            child_stage = str(frame.metrics.get("missionStage", frame.phase))
            groups.append({
                "threatCode": target_code,
                "state": "CAPTURED" if child_captured else child_stage,
                "missionStage": "COMPLETED" if child_captured else child_stage,
                "memberCount": len(frame.agents),
                "uavCount": sum(item.type == "UAV" for item in frame.agents),
                "usvCount": sum(item.type == "USV" for item in frame.agents),
                "progress": 1.0 if child_captured else frame.metrics.get("progress", 0.0),
                # Preserve the child solver's real closure diagnostics.  The
                # previous coordinator only copied progress and blocker, so
                # the UI rendered every multi-target group as stage 1/3,
                # arrival 0% and hold 0/0 even after the ring was complete.
                "stage": group_stage,
                "arrivalRatio": 1.0 if child_captured else frame.metrics.get("arrivalRatio", 0.0),
                "holdFrames": (
                    max(
                        int(frame.metrics.get("captureHoldFrames", 0)),
                        int(frame.metrics.get("requiredCaptureHoldFrames", 0)),
                    )
                    if child_captured
                    else int(frame.metrics.get("captureHoldFrames", 0))
                ),
                "holdRequiredFrames": frame.metrics.get("requiredCaptureHoldFrames", 0),
                "pursuitDistanceM": frame.metrics.get("targetTravelDistanceM", 0.0),
                "requiredPursuitDistanceM": frame.metrics.get("requiredPursuitDistanceM", 0.0),
                "targetSpeedMps": frame.metrics.get("targetSpeedMps", 0.0),
                "targetBehavior": frame.metrics.get("targetBehavior", ""),
                "ringGeometryReady": frame.metrics.get("ringGeometryReady", False),
                "captureBlocker": "NONE" if child_captured else frame.metrics.get("captureBlocker", ""),
                "containmentConfidence": frame.metrics.get("containmentConfidence", 0.0),
                "stableContainmentFrames": frame.metrics.get("stableContainmentFrames", 0),
                "stableContainmentRequiredFrames": frame.metrics.get("requiredStableContainmentFrames", frame.metrics.get("requiredCaptureHoldFrames", 0)),
                "gapRepairRequired": frame.metrics.get("gapRepairRequired", False),
            })

        # Child solvers are intentionally independent per target, but their
        # output shares one Unity ocean.  Enforce a final whole-fleet safety
        # pass so craft assigned to different targets cannot intersect while
        # their pursuit corridors cross.
        proposals = {
            agent.code: (agent.type, (agent.x, agent.y, agent.z))
            for agent in agents
        }
        fixed_targets = {
            target.code: (target.type, (target.x, target.y, target.z))
            for target in targets
        }
        globally_resolved = self.safety.resolve_group(
            proposals,
            self.previous_scene,
            fixed_targets,
        )
        global_adjustments = 0
        global_adjustments_by_target = {
            f"TARGET-{index + 1:03d}": 0
            for index in range(self.target_count)
        }
        agents_by_code = {agent.code: agent for agent in agents}
        for agent in agents:
            safe = globally_resolved[agent.code]
            if safe.adjusted:
                global_adjustments += 1
                global_adjustments_by_target[agent.assignedTargetCode] = (
                    global_adjustments_by_target.get(agent.assignedTargetCode, 0) + 1
                )
            agent.x, agent.y, agent.z = safe.x, safe.y, safe.z
            self.previous_scene[agent.code] = (safe.x, safe.y, safe.z)

        # A second, role-aware pass repairs gaps created by the first global
        # collision pass. Only the selected GAP_BLOCKER receives an accelerated
        # proposal; every other member holds position, so closure does not
        # turn into another whole-ring chase.
        repair_metrics: Dict[str, Dict[str, object]] = {}
        repairs = 0
        # One 0.1 s correction is cancelled by the child solver's return to
        # its ideal slot on the next frame.  Iterate the executed geometry in
        # this same frame until the opening is actually below the contract (or
        # a small bounded budget is exhausted).  This is still one physical
        # GAP_BLOCKER per target; it simply receives enough arc travel to beat
        # the global collision displacement instead of oscillating forever.
        for _repair_round in range(12):
            repair_proposals = {
                agent.code: (agent.type, (agent.x, agent.y, agent.z))
                for agent in agents
            }
            round_repairs = 0
            for index, (child, target) in enumerate(zip(self.children, targets)):
                target_code = f"TARGET-{index + 1:03d}"
                group_agents = [
                    item for item in agents if item.assignedTargetCode == target_code
                ]
                executed = self._executed_containment(child, group_agents, target)
                within_exact_gap = (
                    float(executed.get("maxGapDeg", 360.0))
                    <= float(executed.get("maxAllowedGapDeg", 0.0)) + 0.02
                )
                if (
                    (bool(executed["ready"]) and within_exact_gap)
                    or executed["blocker"] == "PURSUIT_DISTANCE"
                ):
                    continue
                repair = self._gap_repair_proposal(child, group_agents, target)
                if repair is None:
                    continue
                code, proposal, diagnostics = repair
                filler = agents_by_code.get(code)
                if filler is None:
                    continue
                repair_proposals[code] = (filler.type, proposal)
                filler.role = "GAP_BLOCKER"
                repair_metrics[target_code] = diagnostics
                round_repairs += 1
                repairs += 1
            if not round_repairs:
                break
            repair_previous = {
                agent.code: (agent.x, agent.y, agent.z) for agent in agents
            }
            repaired = self.safety.resolve_group(
                repair_proposals,
                repair_previous,
                fixed_targets,
                iterations=64,
                max_steps={"UAV": 1.5, "USV": 0.4},
            )
            for agent in agents:
                safe = repaired[agent.code]
                if safe.adjusted:
                    global_adjustments += 1
                    global_adjustments_by_target[agent.assignedTargetCode] = (
                        global_adjustments_by_target.get(agent.assignedTargetCode, 0) + 1
                    )
                agent.x, agent.y, agent.z = safe.x, safe.y, safe.z
                self.previous_scene[agent.code] = (safe.x, safe.y, safe.z)
        for target in targets:
            self.previous_scene[target.code] = (target.x, target.y, target.z)

        # Feed the executed global poses back into each child. Without this,
        # a child would plan the next frame from its pre-avoidance position and
        # repeatedly drive the renderer back into the same conflict.
        for child, code_map in zip(self.children, self.agent_code_maps):
            for local_code, global_code in code_map.items():
                executed = agents_by_code.get(global_code)
                if executed is None:
                    continue
                child.previous_scene[local_code] = (
                    executed.x,
                    executed.y,
                    executed.z,
                )
                agent_type = 0 if local_code.startswith("UAV-") else 1
                ordinal = int(local_code.rsplit("-", 1)[1])
                agent_id = (1000 if agent_type == 0 else 2000) + ordinal - 1
                for raw in child.env.agents:
                    if int(raw[6]) == agent_type and int(raw[7]) == agent_id:
                        raw[:3] = child._to_internal(
                            (executed.x, executed.y, executed.z),
                            executed.type,
                        )
                        break

        # Child metrics are computed before this coordinator resolves
        # cross-target collisions. Recheck each ring from the executed global
        # poses and invalidate a candidate/hold if global safety opened it.
        # This keeps the UI, the child state machine and Unity on one geometry.
        for index, (child, frame, target, group) in enumerate(zip(
            self.children, child_frames, targets, groups
        )):
            target_code = f"TARGET-{index + 1:03d}"
            executed_agents = [
                agent for agent in agents
                if agent.assignedTargetCode == target_code
            ]
            executed = self._executed_containment(child, executed_agents, target)
            frame.metrics["postGlobalContainmentReady"] = executed["ready"]
            frame.metrics["postGlobalTargetInsideFormation"] = executed["targetInside"]
            frame.metrics["postGlobalCombinedMaxGapDeg"] = executed["maxGapDeg"]
            frame.metrics["postGlobalMaxAllowedGapDeg"] = executed["maxAllowedGapDeg"]
            frame.metrics["postGlobalMinimumRadiusM"] = executed["minimumRadiusM"]
            frame.metrics["postGlobalMaximumRadiusM"] = executed["maximumRadiusM"]
            frame.metrics["globalAvoidanceCount"] = global_adjustments_by_target.get(target_code, 0)
            group["postGlobalContainmentReady"] = executed["ready"]
            group["postGlobalMaxGapDeg"] = executed["maxGapDeg"]
            group["postGlobalMaxAllowedGapDeg"] = executed["maxAllowedGapDeg"]
            group["globalAvoidanceCount"] = global_adjustments_by_target.get(target_code, 0)
            group.update(repair_metrics.get(target_code, {}))
            breakout_active = bool(getattr(child, "breakout_test_active", False))
            breakout_passed = bool(getattr(child, "breakout_test_passed", False))
            if breakout_active:
                self.breakout_test_phase_started = True
            group["breakoutTestState"] = (
                "ACTIVE" if breakout_active
                else "PASSED" if breakout_passed
                else "PENDING"
            )
            group["breakoutTestFrames"] = int(getattr(child, "breakout_test_frames", 0))
            group["breakoutTestRequiredFrames"] = int(
                getattr(child, "breakout_test_required_frames", 0)
            )
            group["breakoutTestDistanceM"] = round(
                float(getattr(child, "breakout_test_distance_m", 0.0)), 3
            )
            group["breakoutTestRequiredDistanceM"] = float(
                getattr(child, "breakout_test_required_distance_m", 0.0)
            )
            group["postBreakoutStableFrames"] = int(
                getattr(child, "post_breakout_stable_frames", 0)
            )
            group["requiredPostBreakoutStableFrames"] = int(
                getattr(child, "required_post_breakout_stable_frames", 25)
            )
            if bool(executed["ready"]) and not breakout_active and not breakout_passed:
                self.executed_hold_frames[index] = min(
                    child.capture_hold_frames,
                    self.executed_hold_frames[index] + 1,
                )
                group["postGlobalHoldFrames"] = self.executed_hold_frames[index]
                group["postGlobalHoldRequiredFrames"] = child.capture_hold_frames
                if self.executed_hold_frames[index] >= child.capture_hold_frames:
                    gap_direction = child._largest_gap_direction(
                        (target.x, target.y, target.z),
                        [(agent.x, agent.y, agent.z) for agent in executed_agents],
                    )
                    child.breakout_test_active = True
                    child.breakout_test_started_sequence = child.sequence
                    child.breakout_test_origin = (target.x, target.y)
                    child.breakout_test_direction = gap_direction or child.target_escape_direction
                    child.breakout_test_frames = 0
                    child.breakout_test_distance_m = 0.0
                    child.target_behavior_state = "BREAKOUT_TEST"
                    self.breakout_test_phase_started = True
                    breakout_active = True
                    group["breakoutTestState"] = "ACTIVE"
                    group["state"] = "BREAKOUT_TEST"
                    frame.phase = "BREAKOUT_TEST"
            if (
                bool(executed["ready"])
                and breakout_active
                and child.breakout_test_frames >= child.breakout_test_required_frames
                and child.breakout_test_distance_m >= child.breakout_test_required_distance_m
            ):
                child.breakout_test_active = False
                child.breakout_test_passed = True
                child.target_behavior_state = "CONTAINED"
                breakout_active = False
                breakout_passed = True
                group["breakoutTestState"] = "PASSED"
            if bool(executed["ready"]) and not breakout_active and not breakout_passed:
                group["captureBlocker"] = "HOLD_CONFIRMATION"
                group["missionStage"] = "STABLE_CONTAINMENT"
                group["state"] = "STABLE_CONTAINMENT"
                continue
            if bool(executed["ready"]) and not breakout_active and breakout_passed:
                required_final_hold = int(getattr(
                    child, "required_post_breakout_stable_frames", 25
                ))
                self.executed_post_breakout_stable_frames[index] = min(
                    required_final_hold,
                    self.executed_post_breakout_stable_frames[index] + 1,
                )
                group["postBreakoutStableFrames"] = self.executed_post_breakout_stable_frames[index]
                group["requiredPostBreakoutStableFrames"] = required_final_hold
                group["missionStage"] = "STABLE_CONTAINMENT"
                group["state"] = "STABLE_CONTAINMENT"
                if (
                    self.mission_active
                    and self.executed_post_breakout_stable_frames[index] >= required_final_hold
                ):
                    child.confirm_executed_containment()
                    frame.terminalStatus = "COMPLETED"
                    frame.phase = "CAPTURED"
                    frame.metrics["captured"] = True
                    frame.metrics["formationReady"] = True
                    frame.metrics["captureHoldFrames"] = child.capture_hold_frames
                    frame.metrics["captureStage"] = 3
                    frame.metrics["captureBlocker"] = "NONE"
                    group["state"] = "CAPTURED"
                    group["stage"] = 3
                    group["progress"] = 1.0
                    group["holdFrames"] = child.capture_hold_frames
                    group["captureBlocker"] = "NONE"
                    target.state = "CAPTURED"
                continue
            if bool(executed["ready"]) and breakout_active:
                group["state"] = "BREAKOUT_TEST"
                group["captureBlocker"] = "BREAKOUT_TEST"
                group["missionStage"] = "BREAKOUT_TEST"
                frame.terminalStatus = None
                frame.metrics["captured"] = False
                frame.metrics["formationReady"] = True
                frame.metrics["captureBlocker"] = "BREAKOUT_TEST"
                target.state = "BREAKOUT_TEST"
                continue
            self.executed_hold_frames[index] = 0
            self.executed_post_breakout_stable_frames[index] = 0
            child.containment_candidate_at_sequence = None
            child.formation_ready_at_sequence = None
            if child.captured_at_sequence is not None:
                # A child freezes its target when it first latches capture.
                # If global collision resolution later opens that ring, revoke
                # through the child state machine so the target resumes its
                # seeded breakout speed and the coordinator cannot own state.
                child.revoke_executed_containment()
            frame.terminalStatus = None
            if frame.phase == "CAPTURED":
                frame.phase = "ENCIRCLEMENT"
            frame.metrics["captured"] = False
            frame.metrics["formationReady"] = False
            frame.metrics["captureHoldFrames"] = 0
            frame.metrics["captureStage"] = 1
            frame.metrics["captureBlocker"] = executed["blocker"]
            group["state"] = frame.phase
            group["stage"] = 1
            group["holdFrames"] = 0
            group["captureBlocker"] = executed["blocker"]
            group["missionStage"] = (
                "GAP_REPAIR"
                if str(frame.metrics.get("missionStage", frame.phase)) in {
                    "ENCIRCLEMENT", "GAP_REPAIR", "STABLE_CONTAINMENT"
                } and (
                    repair_metrics.get(target_code)
                or executed["blocker"] in {"ANGULAR_GAP", "SECTOR_COVERAGE", "RADIAL_SPREAD"}
                )
                else str(frame.metrics.get("missionStage", frame.phase))
            )
            target.state = child.target_behavior_state

        # A child may have already latched its capture state in the vendor
        # environment while the adapter terminal flag is delayed by one
        # presentation frame.  Use both signals so the aggregate progress
        # cannot remain below 100% after every target has actually closed.
        completed = [
            frame.terminalStatus == "COMPLETED"
            or bool(frame.metrics.get("captured", False))
            for frame in child_frames
        ]
        all_completed = all(completed)
        breakout_active_count = sum(
            str(group.get("breakoutTestState", "")) == "ACTIVE"
            for group in groups
        )
        breakout_passed_count = sum(
            str(group.get("breakoutTestState", "")) == "PASSED"
            for group in groups
        )
        # The coordinator can promote a child into BREAKOUT_TEST after the
        # child frame has been produced, once the executed global poses pass
        # the final containment check. Rebuild the aggregate phase from the
        # post-coordination group states so that state is visible to Unity for
        # at least the frame in which it was entered.
        post_states = [str(group.get("state", "")) for group in groups]
        phases = [frame.phase for frame in child_frames]
        if all(phase == "PREVIEW" for phase in phases):
            phase = "PREVIEW"
        elif all_completed:
            phase = "CAPTURED"
        elif self.breakout_test_phase_started and breakout_passed_count < len(groups):
            phase = "BREAKOUT_TEST"
        elif "ESCAPE_PURSUIT" in phases:
            phase = "ESCAPE_PURSUIT"
        elif "INTERCEPTING" in phases:
            phase = "INTERCEPTING"
        else:
            phase = "ENCIRCLEMENT"

        group_stages = [str(group.get("missionStage", group.get("state", ""))) for group in groups]
        if all_completed:
            mission_stage = "COMPLETED"
        elif self.breakout_test_phase_started and breakout_passed_count < len(groups):
            mission_stage = "BREAKOUT_TEST"
        elif "INTERCEPT" in group_stages:
            # Preserve the tactical hand-off for at least one aggregate frame
            # when another target is already asking for gap repair.
            mission_stage = "INTERCEPT"
        elif "GAP_REPAIR" in group_stages:
            mission_stage = "GAP_REPAIR"
        elif "STABLE_CONTAINMENT" in group_stages:
            mission_stage = "STABLE_CONTAINMENT"
        elif "PURSUIT" in group_stages:
            mission_stage = "PURSUIT"
        elif "ESCAPE" in group_stages:
            mission_stage = "ESCAPE"
        else:
            mission_stage = "ENCIRCLEMENT"

        def mean_metric(name: str) -> float:
            return sum(float(item.get(name, 0.0)) for item in metrics_list) / max(1, len(metrics_list))

        blockers = [
            f"TARGET-{index + 1:03d}:{item.get('captureBlocker')}"
            for index, item in enumerate(metrics_list)
            if not completed[index]
            and item.get("captureBlocker") not in {None, "", "NONE"}
        ]
        ring_diagnostics: Dict[str, object] = {}
        for index, item in enumerate(metrics_list):
            raw = item.get("ringDiagnostics", {})
            if isinstance(raw, Mapping):
                for name, diagnostic in raw.items():
                    ring_diagnostics[f"TARGET-{index + 1:03d}/{name}"] = diagnostic

        raw_progress = 1.0 if all_completed else min(
            0.999,
            sum(
                1.0 if done else float(metrics_list[index].get("progress", 0.0))
                for index, done in enumerate(completed)
            ) / max(1, len(completed)),
        )
        # Mission progress is a user-facing completion indicator. It must be
        # monotonic; changing containment quality is reported separately by
        # missionStage, captureBlocker and ring diagnostics.
        self.display_progress = max(self.display_progress, raw_progress)
        metrics: Dict[str, object] = {
            "targetCount": self.target_count,
            "visibleTargetCount": len(targets),
            "capturedTargetCount": sum(completed),
            "capturedThreatCount": sum(completed),
            "progress": round(self.display_progress, 3),
            "captured": all_completed,
            "formationReady": all(
                completed[index] or bool(item.get("formationReady", False))
                for index, item in enumerate(metrics_list)
            ),
            "ringGeometryReady": all(
                completed[index] or bool(item.get("ringGeometryReady", False))
                for index, item in enumerate(metrics_list)
            ),
            "captureAgents": sum(int(item.get("captureAgents", 0)) for item in metrics_list),
            "requiredCaptureAgents": sum(int(item.get("requiredCaptureAgents", 0)) for item in metrics_list),
            "targetTravelDistanceM": min(float(item.get("targetTravelDistanceM", 0.0)) for item in metrics_list),
            "requiredPursuitDistanceM": max(float(item.get("requiredPursuitDistanceM", 0.0)) for item in metrics_list),
            "targetSpeedMps": mean_metric("targetSpeedMps"),
            "targetBehavior": "MULTI_CAPTURE" if len(set(str(item.get("targetBehavior", "")) for item in metrics_list)) > 1 else str(metrics_list[0].get("targetBehavior", "")),
            "containmentConfidence": mean_metric("containmentConfidence"),
            "captureBlocker": " | ".join(blockers) if blockers else "NONE",
            "replanCount": sum(int(item.get("replanCount", 0)) for item in metrics_list),
            "avoidanceCount": sum(int(item.get("avoidanceCount", 0)) for item in metrics_list) + global_adjustments,
            "globalAvoidanceCount": global_adjustments,
            "captureHoldFrames": min(
                (
                    max(
                        int(item.get("captureHoldFrames", 0)),
                        int(item.get("requiredCaptureHoldFrames", 0)),
                    )
                    if completed[index]
                    else int(item.get("captureHoldFrames", 0))
                )
                for index, item in enumerate(metrics_list)
            ),
            "requiredCaptureHoldFrames": max(int(item.get("requiredCaptureHoldFrames", 0)) for item in metrics_list),
            "captureGroups": groups,
            "breakoutTestActiveCount": breakout_active_count,
            "breakoutTestPassedCount": breakout_passed_count,
            "breakoutTestRequiredTargetCount": len(groups),
            "breakoutTestCompleted": breakout_passed_count == len(groups),
            "missionStage": mission_stage,
            "stageSequence": ["ESCAPE", "PURSUIT", "INTERCEPT", "ENCIRCLEMENT", "GAP_REPAIR", "STABLE_CONTAINMENT", "BREAKOUT_TEST", "COMPLETED"],
            "ringDiagnostics": ring_diagnostics,
        }
        return RuntimeFrame(
            self.run_id, self.code, self.sequence, int(time.time() * 1000), phase,
            agents, targets, metrics, route=[], obstacles=[],
            terminalStatus="COMPLETED" if all_completed else None,
        )
