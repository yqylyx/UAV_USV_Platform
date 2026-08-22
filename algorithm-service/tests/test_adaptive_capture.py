import contextlib
import io
import math
import unittest

from app.adapters.adaptive_capture import AdaptiveCaptureAdapter
from app.navigation import TASK_CENTER_SCENE_MAP, SceneSafetyFilter


def frontend_multi_target_config(count: int, seed: int = 20260814):
    """Mirror the current capture-mode layout emitted by the Vue frontend."""
    poses = []
    state = seed & 0xFFFFFFFF

    def random_value():
        nonlocal state
        state = (state * 1664525 + 1013904223) & 0xFFFFFFFF
        return state / 0x100000000

    columns = math.ceil(math.sqrt(count))
    rows = math.ceil(count / columns)
    corridor = 55 + max(0, columns - 2) * 4
    for kind, spacing in (("UAV", 10.0), ("USV", 14.0)):
        for index in range(count):
            row, column = divmod(index, columns)
            east = corridor + column * spacing + (random_value() - 0.5) * spacing * 0.18
            north = (row - (rows - 1) / 2) * spacing + (random_value() - 0.5) * spacing * 0.18
            poses.append({
                "deviceCode": f"{kind}-{index + 1:03d}",
                "deviceType": kind,
                "eastM": east,
                "northM": north,
                "upM": 20.0 + index % 4 * 2.0 if kind == "UAV" else 0.0,
                "headingDeg": random_value() * 360.0,
                "valid": True,
            })
    spread = 72.8
    for index, north in enumerate((-spread, spread), start=1):
        poses.append({
            "deviceCode": f"TARGET-{index:03d}",
            "deviceType": "TARGET",
            "eastM": -corridor - abs(north) * 0.12,
            "northM": north,
            "upM": 0.0,
            "headingDeg": 180.0 if index == 1 else 0.0,
            "valid": True,
        })
    return {
        "uavCount": count,
        "usvCount": count,
        "targetCount": 2,
        "seed": seed,
        "uavSpeedMps": 5.0,
        "usvSpeedMps": 3.2,
        "initialPoses": poses,
        "initialPosesCoordinateFrame": "GLOBAL_ENU",
        "fleetOrigin": {"eastM": 0.0, "northM": 0.0, "upM": 0.0},
    }


class AdaptiveCaptureAdapterTest(unittest.TestCase):
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

    def test_ten_to_fourteen_two_targets_close_both_rings(self):
        for count in (10, 11, 12, 13, 14):
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
                for _ in range(1000):
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

    def test_visible_chase_starts_settling_without_false_containment_candidate(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            adapter = AdaptiveCaptureAdapter(9050, {
                "uavCount": 10,
                "usvCount": 10,
                "targetCount": 2,
                "seed": 20260814,
            })
            adapter.set_mission_active(True)
            for child in adapter.children:
                child.target_travelled_distance = child.required_pursuit_distance + 20.0
            frame = adapter.step()

        self.assertFalse(frame.metrics["captured"])
        for child, group in zip(adapter.children, frame.metrics["captureGroups"]):
            self.assertIsNotNone(child.settling_started_at_sequence)
            self.assertIsNone(child.containment_candidate_at_sequence)
            self.assertEqual(0, group["holdFrames"])

    def test_exact_frontend_ten_and_eleven_layouts_complete_post_global_hold(self):
        for count in (10, 11):
            with self.subTest(count=count):
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    adapter = AdaptiveCaptureAdapter(9100 + count, frontend_multi_target_config(count))
                    adapter.set_mission_active(True)
                    final = None
                    for _ in range(1500):
                        final = adapter.step()
                        if final.terminalStatus == "COMPLETED":
                            break

                self.assertIsNotNone(final)
                self.assertEqual("COMPLETED", final.terminalStatus, final.metrics)
                self.assertTrue(all(
                    group["postGlobalContainmentReady"]
                    for group in final.metrics["captureGroups"]
                ))
                self.assertEqual(2, final.metrics["capturedTargetCount"])


if __name__ == "__main__":
    unittest.main()
