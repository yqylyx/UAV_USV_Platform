import contextlib
import io
import unittest

from app.adapters.adaptive_capture import AdaptiveCaptureAdapter
from app.adapters.adaptive_escort import AdaptiveEscortAdapter


def quiet_step(adapter):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return adapter.step()


class DirectContainmentRegression(unittest.TestCase):
    def test_capture_completes_only_after_stable_live_ring(self):
        adapter = AdaptiveCaptureAdapter(9601, {
            "uavCount": 5,
            "usvCount": 5,
            "targetCount": 1,
            "seed": 20260814,
        })
        adapter.set_mission_active(True)
        for _ in range(1800):
            frame = quiet_step(adapter)
            group = frame.metrics["captureGroups"][0]
            self.assertNotIn("breakoutTestState", group)
            self.assertNotEqual("BREAKOUT_TEST", frame.phase)
            if frame.terminalStatus:
                break
        self.assertEqual("COMPLETED", frame.terminalStatus)
        self.assertTrue(group["postGlobalContainmentReady"])

    def test_capture_coordinator_requires_every_executed_ring(self):
        adapter = AdaptiveCaptureAdapter(9602, {
            "uavCount": 10,
            "usvCount": 10,
            "targetCount": 2,
            "seed": 20260814,
        })
        adapter.set_mission_active(True)
        for _ in range(1800):
            frame = quiet_step(adapter)
            if frame.terminalStatus:
                break
        self.assertEqual("COMPLETED", frame.terminalStatus)
        self.assertEqual(2, frame.metrics["capturedTargetCount"])
        self.assertTrue(all(
            group["postGlobalContainmentReady"]
            for group in frame.metrics["captureGroups"]
        ))

    def test_capture_never_exposes_removed_breakout_phase(self):
        adapter = AdaptiveCaptureAdapter(9604, {
            "uavCount": 10,
            "usvCount": 10,
            "targetCount": 1,
            "seed": 20260814,
        })
        adapter.set_mission_active(True)
        for _ in range(1800):
            frame = quiet_step(adapter)
            group = frame.metrics["captureGroups"][0]
            self.assertNotEqual("BREAKOUT_TEST", frame.phase)
            self.assertNotEqual("BREAKOUT_TEST", group["state"])
            self.assertNotIn("breakoutTestState", group)
            if frame.terminalStatus:
                break
        self.assertEqual("COMPLETED", frame.terminalStatus)

    def test_escort_uses_live_ring_without_breakout_stage(self):
        adapter = AdaptiveEscortAdapter(9603, {
            "uavCount": 5,
            "usvCount": 5,
            "seed": 20260814,
        })
        quiet_step(adapter)
        adapter.activate_capture()
        for _ in range(5000):
            frame = quiet_step(adapter)
            groups = frame.metrics.get("captureGroups", [])
            self.assertNotEqual("BREAKOUT_TEST", frame.phase)
            self.assertTrue(all("breakoutTestState" not in group for group in groups))
            if frame.terminalStatus:
                break
        self.assertEqual("COMPLETED", frame.terminalStatus)
        self.assertEqual(
            frame.metrics["threatCount"],
            frame.metrics["capturedThreatCount"],
        )


if __name__ == "__main__":
    unittest.main()
