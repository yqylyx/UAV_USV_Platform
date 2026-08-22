import math
import unittest

from app.adapters.adaptive_escort import AdaptiveEscortAdapter
from app.scenario import derive_scenario_plan


class PhaseTwoScenarioTests(unittest.TestCase):
    def test_threshold_plans_through_realtime_limit(self):
        expected = {
            3: (1, 1, 1, 360, 280),
            10: (1, 2, 2, 360, 280),
            15: (1, 3, 2, 420, 320),
        }
        for count, values in expected.items():
            with self.subTest(count=count):
                plan = derive_scenario_plan(count, count)
                self.assertEqual(
                    (plan.protected_count, plan.threat_count, plan.simultaneous_threats,
                     plan.world_width, plan.world_height),
                    values,
                )
                self.assertEqual(plan.target_count, values[0] + values[1])

    def test_imbalanced_fleet_uses_smaller_serviceable_scale(self):
        self.assertEqual(derive_scenario_plan(20, 5).effective_scale, 5)
        self.assertEqual(derive_scenario_plan(5, 20).target_count, 2)

    def test_multi_target_frame_and_active_capture(self):
        adapter = AdaptiveEscortAdapter(42, {
            "uavCount": 15, "usvCount": 15, "seed": 20260814,
            "adaptiveMultiTarget": True,
        })
        initial = adapter.step()
        self.assertEqual(len(initial.agents), 30)
        self.assertEqual(len(initial.targets), 4)
        self.assertEqual(sum(t.type == "ESCORT_TARGET" for t in initial.targets), 1)
        self.assertEqual(sum(t.type == "THREAT_TARGET" for t in initial.targets), 3)
        self.assertEqual(sum(t.visible for t in initial.targets if t.type == "THREAT_TARGET"), 2)
        selected = adapter.activate_capture()
        self.assertTrue(selected.startswith("THREAT-"))
        frame = adapter.step()
        assigned = [agent for agent in frame.agents if agent.assignedTargetCode == selected]
        self.assertGreaterEqual(len(assigned), 3)

    def test_capture_team_scales_beyond_fixed_two_plus_two(self):
        adapter = AdaptiveEscortAdapter(421, {
            "uavCount": 15, "usvCount": 15, "seed": 20260814,
            "adaptiveMultiTarget": True,
        })
        selected = adapter.activate_capture()
        adapter.step()  # authoritative random initial scene
        frame = adapter.step()
        assigned = [agent for agent in frame.agents if agent.assignedTargetCode == selected]
        self.assertGreaterEqual(sum(agent.type == "UAV" for agent in assigned), 4)
        self.assertGreaterEqual(sum(agent.type == "USV" for agent in assigned), 4)

    def test_speed_controls_change_surface_step(self):
        slow = AdaptiveEscortAdapter(422, {
            "uavCount": 3, "usvCount": 3, "usvSpeedMps": 0.4, "seed": 2,
        })
        fast = AdaptiveEscortAdapter(423, {
            "uavCount": 3, "usvCount": 3, "usvSpeedMps": 1.6, "seed": 2,
        })
        slow_initial = slow.step()
        fast_initial = fast.step()
        slow_next = slow.step()
        fast_next = fast.step()
        def mean_surface_step(first, second):
            old = {item.code: item for item in first.agents}
            values = [math.hypot(item.x - old[item.code].x, item.y - old[item.code].y)
                      for item in second.agents if item.type == "USV"]
            return sum(values) / len(values)
        self.assertGreater(
            mean_surface_step(fast_initial, fast_next),
            mean_surface_step(slow_initial, slow_next) * 1.8,
        )

    def test_targets_approach_from_distinct_sectors(self):
        adapter = AdaptiveEscortAdapter(43, {"uavCount": 15, "usvCount": 15, "seed": 7})
        visible = [item for item in adapter.threats if item.state != "WAITING"]
        angles = sorted(math.atan2(item.y, item.x) for item in visible)
        gaps = [
            (angles[(index + 1) % len(angles)] - angles[index]) % (2 * math.pi)
            for index in range(len(angles))
        ]
        self.assertGreaterEqual(min(gaps), math.radians(60))

    def test_thirty_plus_thirty_stays_in_bounds(self):
        adapter = AdaptiveEscortAdapter(44, {"uavCount": 15, "usvCount": 15, "seed": 9})
        for _ in range(120):
            frame = adapter.step()
        min_x, max_x, min_y, max_y = adapter.safety.bounds
        for agent in frame.agents:
            self.assertLessEqual(min_x, agent.x)
            self.assertLessEqual(agent.x, max_x)
            self.assertLessEqual(min_y, agent.y)
            self.assertLessEqual(agent.y, max_y)


if __name__ == "__main__":
    unittest.main()
