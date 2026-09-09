import math
import unittest

from app.adapters.capture import CaptureAdapter


def pose(code, kind, east, north, up=0.0):
    return {
        "deviceCode": code,
        "deviceType": kind,
        "eastM": east,
        "northM": north,
        "upM": up,
        "headingDeg": 0.0,
        "speedMps": 0.0,
        "state": "READY",
        "valid": True,
    }


class CaptureV4AcceptanceTests(unittest.TestCase):
    def config(self):
        origin = {"eastM": -150.0, "northM": -275.0, "upM": 0.0}
        poses = []
        for kind, altitude in (("UAV", 25.0), ("USV", 0.0)):
            for index, north in enumerate((-14.0, 0.0, 14.0), start=1):
                poses.append(pose(
                    f"{kind}-{index:03d}",
                    kind,
                    origin["eastM"] - 55.0 - (index % 2) * 12.0,
                    origin["northM"] + north,
                    altitude,
                ))
        poses.append(pose(
            "TARGET-001",
            "TARGET",
            origin["eastM"] + 55.0,
            origin["northM"],
        ))
        return {
            "uavCount": 3,
            "usvCount": 3,
            "seed": 20260814,
            "uavSpeedMps": 5.0,
            "usvSpeedMps": 1.0,
            "targetBehavior": "MOVING",
            "threatMinDistanceM": 90.0,
            "fleetOrigin": origin,
            "initialPosesCoordinateFrame": "GLOBAL_ENU",
            "initialPoses": poses,
        }

    def test_initial_target_is_far_from_every_pursuer(self):
        adapter = CaptureAdapter(7001, self.config())
        frame = adapter.step()
        target = frame.targets[0]
        self.assertGreaterEqual(
            min(math.hypot(agent.x - target.x, agent.y - target.y) for agent in frame.agents),
            90.0,
        )

    def test_escape_corridor_is_in_the_away_half_plane(self):
        adapter = CaptureAdapter(7003, self.config())
        frame = adapter.step()
        target = frame.targets[0]
        center_x = sum(agent.x for agent in frame.agents) / len(frame.agents)
        center_y = sum(agent.y for agent in frame.agents) / len(frame.agents)
        distance = math.hypot(target.x - center_x, target.y - center_y)
        away_x = (target.x - center_x) / distance
        away_y = (target.y - center_y) / distance
        escape_x, escape_y = adapter.target_escape_direction
        self.assertGreaterEqual(escape_x * away_x + escape_y * away_y, 0.3)

    def test_target_runs_before_encirclement(self):
        adapter = CaptureAdapter(7002, self.config())
        adapter.step()
        frame = None
        for _ in range(300):
            frame = adapter.step()
        self.assertEqual(frame.phase, "ESCAPE_PURSUIT")
        self.assertGreater(frame.metrics["targetTravelDistanceM"], 20.0)
        self.assertLess(
            frame.metrics["targetTravelDistanceM"],
            frame.metrics["requiredPursuitDistanceM"],
        )
        self.assertFalse(frame.metrics["formationReady"])
        self.assertGreater(
            frame.metrics["targetNetDisplacementM"],
            frame.metrics["targetTravelDistanceM"] * 0.65,
        )

    def test_external_executed_ring_is_the_only_authority_that_can_slow_target(self):
        config = self.config()
        config["externalContainmentAuthority"] = True
        adapter = CaptureAdapter(7004, config)
        target = adapter._to_scene(adapter.env.targets[0, :3], "TARGET")
        adapter.containment_candidate_at_sequence = 1
        adapter.target_travelled_distance = adapter.required_pursuit_distance + 5.0
        adapter.target_velocity = (
            adapter.target_escape_direction[0] * adapter.target_cruise_mps,
            adapter.target_escape_direction[1] * adapter.target_cruise_mps,
        )

        adapter.sequence = 2
        adapter._advance_capture_target(target)
        self.assertGreaterEqual(
            math.hypot(*adapter.target_velocity),
            adapter.target_cruise_mps * 0.99,
        )
        self.assertNotEqual("EXECUTED_CONTAINMENT_DECEL", adapter.target_speed_reason)

        adapter.set_executed_containment_feedback(
            ready=True,
            confidence=1.0,
            max_gap_deg=25.0,
            allowed_gap_deg=38.0,
        )
        # Exercise real 0.1 s control steps, not a sequence jump followed by
        # one step that demanded an instantaneous velocity collapse.
        for _ in range(adapter.capture_hold_frames):
            previous_speed = math.hypot(*adapter.target_velocity)
            adapter.sequence += 1
            safe = adapter._advance_capture_target(target)
            target = (safe.x, safe.y, safe.z)
            self.assertLessEqual(previous_speed-math.hypot(*adapter.target_velocity), .10001)
        self.assertLess(math.hypot(*adapter.target_velocity), adapter.target_cruise_mps * 0.35)
        self.assertEqual("EXECUTED_CONTAINMENT_DECEL", adapter.target_speed_reason)


if __name__ == "__main__":
    unittest.main()
