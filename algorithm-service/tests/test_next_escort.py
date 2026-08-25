import math
import unittest

from app.adapters.adaptive_escort import (
    AdaptiveEscortAdapter,
    BREACH_DISTANCE_M,
    CONTAINMENT_STANDOFF_M,
    TARGET_SEPARATION_M,
)


class NextEscortAcceptanceTests(unittest.TestCase):
    def run_frames(self, adapter, count):
        frame = None
        for _ in range(count):
            frame = adapter.step()
        return frame

    def test_detection_automatically_starts_capture(self):
        adapter = AdaptiveEscortAdapter(9001, {"uavCount": 3, "usvCount": 3, "seed": 8})
        frame = self.run_frames(adapter, 650)
        self.assertTrue(any(threat.forced for threat in adapter.threats))
        self.assertTrue(any(agent.role in {"CAPTURE", "INTERCEPTOR", "CONTAINMENT"} for agent in frame.agents))
        self.assertTrue(any(target.state not in {"APPROACHING", "WAITING"} for target in frame.targets if target.type == "THREAT_TARGET"))

    def test_generated_threats_start_outside_guard_area(self):
        for count in (3, 5, 10, 20, 30):
            with self.subTest(count=count):
                adapter = AdaptiveEscortAdapter(9050 + count, {
                    "uavCount": count,
                    "usvCount": count,
                    "seed": 20260814,
                    "threatMinDistanceM": 120,
                })
                for threat in adapter.threats:
                    protected = adapter.protected[threat.protected_index]
                    self.assertGreaterEqual(
                        math.hypot(threat.x - protected.x, threat.y - protected.y),
                        112.0,
                    )

    def test_active_capture_keeps_mixed_close_guards(self):
        for count in (3, 4, 10, 20, 30):
            with self.subTest(count=count):
                adapter = AdaptiveEscortAdapter(9100 + count, {"uavCount": count, "usvCount": count, "seed": 12})
                adapter.step()
                selected = adapter.activate_capture()
                frame = self.run_frames(adapter, 10)
                guards = [agent for agent in frame.agents if agent.role == "CLOSE_GUARD"]
                self.assertGreaterEqual(sum(agent.type == "UAV" for agent in guards), adapter.plan.protected_count)
                self.assertGreaterEqual(sum(agent.type == "USV" for agent in guards), adapter.plan.protected_count)
                assigned = [agent for agent in frame.agents if agent.assignedTargetCode == selected]
                self.assertGreaterEqual(sum(agent.type == "UAV" for agent in assigned), 2)
                self.assertGreaterEqual(sum(agent.type == "USV" for agent in assigned), 2)

    def test_active_threat_visibly_moves_and_evades(self):
        adapter = AdaptiveEscortAdapter(9201, {"uavCount": 3, "usvCount": 3, "seed": 21, "usvSpeedMps": 1.5})
        adapter.step()
        code = adapter.activate_capture()
        start = next(item for item in adapter.threats if item.code == code)
        start_point = (start.x, start.y)
        headings = []
        for _ in range(160):
            adapter.step()
            threat = next(item for item in adapter.threats if item.code == code)
            headings.append(threat.heading)
        travelled = math.hypot(threat.x - start_point[0], threat.y - start_point[1])
        self.assertGreater(travelled, 8.0)
        self.assertGreater(max(headings) - min(headings), 1.0)

    def test_capture_escape_corridor_points_away_from_protected_target(self):
        adapter = AdaptiveEscortAdapter(9202, {
            "uavCount": 5, "usvCount": 6, "seed": 20260814,
            "uavSpeedMps": 5, "usvSpeedMps": 2,
        })
        adapter.step()
        adapter.activate_capture()
        threat = adapter.threats[0]
        protected = adapter.protected[threat.protected_index]
        distance = math.hypot(threat.x - protected.x, threat.y - protected.y)
        away_x = (threat.x - protected.x) / distance
        away_y = (threat.y - protected.y) / distance
        self.assertGreaterEqual(
            threat.escape_dir_x * away_x + threat.escape_dir_y * away_y,
            0.3,
        )

    def test_capture_waits_for_a_visible_escape_run_before_forming_ring(self):
        adapter = AdaptiveEscortAdapter(9221, {
            "uavCount": 3, "usvCount": 3, "seed": 20260814,
            "uavSpeedMps": 5, "usvSpeedMps": 1,
        })
        adapter.step()
        adapter.activate_capture()
        frame = self.run_frames(adapter, 500)
        threat = adapter.threats[0]
        pursuit_distance = threat.travelled_distance - threat.capture_start_travel_distance
        self.assertGreater(pursuit_distance, 35.0)
        self.assertLess(pursuit_distance, threat.required_pursuit_distance)
        self.assertEqual(threat.capture_stage, 0)
        self.assertEqual(threat.state, "ESCAPE_PURSUIT")
        group = frame.metrics["captureGroups"][0]
        self.assertAlmostEqual(group["pursuitDistanceM"], pursuit_distance, delta=0.2)
        self.assertEqual(group["requiredPursuitDistanceM"], 100.0)

    def test_late_active_capture_gets_a_fresh_deadline_and_completes(self):
        adapter = AdaptiveEscortAdapter(9251, {
            "uavCount": 3, "usvCount": 3, "seed": 20260814,
            "uavSpeedMps": 5, "usvSpeedMps": 1,
        })
        self.run_frames(adapter, 401)
        activation_sequence = adapter.sequence
        adapter.activate_capture()
        terminal = None
        # Automatic capture may already be active before this compatibility
        # command. The convoy then needs its independent escort window to
        # reach the safe destination after containment is complete.
        for _ in range(12000):
            frame = adapter.step()
            terminal = frame.terminalStatus
            if terminal:
                break
        self.assertEqual(terminal, "COMPLETED")
        self.assertGreater(frame.sequence, activation_sequence)
        self.assertNotEqual(frame.metrics["terminalReason"], "active capture time limit reached")
        self.assertEqual(frame.metrics["missionProgress"], 1.0)

    def test_completed_escort_keeps_the_enemy_contained(self):
        adapter = AdaptiveEscortAdapter(9253, {
            "uavCount": 5, "usvCount": 6, "seed": 20260814,
            "uavSpeedMps": 5, "usvSpeedMps": 2,
        })
        frame = None
        minimum_after_capture = math.inf
        minimum_member_clearance = math.inf
        for _ in range(12000):
            frame = adapter.step()
            threat = adapter.threats[0]
            protected = adapter.protected[0]
            if threat.state == "CAPTURED":
                minimum_after_capture = min(
                    minimum_after_capture,
                    math.hypot(threat.x - protected.x, threat.y - protected.y),
                )
                for member in adapter._capture_members(0):
                    minimum_member_clearance = min(
                        minimum_member_clearance,
                        math.hypot(member.x - protected.x, member.y - protected.y),
                    )
            if frame.terminalStatus:
                break
        self.assertEqual(frame.terminalStatus, "COMPLETED")
        self.assertEqual(adapter.threats[0].state, "CAPTURED")
        members = adapter._capture_members(0)
        self.assertGreaterEqual(sum(item.kind == "UAV" for item in members), 2)
        self.assertGreaterEqual(sum(item.kind == "USV" for item in members), 2)
        self.assertTrue(all(item.role == "CONTAINMENT" for item in members))
        self.assertGreaterEqual(minimum_after_capture, CONTAINMENT_STANDOFF_M - 1.0)
        self.assertGreaterEqual(minimum_member_clearance, 38.0)

    def test_multi_threat_capture_uses_fixed_balanced_mixed_groups(self):
        adapter = AdaptiveEscortAdapter(9252, {"uavCount": 10, "usvCount": 10, "seed": 20260814})
        adapter.step()
        adapter.activate_capture()
        frame = adapter.step()
        groups = frame.metrics["captureGroups"]
        self.assertEqual(len(groups), 2)
        self.assertTrue(all(group["uavCount"] >= 2 and group["usvCount"] >= 2 for group in groups))
        self.assertLessEqual(max(group["memberCount"] for group in groups) - min(group["memberCount"] for group in groups), 1)
        assigned_codes = [item.code for item in adapter.vehicles if item.assigned_threat is not None]
        self.assertEqual(len(assigned_codes), len(set(assigned_codes)))
        self.assertIn("escortProgress", frame.metrics)
        self.assertIn("captureProgress", frame.metrics)
        self.assertNotIn("captureRemainingFrames", frame.metrics)

    def test_ten_plus_ten_two_threats_attack_then_get_independent_intercepts(self):
        adapter = AdaptiveEscortAdapter(9254, {
            "uavCount": 10, "usvCount": 10, "seed": 20260814,
            "uavSpeedMps": 5, "usvSpeedMps": 3,
        })
        attack_alignment_frames = {item.code: 0 for item in adapter.threats}
        blocker_groups_seen = set()
        observer_groups_seen = set()
        maximum_target_speed = 0.0
        frame = None
        for _ in range(1800):
            frame = adapter.step()
            maximum_target_speed = max(
                maximum_target_speed,
                max(math.hypot(item.vx, item.vy) for item in adapter.protected),
            )
            blocker_groups_seen.update(
                item.group_id for item in adapter.vehicles if item.role == "BLOCKER"
            )
            observer_groups_seen.update(
                item.group_id for item in adapter.vehicles if item.role == "CONFRONT"
            )
            for threat in adapter.threats:
                if threat.detected_frame is None or threat.forced:
                    continue
                protected = adapter.protected[threat.protected_index]
                ux, uy = (
                    (protected.x - threat.x) / max(1e-6, math.hypot(protected.x - threat.x, protected.y - threat.y)),
                    (protected.y - threat.y) / max(1e-6, math.hypot(protected.x - threat.x, protected.y - threat.y)),
                )
                speed = math.hypot(threat.vx, threat.vy)
                if speed > 0.5 and (threat.vx * ux + threat.vy * uy) / speed > 0.45:
                    attack_alignment_frames[threat.code] += 1
            if all(item.forced for item in adapter.threats):
                break
        self.assertIsNotNone(frame)
        self.assertTrue(all(item.forced for item in adapter.threats))
        self.assertTrue(all(value >= 18 for value in attack_alignment_frames.values()))
        self.assertEqual(blocker_groups_seen, {"BLOCK-001", "BLOCK-002"})
        self.assertEqual(observer_groups_seen, {"WATCH-001", "WATCH-002"})
        self.assertGreater(maximum_target_speed, 1.4)
        self.assertGreater(frame.metrics["attackClosingDistanceM"], 8.0)
        groups = frame.metrics["captureGroups"]
        self.assertEqual(len(groups), 2)
        self.assertTrue(all(group["uavCount"] >= 2 and group["usvCount"] >= 2 for group in groups))
        guards = [item for item in adapter.vehicles if item.role == "CLOSE_GUARD"]
        self.assertGreaterEqual(sum(item.kind == "UAV" for item in guards), 2)
        self.assertGreaterEqual(sum(item.kind == "USV" for item in guards), 2)

    def test_ten_plus_ten_two_threats_complete_capture_and_safe_arrival(self):
        adapter = AdaptiveEscortAdapter(9256, {
            "uavCount": 10, "usvCount": 10, "seed": 20260814,
            "uavSpeedMps": 5, "usvSpeedMps": 3,
        })
        frame = None
        for _ in range(3200):
            frame = adapter.step()
            if frame.terminalStatus:
                break
        self.assertIsNotNone(frame)
        self.assertEqual("COMPLETED", frame.terminalStatus, frame.metrics)
        self.assertTrue(all(item.state == "CAPTURED" for item in adapter.threats))
        self.assertEqual(2, frame.metrics["capturedThreatCount"])
        self.assertEqual(1.0, frame.metrics["escortProgress"])

    def test_surface_and_target_speeds_use_the_raised_dynamic_profile(self):
        adapter = AdaptiveEscortAdapter(9255, {
            "uavCount": 10, "usvCount": 10, "seed": 20260814,
            "uavSpeedMps": 5, "usvSpeedMps": 3,
        })
        maximum_threat_speed = 0.0
        maximum_usv_speed = 0.0
        maximum_target_speed = 0.0
        for _ in range(260):
            adapter.step()
            maximum_threat_speed = max(
                maximum_threat_speed,
                max(math.hypot(item.vx, item.vy) for item in adapter.threats),
            )
            maximum_usv_speed = max(
                maximum_usv_speed,
                max(math.hypot(item.vx, item.vy) for item in adapter.vehicles if item.kind == "USV"),
            )
            maximum_target_speed = max(
                maximum_target_speed,
                max(math.hypot(item.vx, item.vy) for item in adapter.protected),
            )
        self.assertGreater(maximum_threat_speed, 1.7)
        self.assertLessEqual(maximum_threat_speed, 2.41)
        self.assertGreater(maximum_usv_speed, 2.1)
        # Interceptors may accelerate above cruise but remain under the 4 m/s
        # physical surface limit advertised by the simulation UI.
        self.assertLessEqual(maximum_usv_speed, 4.05)
        self.assertGreater(maximum_target_speed, 1.4)
        self.assertLessEqual(maximum_target_speed, 2.26)

    def test_urgent_threats_receive_independent_mixed_response_pairs(self):
        adapter = AdaptiveEscortAdapter(9300, {
            "uavCount": 15, "usvCount": 15, "seed": 20260814,
        })
        for threat in adapter.threats[:3]:
            target = adapter.protected[threat.protected_index]
            threat.x = target.x - 82.0
            threat.y = target.y
            threat.vx = 2.0
            threat.vy = 0.0
            threat.detected_frame = 1
            threat.state = "DETECTED"
        adapter._synchronize_guard_roles()
        for index in range(3):
            blockers = [
                item for item in adapter.vehicles
                if item.group_id == f"BLOCK-{index + 1:03d}"
            ]
            observers = [
                item for item in adapter.vehicles
                if item.group_id == f"WATCH-{index + 1:03d}"
            ]
            self.assertGreaterEqual(len(blockers), 2)
            self.assertGreaterEqual(len(observers), 2)
            desired = [adapter._desired_position(item) for item in blockers]
            self.assertGreater(math.hypot(
                desired[0][0] - desired[1][0],
                desired[0][1] - desired[1][1],
            ), 10.0)

    def test_capture_allocation_preserves_quick_response_reserve(self):
        adapter = AdaptiveEscortAdapter(9302, {
            "uavCount": 15, "usvCount": 15, "seed": 20260814,
        })
        adapter._start_capture_for([adapter.threats[0]], "TEST")
        for kind in ("UAV", "USV"):
            reserve = [
                item for item in adapter.vehicles
                if item.kind == kind and item.role == "RECON"
                and item.assigned_threat is None
            ]
            self.assertGreaterEqual(len(reserve), 2)

    def test_protected_target_moves_and_evades_after_detection(self):
        adapter = AdaptiveEscortAdapter(9301, {"uavCount": 3, "usvCount": 3, "seed": 4})
        start = (adapter.protected[0].x, adapter.protected[0].y)
        states = set()
        for _ in range(900):
            adapter.step()
            states.add(adapter.protected[0].state)
        target = adapter.protected[0]
        self.assertGreater(math.hypot(target.x - start[0], target.y - start[1]), 4.0)
        self.assertTrue(states.intersection({"THREAT_DETECTED", "EVADING"}))

    def test_target_safety_and_water_margin_hold_across_scales(self):
        for count in (3, 4, 10, 20, 30):
            with self.subTest(count=count):
                adapter = AdaptiveEscortAdapter(9400 + count, {"uavCount": count, "usvCount": count, "seed": 31})
                adapter.step()
                adapter.activate_capture()
                frame = self.run_frames(adapter, 500)
                self.assertNotEqual(frame.terminalStatus, "FAILED")
                distance = frame.metrics["minProtectedThreatDistanceM"]
                self.assertIsNotNone(distance)
                self.assertGreaterEqual(distance, BREACH_DISTANCE_M)
                self.assertGreaterEqual(frame.metrics["minShoreDistanceM"], -1e-6)

    def test_mission_has_no_wall_clock_forced_terminal(self):
        adapter = AdaptiveEscortAdapter(9501, {"uavCount": 3, "usvCount": 3, "seed": 2})
        adapter.timeout_frames = 3
        frame = self.run_frames(adapter, 4)
        self.assertIsNone(frame.terminalStatus)
        self.assertNotEqual(frame.phase, "TIMEOUT")

    def test_active_capture_has_no_fixed_deadline(self):
        adapter = AdaptiveEscortAdapter(9502, {"uavCount": 3, "usvCount": 3, "seed": 2})
        self.run_frames(adapter, 50)
        adapter.activate_capture()
        adapter.capture_timeout_frames = 3
        frame = self.run_frames(adapter, 3)
        self.assertIsNone(frame.terminalStatus)
        self.assertEqual(frame.metrics["captureElapsedFrames"], 3)


if __name__ == "__main__":
    unittest.main()
