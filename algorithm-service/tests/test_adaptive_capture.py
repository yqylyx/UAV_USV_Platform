import contextlib
import io
import math
import unittest

from app.adapters.adaptive_capture import AdaptiveCaptureAdapter
from app.navigation import TASK_CENTER_SCENE_MAP, SceneSafetyFilter


class AdaptiveCaptureAdapterTest(unittest.TestCase):
    def test_stale_completed_stage_is_revoked_when_a_global_ring_is_open(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            adapter = AdaptiveCaptureAdapter(8997, {
                "uavCount": 10, "usvCount": 10, "targetCount": 2,
                "seed": 20260814,
            })
        adapter.set_mission_active(True)
        # Reproduce the presentation state left by a transient all-closed
        # frame. The following executed frame is still in pursuit, so its
        # terminal stage must follow current global geometry.
        adapter.reported_mission_stage = "COMPLETED"

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            frame = adapter.step()

        self.assertIsNone(frame.terminalStatus)
        self.assertNotEqual("COMPLETED", frame.metrics["missionStage"])
        self.assertLess(frame.metrics["progress"], 1.0)

    def test_any_gap_breaks_the_consecutive_visual_hold(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            adapter = AdaptiveCaptureAdapter(8999, {
                "uavCount": 3, "usvCount": 3, "targetCount": 1,
            })
        adapter.containment_stage_latched[0] = True
        adapter.executed_hold_frames[0] = 6
        value, retained = adapter._update_executed_hold(
            0, 6, 25, {"ready": False, "blocker": "POST_GLOBAL_ANGULAR_GAP"},
        )
        self.assertFalse(retained)
        self.assertEqual(0, value)

    def test_hard_failure_immediately_drops_latched_containment(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            adapter = AdaptiveCaptureAdapter(8998, {
                "uavCount": 3, "usvCount": 3, "targetCount": 1,
            })
        adapter.containment_stage_latched[0] = True
        value, retained = adapter._update_executed_hold(
            0, 6, 25, {"ready": False, "blocker": "POST_GLOBAL_TARGET_OUTSIDE_HULL"},
        )
        self.assertFalse(retained)
        self.assertEqual(0, value)

    def test_ten_by_ten_uses_two_independent_targets(self):
        adapter = AdaptiveCaptureAdapter(9001, {
            "uavCount": 10,
            "usvCount": 10,
            "targetCount": 2,
            "seed": 20260814,
        })
        adapter.set_mission_active(False)

        frame = adapter.step()

        self.assertEqual(20, len(frame.agents))
        self.assertEqual(20, len({agent.code for agent in frame.agents}))
        self.assertEqual(["TARGET-001", "TARGET-002"], [target.code for target in frame.targets])
        self.assertEqual(2, frame.metrics["targetCount"])
        self.assertEqual(2, len(frame.metrics["captureGroups"]))
        for target_code in ("TARGET-001", "TARGET-002"):
            assigned = [
                agent for agent in frame.agents
                if agent.assignedTargetCode == target_code
            ]
            self.assertEqual(10, len(assigned))
            self.assertEqual(5, sum(agent.type == "UAV" for agent in assigned))
            self.assertEqual(5, sum(agent.type == "USV" for agent in assigned))

    def test_eighteen_by_eighteen_balances_all_three_target_groups(self):
        adapter = AdaptiveCaptureAdapter(9018, {
            "uavCount": 18,
            "usvCount": 18,
            "targetCount": 3,
            "seed": 20260814,
        })
        adapter.set_mission_active(False)

        frame = adapter.step()

        self.assertEqual(36, len(frame.agents))
        self.assertEqual(36, len({agent.code for agent in frame.agents}))
        self.assertEqual(3, len(frame.metrics["captureGroups"]))
        groups = {
            group["threatCode"]: group
            for group in frame.metrics["captureGroups"]
        }
        for target_code in ("TARGET-001", "TARGET-002", "TARGET-003"):
            assigned = [
                agent for agent in frame.agents
                if agent.assignedTargetCode == target_code
            ]
            self.assertEqual(12, len(assigned))
            self.assertEqual(6, sum(agent.type == "UAV" for agent in assigned))
            self.assertEqual(6, sum(agent.type == "USV" for agent in assigned))
            self.assertEqual(12, groups[target_code]["ringMemberCount"])
            self.assertEqual(12, groups[target_code]["requiredMemberCount"])
            self.assertIsInstance(
                groups[target_code]["detachedParticipantCodes"], list
            )

    def test_all_groups_advance_after_start(self):
        adapter = AdaptiveCaptureAdapter(9002, {
            "uavCount": 10,
            "usvCount": 10,
            "targetCount": 2,
            "seed": 7,
        })
        adapter.set_mission_active(False)
        preview = adapter.step()
        adapter.set_mission_active(True)
        running = adapter.step()

        self.assertEqual(1, preview.sequence)
        self.assertEqual(2, running.sequence)
        self.assertNotEqual("PREVIEW", running.phase)
        self.assertEqual(2, len(running.targets))
        self.assertTrue(all(group["state"] != "PREVIEW" for group in running.metrics["captureGroups"]))

    def test_multi_target_groups_share_one_global_collision_envelope(self):
        safety = SceneSafetyFilter(TASK_CENTER_SCENE_MAP)
        with contextlib.redirect_stdout(io.StringIO()):
            adapter = AdaptiveCaptureAdapter(9003, {
                "uavCount": 10,
                "usvCount": 10,
                "targetCount": 2,
                "seed": 20260814,
            })
        previous = None
        minimum_margin = math.inf
        worst_pair = ""
        for _ in range(700):
            with contextlib.redirect_stdout(io.StringIO()):
                current = adapter.step()
            if previous is not None:
                old = {agent.code: agent for agent in previous.agents}
                for index, left in enumerate(current.agents):
                    for right in current.agents[index + 1:]:
                        required = safety.required_separation(
                            left.type,
                            right.type,
                            left.z,
                            right.z,
                        )
                        endpoint = math.hypot(left.x - right.x, left.y - right.y)
                        swept = safety.swept_distance(
                            (old[left.code].x, old[left.code].y),
                            (left.x, left.y),
                            (old[right.code].x, old[right.code].y),
                            (right.x, right.y),
                        )
                        margin = min(endpoint, swept) - required
                        if margin < minimum_margin:
                            minimum_margin = margin
                            worst_pair = (
                                f"{current.phase} {left.code}/{right.code} "
                                f"endpoint={endpoint:.3f} swept={swept:.3f} required={required:.3f}"
                            )
            previous = current
            if current.terminalStatus:
                break
        self.assertGreaterEqual(minimum_margin, -0.05, worst_pair)

    def test_twelve_to_fourteen_two_targets_close_both_rings(self):
        for count in (12, 13, 14):
            with self.subTest(count=count):
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    adapter = AdaptiveCaptureAdapter(9000 + count, {
                        "uavCount": count,
                        "usvCount": count,
                        "targetCount": 2,
                        "seed": 20260814,
                    })
                adapter.set_mission_active(True)
                final = None
                for _ in range(1800):
                    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                        final = adapter.step()
                    if final.terminalStatus == "COMPLETED":
                        break

                self.assertIsNotNone(final)
                self.assertEqual("COMPLETED", final.terminalStatus)
                self.assertEqual(1.0, final.metrics["progress"])
                self.assertEqual(2, final.metrics["capturedTargetCount"])
                self.assertEqual("NONE", final.metrics["captureBlocker"])
                self.assertTrue(final.metrics["formationReady"])
                self.assertTrue(final.metrics["ringGeometryReady"])
                for group in final.metrics["captureGroups"]:
                    self.assertEqual("CAPTURED", group["state"])
                    self.assertEqual(3, group["stage"])
                    self.assertEqual(1.0, group["arrivalRatio"])
                    self.assertGreaterEqual(group["holdFrames"], group["holdRequiredFrames"])
                    self.assertEqual("NONE", group["captureBlocker"])
                    self.assertLessEqual(group["holdFrames"], group["holdRequiredFrames"])


if __name__ == "__main__":
    unittest.main()
