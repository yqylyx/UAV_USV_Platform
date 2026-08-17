import contextlib
import json
import math
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.adapters import CaptureAdapter, EscortAdapter
from app.navigation import TASK_CENTER_SCENE_MAP, SceneSafetyFilter


class AlgorithmRuntimeTests(unittest.TestCase):
    @staticmethod
    def heading_delta(first, second):
        return abs((second - first + 180.0) % 360.0 - 180.0)

    def test_capture_is_exactly_three_plus_three(self):
        frame = CaptureAdapter(1, {"seed": 42, "targetBehavior": "STATIC"}).step()
        self.assertEqual(3, sum(agent.type == "UAV" for agent in frame.agents))
        self.assertEqual(3, sum(agent.type == "USV" for agent in frame.agents))
        self.assertEqual({"CAPTURE_TARGET", "ESCORT_TARGET"}, {target.type for target in frame.targets})
        escort = next(target for target in frame.targets if target.type == "ESCORT_TARGET")
        next_frame = CaptureAdapter(3, {"seed": 42, "targetBehavior": "STATIC"}).step()
        next_escort = next(target for target in next_frame.targets if target.type == "ESCORT_TARGET")
        self.assertEqual((escort.x, escort.y), (next_escort.x, next_escort.y))
        self.assertEqual(6, frame.metrics["requiredCaptureAgents"])

    def test_escort_has_moving_protected_and_threat_targets(self):
        adapter = EscortAdapter(2, {"threatFrame": 2})
        first = adapter.step()
        second = adapter.step()
        third = adapter.step()
        self.assertEqual(6, len(third.agents))
        self.assertNotEqual((first.targets[0].x, first.targets[0].y), (third.targets[0].x, third.targets[0].y))
        self.assertEqual({"ESCORT_TARGET", "THREAT_TARGET"}, {target.type for target in third.targets})
        self.assertIn(third.metrics["threatState"], {"APPROACHING", "DETECTED", "FORMING", "ORBITING"})

    def test_escort_manual_threat_uses_new_727_state_machine(self):
        adapter = EscortAdapter(23, {"seed": 42, "threatFrame": 10000})
        waiting = adapter.step()
        self.assertEqual("ESCORTING", waiting.phase)
        self.assertFalse(waiting.metrics["threatVisible"])
        self.assertEqual({"ESCORT_TARGET"}, {target.type for target in waiting.targets})

        adapter.place_threat(21.0, 8.0)
        response = adapter.step()
        self.assertIn(response.phase, {"FORMING", "ORBITING"})
        self.assertTrue(response.metrics["threatActive"])
        self.assertEqual({"ESCORT_TARGET", "THREAT_TARGET"}, {target.type for target in response.targets})
        self.assertEqual(
            {"UAV-001", "UAV-002", "UAV-003", "USV-001", "USV-002", "USV-003"},
            {agent.code for agent in response.agents},
        )

    def test_usv_never_enters_dock(self):
        safety = SceneSafetyFilter()
        safe = safety.constrain((-19.0, 0.0, 0.0), (-25.0, 0.0, 0.0), "USV")
        self.assertTrue(safe.adjusted)
        self.assertFalse(-35.8 <= safe.x <= -19.2 and -9.3 <= safe.y <= 9.3)

    def test_runner_emits_machine_readable_ndjson(self):
        process = subprocess.Popen(
            [sys.executable, str(ROOT / "runner.py"), "--algorithm", "ESCORT_GUARD", "--run-id", "9", "--autostart", "--fps", "20"],
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONUTF8": "1"},
        )
        try:
            ready = json.loads(process.stdout.readline())
            frame = json.loads(process.stdout.readline())
            self.assertEqual("runtimeReady", ready["event"])
            self.assertEqual("frame", frame["event"])
            self.assertEqual("ESCORT_GUARD", frame["payload"]["algorithmCode"])
        finally:
            process.stdin.write('{"action":"CANCEL"}\n')
            process.stdin.flush()
            process.wait(timeout=5)
            process.stdin.close()
            process.stdout.close()
            process.stderr.close()

    def test_both_scenarios_preserve_visual_footprints(self):
        safety = SceneSafetyFilter(TASK_CENTER_SCENE_MAP)
        for adapter_type in (CaptureAdapter, EscortAdapter):
            with contextlib.redirect_stdout(sys.stderr):
                adapter = adapter_type(12, {"seed": 42})
            for _ in range(300):
                with contextlib.redirect_stdout(sys.stderr):
                    frame = adapter.step()
                self.assertEqual([], frame.obstacles)
                for item in [*frame.agents, *frame.targets]:
                    self.assertTrue(math.isfinite(item.x))
                    self.assertTrue(math.isfinite(item.y))
                    self.assertGreaterEqual(item.x, safety.bounds[0] - 1e-3)
                    self.assertLessEqual(item.x, safety.bounds[1] + 1e-3)
                    self.assertGreaterEqual(item.y, safety.bounds[2] - 1e-3)
                    self.assertLessEqual(item.y, safety.bounds[3] + 1e-3)
                for index, first in enumerate(frame.agents):
                    for second in frame.agents[index + 1:]:
                        required = safety.required_separation(first.type, second.type, first.z, second.z)
                        if required <= 0:
                            continue
                        distance = math.hypot(first.x - second.x, first.y - second.y)
                        self.assertGreaterEqual(distance + 1e-3, required)
                for craft in (item for item in frame.agents if item.type == "USV"):
                    for target in frame.targets:
                        required = safety.required_separation(craft.type, target.type, craft.z, target.z)
                        distance = math.hypot(craft.x - target.x, craft.y - target.y)
                        self.assertGreaterEqual(distance + 1e-3, required)

    def test_capture_completes_after_smooth_long_approach(self):
        with contextlib.redirect_stdout(sys.stderr):
            adapter = CaptureAdapter(21, {"seed": 42, "targetBehavior": "STATIC"})
        frames = []
        for _ in range(520):
            with contextlib.redirect_stdout(sys.stderr):
                frame = adapter.step()
            frames.append(frame)
            if frame.terminalStatus:
                break
        self.assertEqual("COMPLETED", frames[-1].terminalStatus)
        self.assertEqual(6, frames[-1].metrics["captureAgents"])
        self.assertIn("TRANSIT", {item.phase for item in frames})
        travel = {agent.code: 0.0 for agent in frames[0].agents}
        for previous, current in zip(frames, frames[1:]):
            for first in previous.agents:
                second = next(item for item in current.agents if item.code == first.code)
                travel[first.code] += math.hypot(second.x - first.x, second.y - first.y)
                limit = 6.01 if first.type == "UAV" else 3.51
                self.assertLessEqual(self.heading_delta(first.heading, second.heading), limit)
        self.assertGreater(min(travel.values()), 10.0)

    def test_first_frame_preserves_unity_initial_poses(self):
        initial_poses = [
            {
                "deviceCode": "UAV-001",
                "deviceType": "UAV",
                "eastM": -67.0,
                "northM": -303.0,
                "upM": 26.0,
                "headingDeg": 90.0,
                "valid": True,
            },
            {
                "deviceCode": "UAV-002",
                "deviceType": "UAV",
                "eastM": -59.0,
                "northM": -296.0,
                "upM": 27.0,
                "headingDeg": 90.0,
                "valid": True,
            },
            {
                "deviceCode": "USV-001",
                "deviceType": "USV",
                "eastM": -65.0,
                "northM": -318.0,
                "upM": 0.0,
                "headingDeg": 90.0,
                "valid": True,
            },
            {
                "deviceCode": "USV-002",
                "deviceType": "USV",
                "eastM": -55.0,
                "northM": -326.0,
                "upM": 0.0,
                "headingDeg": 90.0,
                "valid": True,
            },
            {
                "deviceCode": "TARGET-001",
                "deviceType": "TARGET",
                "eastM": -75.0,
                "northM": -310.0,
                "upM": 0.0,
                "headingDeg": 0.0,
                "valid": True,
            },
        ]
        config = {
            "uavCount": 3,
            "usvCount": 3,
            "targetCount": 1,
            "initialPoses": initial_poses,
            "initialPosesCoordinateFrame": "GLOBAL_ENU",
            "fleetOrigin": {"eastM": -75.0, "northM": -310.0, "upM": 0.0},
            "seed": 20260814,
        }

        for adapter_type in (CaptureAdapter, EscortAdapter):
            adapter = adapter_type(34, config)
            frame = adapter.step()
            poses = {agent.code: agent for agent in frame.agents}
            self.assertEqual(1, frame.sequence)
            self.assertAlmostEqual(8.0, poses["UAV-001"].x, places=3)
            self.assertAlmostEqual(7.0, poses["UAV-001"].y, places=3)
            self.assertAlmostEqual(16.0, poses["UAV-002"].x, places=3)
            self.assertAlmostEqual(14.0, poses["UAV-002"].y, places=3)

    def test_escort_uses_single_step_long_route_and_stable_heading(self):
        adapter = EscortAdapter(22, {"seed": 42, "threatFrame": 10000, "escortSpeed": "LOW"})
        frames = [adapter.step() for _ in range(240)]
        protected_travel = sum(
            math.hypot(current.targets[0].x - previous.targets[0].x, current.targets[0].y - previous.targets[0].y)
            for previous, current in zip(frames, frames[1:])
        )
        self.assertGreater(protected_travel, 15.0)
        self.assertLess(protected_travel, 24.0)
        for previous, current in zip(frames, frames[1:]):
            for first in previous.agents:
                second = next(item for item in current.agents if item.code == first.code)
                limit = 6.01 if first.type == "UAV" else 3.51
                self.assertLessEqual(self.heading_delta(first.heading, second.heading), limit)

    def test_continuous_paths_respect_rendered_hulls_and_speed_limits(self):
        safety = SceneSafetyFilter(TASK_CENTER_SCENE_MAP)
        scenarios = (
            (CaptureAdapter(31, {"seed": 42, "targetBehavior": "STATIC"}), 260),
            (EscortAdapter(32, {"seed": 42, "threatFrame": 60}), 220),
        )
        for adapter, frame_count in scenarios:
            previous = None
            for _ in range(frame_count):
                with contextlib.redirect_stdout(sys.stderr):
                    current = adapter.step()
                if previous is not None:
                    previous_agents = {item.code: item for item in previous.agents}
                    previous_targets = {item.code: item for item in previous.targets}
                    for item in current.agents:
                        old = previous_agents[item.code]
                        displacement = math.hypot(item.x - old.x, item.y - old.y)
                        speed_limit = 0.351 if item.type == "UAV" else 0.181
                        self.assertLessEqual(
                            displacement,
                            speed_limit,
                            f"{adapter.code} {item.code} exceeded per-frame speed",
                        )
                    for left_index, left in enumerate(current.agents):
                        for right in current.agents[left_index + 1:]:
                            required = safety.required_separation(
                                left.type, right.type, left.z, right.z
                            )
                            if required <= 0:
                                continue
                            swept = safety.swept_distance(
                                (
                                    previous_agents[left.code].x,
                                    previous_agents[left.code].y,
                                ),
                                (left.x, left.y),
                                (
                                    previous_agents[right.code].x,
                                    previous_agents[right.code].y,
                                ),
                                (right.x, right.y),
                            )
                            self.assertGreaterEqual(
                                swept + 1e-3,
                                required,
                                f"{adapter.code} {left.code}/{right.code} crossed between frames",
                            )
                    for craft in (item for item in current.agents if item.type == "USV"):
                        for target in current.targets:
                            if target.code not in previous_targets:
                                continue
                            required = safety.required_separation(
                                craft.type, target.type, craft.z, target.z
                            )
                            swept = safety.swept_distance(
                                (
                                    previous_agents[craft.code].x,
                                    previous_agents[craft.code].y,
                                ),
                                (craft.x, craft.y),
                                (
                                    previous_targets[target.code].x,
                                    previous_targets[target.code].y,
                                ),
                                (target.x, target.y),
                            )
                            self.assertGreaterEqual(
                                swept + 1e-3,
                                required,
                                f"{adapter.code} {craft.code}/{target.code} crossed between frames",
                            )
                previous = current

    def test_capture_holds_large_domain_specific_formation_before_completion(self):
        with contextlib.redirect_stdout(sys.stderr):
            adapter = CaptureAdapter(33, {"seed": 42, "targetBehavior": "STATIC"})
        final = None
        for _ in range(520):
            with contextlib.redirect_stdout(sys.stderr):
                final = adapter.step()
            if final.terminalStatus:
                break
        self.assertIsNotNone(final)
        self.assertEqual("COMPLETED", final.terminalStatus)
        target = next(item for item in final.targets if item.type == "CAPTURE_TARGET")
        usv_radii = [
            math.hypot(item.x - target.x, item.y - target.y)
            for item in final.agents
            if item.type == "USV"
        ]
        uav_radii = [
            math.hypot(item.x - target.x, item.y - target.y)
            for item in final.agents
            if item.type == "UAV"
        ]
        self.assertAlmostEqual(22.0, sum(usv_radii) / len(usv_radii), delta=1.2)
        self.assertAlmostEqual(30.0, sum(uav_radii) / len(uav_radii), delta=1.4)


if __name__ == "__main__":
    unittest.main()
