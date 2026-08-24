import contextlib
import io
import unittest

from app.adapters.adaptive_capture import AdaptiveCaptureAdapter
from app.adapters.adaptive_escort import AdaptiveEscortAdapter


def quiet_step(adapter):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return adapter.step()


class BreakoutTestRegression(unittest.TestCase):
    def test_capture_requires_breakout_before_completion(self):
        adapter = AdaptiveCaptureAdapter(9601, {
            "uavCount": 5,
            "usvCount": 5,
            "targetCount": 1,
            "seed": 20260814,
            "breakoutTestFrames": 15,
            "breakoutTestDistanceM": 3.0,
        })
        adapter.set_mission_active(True)
        active_seen = False
        passed_seen = False
        for _ in range(900):
            frame = quiet_step(adapter)
            group = frame.metrics["captureGroups"][0]
            state = group["breakoutTestState"]
            active_seen = active_seen or state == "ACTIVE"
            if state == "ACTIVE":
                self.assertIsNone(frame.terminalStatus)
                self.assertNotEqual("COMPLETED", frame.phase)
            passed_seen = passed_seen or state == "PASSED"
            if frame.terminalStatus:
                break
        self.assertTrue(active_seen, "capture never entered BREAKOUT_TEST")
        self.assertTrue(passed_seen, "capture never passed BREAKOUT_TEST")
        self.assertEqual("COMPLETED", frame.terminalStatus)

    def test_capture_coordinator_uses_executed_breakout_state(self):
        adapter = AdaptiveCaptureAdapter(9602, {
            "uavCount": 10,
            "usvCount": 10,
            "targetCount": 2,
            "seed": 20260814,
            "breakoutTestFrames": 15,
            "breakoutTestDistanceM": 3.0,
        })
        adapter.set_mission_active(True)
        active_seen = False
        passed_seen = False
        for _ in range(1000):
            frame = quiet_step(adapter)
            states = {group["breakoutTestState"] for group in frame.metrics["captureGroups"]}
            active_seen = active_seen or "ACTIVE" in states
            passed_seen = passed_seen or "PASSED" in states
            if "ACTIVE" in states:
                self.assertIsNone(frame.terminalStatus)
            if frame.terminalStatus:
                break
        self.assertTrue(active_seen)
        self.assertTrue(passed_seen)
        self.assertEqual("COMPLETED", frame.terminalStatus)
        self.assertEqual(2, frame.metrics["capturedTargetCount"])

    def test_capture_10_plus_10_exposes_breakout_phase_for_single_target(self):
        adapter = AdaptiveCaptureAdapter(9604, {
            "uavCount": 10,
            "usvCount": 10,
            "targetCount": 1,
            "seed": 20260814,
            "breakoutTestFrames": 15,
            "breakoutTestDistanceM": 3.0,
        })
        adapter.set_mission_active(True)
        breakout_frame = None
        for _ in range(1000):
            frame = quiet_step(adapter)
            group = frame.metrics["captureGroups"][0]
            if group["breakoutTestState"] == "ACTIVE":
                breakout_frame = frame
                self.assertEqual("BREAKOUT_TEST", frame.phase)
                self.assertEqual("BREAKOUT_TEST", group["state"])
                self.assertIsNone(frame.terminalStatus)
                break
        self.assertIsNotNone(breakout_frame, "10+10 capture never entered BREAKOUT_TEST")

    def test_escort_requires_breakout_before_completion(self):
        adapter = AdaptiveEscortAdapter(9603, {
            "uavCount": 5,
            "usvCount": 5,
            "seed": 20260814,
            "breakoutTestFrames": 15,
            "breakoutTestDistanceM": 3.0,
        })
        quiet_step(adapter)
        adapter.activate_capture()
        active_seen = False
        passed_seen = False
        for _ in range(1400):
            frame = quiet_step(adapter)
            groups = frame.metrics.get("captureGroups", [])
            states = {group["breakoutTestState"] for group in groups}
            active_seen = active_seen or "ACTIVE" in states
            passed_seen = passed_seen or "PASSED" in states
            if "ACTIVE" in states:
                self.assertNotEqual("COMPLETED", frame.terminalStatus)
                self.assertNotEqual("COMPLETED", frame.phase)
            if frame.terminalStatus:
                break
        self.assertTrue(active_seen, "escort never entered BREAKOUT_TEST")
        self.assertTrue(passed_seen, "escort never passed BREAKOUT_TEST")
        self.assertEqual("COMPLETED", frame.terminalStatus)


if __name__ == "__main__":
    unittest.main()
