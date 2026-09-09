import contextlib
import io
import math
import unittest

from app.adapters.adaptive_capture import AdaptiveCaptureAdapter
from app.navigation import TASK_CENTER_SCENE_MAP, SceneSafetyFilter


class AdaptiveCaptureAdapterTest(unittest.TestCase):
    def test_enemy_motion_is_bow_first_and_continuous_including_preview_start(self):
        for count in (3, 10):
            with self.subTest(count=count), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                a = AdaptiveCaptureAdapter(9911, {"uavCount":count, "usvCount":count, "targetCount":1 if count==3 else 2, "seed":20260814})
                a.set_mission_active(False)
                previous = {}
                for index in range(2000):
                    if index == 20:
                        a.set_mission_active(True)
                    f = a.step()
                    for t in f.targets:
                        if t.code in previous:
                            x,y,h = previous[t.code]
                            dx,dy = t.x-x,t.y-y
                            angle = math.radians(t.heading)
                            why = (count,index,t.code)
                            self.assertLessEqual(math.hypot(dx,dy), .282, why)
                            self.assertGreaterEqual(dx*math.cos(angle)+dy*math.sin(angle), -.002, why)
                            self.assertLessEqual(abs(-dx*math.sin(angle)+dy*math.cos(angle)), .003, why)
                            self.assertLessEqual(abs((t.heading-h+180)%360-180), 7.1, why)
                        previous[t.code] = (t.x,t.y,t.heading)
                    if f.terminalStatus:
                        break
                self.assertEqual(f.terminalStatus, "COMPLETED")

    def test_predictive_reassignment_changes_members_but_preserves_balanced_quotas(self):
        adapter = AdaptiveCaptureAdapter(91, {
            "uavCount": 6,
            "usvCount": 6,
            "targetCount": 2,
            "seed": 20260814,
            "assignmentEvaluationFrames": 1,
            "assignmentConfirmationCycles": 2,
            "assignmentMinimumImprovement": 0.01,
        })
        adapter.set_mission_active(True)
        initial = {
            global_code: f"TARGET-{target_index + 1:03d}"
            for target_index, mapping in enumerate(adapter.agent_code_maps)
            for global_code in mapping.values()
        }
        centers = [(-120.0, 0.0, 0.0), (120.0, 0.0, 0.0)]
        for child, center in zip(adapter.children, centers):
            child.previous_scene["TARGET"] = center
            child.target_velocity = (0.0, 0.0)
        for target_index, mapping in enumerate(adapter.agent_code_maps):
            opposite = centers[1 - target_index]
            for offset, global_code in enumerate(sorted(mapping.values())):
                adapter.previous_scene[global_code] = (
                    opposite[0] + (offset % 3) * 0.4,
                    opposite[1] + (offset // 3) * 0.4,
                    25.0 if global_code.startswith("UAV-") else 0.0,
                )
        adapter.sequence = 10
        adapter._maybe_reassign_capture_groups()
        adapter.sequence = 15
        adapter._maybe_reassign_capture_groups()

        updated = {
            global_code: f"TARGET-{target_index + 1:03d}"
            for target_index, mapping in enumerate(adapter.agent_code_maps)
            for global_code in mapping.values()
        }
        self.assertNotEqual(initial, updated)
        self.assertGreater(adapter.dynamic_allocator.reassignment_count, 0)
        for mapping in adapter.agent_code_maps:
            values = list(mapping.values())
            self.assertEqual(3, sum(code.startswith("UAV-") for code in values))
            self.assertEqual(3, sum(code.startswith("USV-") for code in values))
        self.assertEqual(12, len(updated))

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
