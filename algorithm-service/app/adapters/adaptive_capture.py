from __future__ import annotations

import time
from typing import Dict, List, Mapping

from app.adapters.base import AlgorithmAdapter
from app.adapters.capture import CaptureAdapter
from app.navigation import TASK_CENTER_SCENE_MAP, SceneSafetyFilter
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
        uav_count = max(1, min(15, int(self.config.get("uavCount", 3))))
        usv_count = max(1, min(15, int(self.config.get("usvCount", 3))))
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
        self.safety = SceneSafetyFilter({
            "bounds": [-260.0, 260.0, -190.0, 190.0],
            "obstacles": list(TASK_CENTER_SCENE_MAP.get("obstacles", [])),
        })
        self.previous_scene: Dict[str, tuple[float, float, float]] = {}
        initial = self.initial_pose_map()

        uav_groups = self._partition_codes("UAV", uav_count, self.target_count)
        usv_groups = self._partition_codes("USV", usv_count, self.target_count)
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
    def _partition_codes(kind: str, count: int, groups: int) -> List[List[str]]:
        result: List[List[str]] = [[] for _ in range(groups)]
        for index in range(count):
            result[index % groups].append(f"{kind}-{index + 1:03d}")
        return result

    def set_mission_active(self, active: bool) -> None:
        super().set_mission_active(active)
        for child in self.children:
            child.set_mission_active(active)

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
            groups.append({
                "threatCode": target_code,
                "state": "CAPTURED" if child_captured else frame.phase,
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
        agents_by_code = {agent.code: agent for agent in agents}
        for agent in agents:
            safe = globally_resolved[agent.code]
            if safe.adjusted:
                global_adjustments += 1
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
        phases = [frame.phase for frame in child_frames]
        if all(phase == "PREVIEW" for phase in phases):
            phase = "PREVIEW"
        elif all_completed:
            phase = "CAPTURED"
        elif "ESCAPE_PURSUIT" in phases:
            phase = "ESCAPE_PURSUIT"
        elif "INTERCEPTING" in phases:
            phase = "INTERCEPTING"
        else:
            phase = "ENCIRCLEMENT"

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

        metrics: Dict[str, object] = {
            "targetCount": self.target_count,
            "visibleTargetCount": len(targets),
            "capturedTargetCount": sum(completed),
            "capturedThreatCount": sum(completed),
            "progress": 1.0 if all_completed else min(
                0.999,
                sum(
                    1.0 if done else float(metrics_list[index].get("progress", 0.0))
                    for index, done in enumerate(completed)
                ) / max(1, len(completed)),
            ),
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
            "ringDiagnostics": ring_diagnostics,
        }
        return RuntimeFrame(
            self.run_id, self.code, self.sequence, int(time.time() * 1000), phase,
            agents, targets, metrics, route=[], obstacles=[],
            terminalStatus="COMPLETED" if all_completed else None,
        )
