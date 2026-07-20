from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path


SERVICE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_DIR))

from adapters.escort_adapter import ROLE_MAP, _scene_from_parameters, run_escort_once
from adapters.models import AlgorithmRequest, Position, VehicleState


class EscortAdapterTest(unittest.TestCase):
    def _request(self, threat_direction: str = "front") -> AlgorithmRequest:
        return AlgorithmRequest(
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
            parameters={"escortRadius": 6.0, "threatDirection": threat_direction},
        )

    def _legacy_snapshots(self) -> dict[str, bytes]:
        return {
            path.name: path.read_bytes()
            for path in (SERVICE_DIR / "legacy").glob("*.py")
        }

    def test_runs_one_step_with_three_uavs_and_three_usvs(self) -> None:
        request = self._request()

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

    def test_frontend_threat_directions_map_to_legacy_scenes(self) -> None:
        cases = {
            "FRONT": "front",
            "FRONT_RIGHT": "front_right",
            "RIGHT": "right",
            "BACK_RIGHT": "back_right",
            "BACK": "back",
            "BACK_LEFT": "back_left",
            "LEFT": "left",
            "FRONT_LEFT": "front_left",
        }

        for frontend_value, legacy_scene in cases.items():
            with self.subTest(frontend_value=frontend_value):
                self.assertEqual(_scene_from_parameters({"threatDirection": frontend_value}), legacy_scene)

        self.assertEqual(_scene_from_parameters({"threatDirection": "FRONT_RIGHT"}), "front_right")
        self.assertNotEqual(_scene_from_parameters({"threatDirection": "FRONT_RIGHT"}), "front")
        self.assertEqual(_scene_from_parameters({"threatDirection": "BACK_LEFT"}), "back_left")
        self.assertNotEqual(_scene_from_parameters({"threatDirection": "BACK_LEFT"}), "front")
        self.assertEqual(_scene_from_parameters({"threatDirection": "front-right"}), "front_right")
        self.assertEqual(_scene_from_parameters({"threatDirection": "  FrOnT_LeFt  "}), "front_left")
        self.assertEqual(_scene_from_parameters({"threatDirection": "unknown"}), "front")

    def test_all_frontend_threat_directions_run_and_do_not_modify_legacy_files(self) -> None:
        directions = [
            "FRONT",
            "FRONT_RIGHT",
            "RIGHT",
            "BACK_RIGHT",
            "BACK",
            "BACK_LEFT",
            "LEFT",
            "FRONT_LEFT",
        ]
        before = self._legacy_snapshots()

        for direction in directions:
            with self.subTest(direction=direction):
                request = self._request(direction)
                result = run_escort_once(request)

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

        self.assertEqual(self._legacy_snapshots(), before)


if __name__ == "__main__":
    unittest.main()
