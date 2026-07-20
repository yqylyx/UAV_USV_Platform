from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path


SERVICE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_DIR))

from adapters.capture_adapter import load_capture_module, probe_capture_core_step, run_capture_once
from adapters.models import AlgorithmRequest, Position, VehicleState


class CaptureAdapterTest(unittest.TestCase):
    def _valid_request(self, command_id: str = "cmd-capture-1") -> AlgorithmRequest:
        return AlgorithmRequest(
            commandId=command_id,
            algorithmType="CAPTURE",
            targetId="target-1",
            targetPosition=Position(x=100.0, y=100.0, z=0.0),
            uavs=[
                VehicleState(vehicleId="uav-01", x=0.0, y=0.0, z=20.0, heading=0.0),
                VehicleState(vehicleId="uav-02", x=10.0, y=0.0, z=20.0, heading=0.0),
                VehicleState(vehicleId="uav-03", x=20.0, y=0.0, z=20.0, heading=0.0),
            ],
            usvs=[
                VehicleState(vehicleId="usv-01", x=0.0, y=10.0, z=0.0, heading=0.0),
                VehicleState(vehicleId="usv-02", x=10.0, y=10.0, z=0.0, heading=0.0),
                VehicleState(vehicleId="usv-03", x=20.0, y=10.0, z=0.0, heading=0.0),
            ],
            parameters={"minimumAgents": 3},
        )

    def test_legacy_module_imports_and_executes_core_step(self) -> None:
        probe = probe_capture_core_step()

        self.assertEqual(probe["status"], "RUNNING")
        self.assertEqual(probe["fixedConfiguration"]["uavCount"], 40)
        self.assertEqual(probe["fixedConfiguration"]["usvCount"], 40)
        self.assertEqual(probe["fixedConfiguration"]["targetCount"], 20)
        self.assertEqual(probe["agentCount"], 80)
        self.assertEqual(probe["targetCount"], 20)
        self.assertGreater(probe["assignmentCount"], 0)

    def test_three_uav_three_usv_one_target_returns_real_waypoints(self) -> None:
        request = self._valid_request()

        result = run_capture_once(request)

        self.assertEqual(result.commandId, request.commandId)
        self.assertEqual(result.status, "RUNNING")
        self.assertEqual(len(result.assignments), 6)
        self.assertEqual(
            {assignment.vehicleId for assignment in result.assignments},
            {vehicle.vehicleId for vehicle in request.uavs + request.usvs},
        )
        for assignment in result.assignments:
            self.assertTrue(math.isfinite(assignment.x))
            self.assertTrue(math.isfinite(assignment.y))
            self.assertTrue(math.isfinite(assignment.z))
            self.assertTrue(math.isfinite(assignment.heading))
            self.assertEqual(assignment.detail["coordinateSource"], "GBSFLACSAlgorithm.desired_waypoints")
            self.assertEqual(assignment.detail["assignmentSource"], "GBSFLACSAlgorithm.step")
            if assignment.vehicleId.startswith("uav"):
                self.assertEqual(assignment.role, "TRACK")
            if assignment.vehicleId.startswith("usv"):
                self.assertEqual(assignment.role, "ENCIRCLE")

        module = load_capture_module()
        self.assertEqual(module.UAV_COUNT, 40)
        self.assertEqual(module.USV_COUNT, 40)
        self.assertEqual(module.TARGET_COUNT, 20)

    def test_repeated_three_by_three_calls_restore_legacy_globals(self) -> None:
        first = run_capture_once(self._valid_request("cmd-capture-1"))
        second = run_capture_once(self._valid_request("cmd-capture-2"))
        module = load_capture_module()

        self.assertEqual(first.status, "RUNNING")
        self.assertEqual(second.status, "RUNNING")
        self.assertEqual(len(first.assignments), 6)
        self.assertEqual(len(second.assignments), 6)
        self.assertEqual(module.UAV_COUNT, 40)
        self.assertEqual(module.USV_COUNT, 40)
        self.assertEqual(module.TARGET_COUNT, 20)

    def test_missing_target_position_is_invalid(self) -> None:
        request = self._valid_request()
        request = AlgorithmRequest(
            commandId=request.commandId,
            algorithmType=request.algorithmType,
            targetId=request.targetId,
            targetPosition=None,
            uavs=request.uavs,
            usvs=request.usvs,
            parameters=request.parameters,
        )

        result = run_capture_once(request)

        self.assertEqual(result.status, "INVALID_REQUEST")
        self.assertEqual(result.assignments, [])

    def test_minimum_agents_above_platform_count_is_invalid(self) -> None:
        request = self._valid_request()
        request = AlgorithmRequest(
            commandId=request.commandId,
            algorithmType=request.algorithmType,
            targetId=request.targetId,
            targetPosition=request.targetPosition,
            uavs=request.uavs,
            usvs=request.usvs,
            parameters={"minimumAgents": 7},
        )

        result = run_capture_once(request)

        self.assertEqual(result.status, "INVALID_REQUEST")
        self.assertEqual(result.assignments, [])

    def test_empty_uav_or_usv_is_invalid(self) -> None:
        valid = self._valid_request()
        no_uav = AlgorithmRequest(
            commandId="cmd-no-uav",
            algorithmType=valid.algorithmType,
            targetId=valid.targetId,
            targetPosition=valid.targetPosition,
            uavs=[],
            usvs=valid.usvs,
            parameters=valid.parameters,
        )
        no_usv = AlgorithmRequest(
            commandId="cmd-no-usv",
            algorithmType=valid.algorithmType,
            targetId=valid.targetId,
            targetPosition=valid.targetPosition,
            uavs=valid.uavs,
            usvs=[],
            parameters=valid.parameters,
        )

        self.assertEqual(run_capture_once(no_uav).status, "INVALID_REQUEST")
        self.assertEqual(run_capture_once(no_usv).status, "INVALID_REQUEST")


if __name__ == "__main__":
    unittest.main()
