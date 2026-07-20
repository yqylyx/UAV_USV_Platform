from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path


SERVICE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_DIR))

from adapters.escort_adapter import ROLE_MAP, run_escort_once
from adapters.models import AlgorithmRequest, Position, VehicleState


class EscortAdapterTest(unittest.TestCase):
    def test_runs_one_step_with_three_uavs_and_three_usvs(self) -> None:
        request = AlgorithmRequest(
            commandId="cmd-escort-1",
            algorithmType="ESCORT_DEFENSE",
            targetId="escort-target",
            targetPosition=Position(x=0.0, y=0.0, z=0.0),
            threatTargetId="threat-1",
            threatPosition=Position(x=10.0, y=0.0, z=0.0),
            uavs=[
                VehicleState(vehicleId="uav-01", x=-6.0, y=-3.0, z=20.0, heading=0.1),
                VehicleState(vehicleId="uav-02", x=-5.0, y=0.0, z=22.0, heading=0.2),
                VehicleState(vehicleId="uav-03", x=-6.0, y=3.0, z=24.0, heading=0.3),
            ],
            usvs=[
                VehicleState(vehicleId="usv-01", x=-4.0, y=-4.0, z=0.0, heading=0.4),
                VehicleState(vehicleId="usv-02", x=-4.0, y=0.0, z=0.0, heading=0.5),
                VehicleState(vehicleId="usv-03", x=-4.0, y=4.0, z=0.0, heading=0.6),
            ],
            parameters={"escortRadius": 6.0, "threatDirection": "front"},
        )

        result = run_escort_once(request)

        self.assertEqual(result.commandId, request.commandId)
        self.assertEqual(result.status, "RUNNING")
        self.assertEqual(len(result.assignments), 6)
        self.assertEqual(
            {assignment.vehicleId for assignment in result.assignments},
            {vehicle.vehicleId for vehicle in request.uavs + request.usvs},
        )
        legacy_roles = result.metrics["platformRoles"]
        for assignment in result.assignments:
            self.assertTrue(math.isfinite(assignment.x))
            self.assertTrue(math.isfinite(assignment.y))
            self.assertTrue(math.isfinite(assignment.z))
            self.assertIn(assignment.detail["legacyRole"], ROLE_MAP)
            self.assertEqual(assignment.role, ROLE_MAP[legacy_roles[assignment.vehicleId]])
            self.assertIn(assignment.detail["coordinateSource"], {"Platform.goal", "Platform.position"})


if __name__ == "__main__":
    unittest.main()
