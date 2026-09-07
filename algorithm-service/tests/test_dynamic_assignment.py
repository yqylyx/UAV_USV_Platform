from __future__ import annotations

import unittest

from app.decision import DecisionAgent, DecisionTarget, DynamicTaskAllocator


class DynamicTaskAllocatorTests(unittest.TestCase):
    def test_predictive_assignment_preserves_exact_mixed_capacities(self) -> None:
        allocator = DynamicTaskAllocator(
            evaluation_interval_frames=1,
            minimum_improvement_ratio=0.05,
            confirmation_cycles=2,
            cooldown_frames=0,
        )
        agents = [
            DecisionAgent("UAV-001", "UAV", -80, 0, 5, 0, 15, "TARGET-002"),
            DecisionAgent("UAV-002", "UAV", 80, 0, 5, 180, 15, "TARGET-001"),
            DecisionAgent("USV-001", "USV", -70, -5, 3, 0, 4, "TARGET-002"),
            DecisionAgent("USV-002", "USV", 70, 5, 3, 180, 4, "TARGET-001"),
        ]
        targets = [
            DecisionTarget("TARGET-001", -35, 0, -1.8, 0),
            DecisionTarget("TARGET-002", 35, 0, 1.8, 0),
        ]
        capacities = {
            "TARGET-001": {"UAV": 1, "USV": 1},
            "TARGET-002": {"UAV": 1, "USV": 1},
        }

        first = allocator.evaluate(agents, targets, capacities, frame=10)
        self.assertFalse(first.accepted)
        self.assertEqual("AWAITING_CONFIRMATION", first.reason)
        second = allocator.evaluate(agents, targets, capacities, frame=11)
        self.assertTrue(second.accepted)
        self.assertGreater(second.improvement_ratio, 0.05)
        for target_code in capacities:
            assigned = [
                agent for agent in agents
                if second.assignments[agent.code] == target_code
            ]
            self.assertEqual(1, sum(agent.kind == "UAV" for agent in assigned))
            self.assertEqual(1, sum(agent.kind == "USV" for agent in assigned))

    def test_small_gain_does_not_churn_current_groups(self) -> None:
        allocator = DynamicTaskAllocator(
            evaluation_interval_frames=1,
            minimum_improvement_ratio=0.25,
            confirmation_cycles=1,
            cooldown_frames=0,
        )
        agents = [
            DecisionAgent("USV-001", "USV", -2, 0, 3, 0, 4, "TARGET-001"),
            DecisionAgent("USV-002", "USV", 2, 0, 3, 180, 4, "TARGET-002"),
        ]
        targets = [
            DecisionTarget("TARGET-001", 1, 0, 0, 0),
            DecisionTarget("TARGET-002", -1, 0, 0, 0),
        ]
        result = allocator.evaluate(
            agents,
            targets,
            {
                "TARGET-001": {"USV": 1},
                "TARGET-002": {"USV": 1},
            },
            frame=1,
        )
        self.assertFalse(result.accepted)
        self.assertEqual(
            {"USV-001": "TARGET-001", "USV-002": "TARGET-002"},
            result.assignments,
        )

    def test_stalled_member_can_bypass_confirmation(self) -> None:
        allocator = DynamicTaskAllocator(
            evaluation_interval_frames=1,
            minimum_improvement_ratio=0.99,
            confirmation_cycles=3,
            cooldown_frames=0,
            stalled_override_frames=10,
        )
        agents = [
            DecisionAgent("USV-001", "USV", -50, 0, 0, 0, 4, "TARGET-002", stalled_frames=12),
            DecisionAgent("USV-002", "USV", 50, 0, 3, 180, 4, "TARGET-001"),
        ]
        targets = [
            DecisionTarget("TARGET-001", -20, 0, 0, 0),
            DecisionTarget("TARGET-002", 20, 0, 0, 0),
        ]
        result = allocator.evaluate(
            agents,
            targets,
            {
                "TARGET-001": {"USV": 1},
                "TARGET-002": {"USV": 1},
            },
            frame=20,
        )
        self.assertTrue(result.accepted)
        self.assertEqual("STALLED_RELIEF", result.reason)


if __name__ == "__main__":
    unittest.main()
