from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path


SERVICE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_DIR))

try:
    from fastapi.testclient import TestClient

    from app import app
except ModuleNotFoundError as exc:
    TestClient = None
    app = None
    FASTAPI_IMPORT_ERROR = exc
else:
    FASTAPI_IMPORT_ERROR = None


@unittest.skipIf(FASTAPI_IMPORT_ERROR is not None, "FastAPI/TestClient dependency is not installed")
class AlgorithmApiTest(unittest.TestCase):
    def setUp(self) -> None:
        assert TestClient is not None
        assert app is not None
        self.client = TestClient(app)

    def _capture_payload(self) -> dict:
        return {
            "algorithmType": "CAPTURE",
            "targetId": "target_01",
            "targetPosition": {"x": 50.0, "y": 50.0, "z": 0.0},
            "uavs": [
                {"vehicleId": "uav_01", "position": {"x": 0.0, "y": 0.0, "z": 20.0}},
                {"vehicleId": "uav_02", "position": {"x": 10.0, "y": 0.0, "z": 20.0}},
                {"vehicleId": "uav_03", "position": {"x": 20.0, "y": 0.0, "z": 20.0}},
            ],
            "usvs": [
                {"vehicleId": "usv_01", "position": {"x": 0.0, "y": 10.0, "z": 0.0}},
                {"vehicleId": "usv_02", "position": {"x": 10.0, "y": 10.0, "z": 0.0}},
                {"vehicleId": "usv_03", "position": {"x": 20.0, "y": 10.0, "z": 0.0}},
            ],
            "parameters": {"minimumAgents": 3},
        }

    def _escort_payload(self) -> dict:
        return {
            "algorithmType": "ESCORT_DEFENSE",
            "targetId": "escort_target",
            "targetPosition": {"x": 0.0, "y": 0.0, "z": 0.0},
            "threatTargetId": "threat_01",
            "threatPosition": {"x": 10.0, "y": 0.0, "z": 0.0},
            "uavs": [
                {"vehicleId": "uav_01", "position": {"x": -6.0, "y": -3.0, "z": 20.0}},
                {"vehicleId": "uav_02", "position": {"x": -5.0, "y": 0.0, "z": 22.0}},
                {"vehicleId": "uav_03", "position": {"x": -6.0, "y": 3.0, "z": 24.0}},
            ],
            "usvs": [
                {"vehicleId": "usv_01", "position": {"x": -4.0, "y": -4.0, "z": 0.0}},
                {"vehicleId": "usv_02", "position": {"x": -4.0, "y": 0.0, "z": 0.0}},
                {"vehicleId": "usv_03", "position": {"x": -4.0, "y": 4.0, "z": 0.0}},
            ],
            "parameters": {"escortRadius": 6.0, "threatDirection": "FRONT_RIGHT"},
        }

    def test_health_returns_ok(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_capture_valid_request_returns_vehicle_ids_and_waypoints(self) -> None:
        payload = self._capture_payload()

        response = self.client.post("/api/v1/algorithms/run-once", json=payload)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "RUNNING")
        self.assertEqual(
            {assignment["vehicleId"] for assignment in body["assignments"]},
            {vehicle["vehicleId"] for vehicle in payload["uavs"] + payload["usvs"]},
        )
        for assignment in body["assignments"]:
            self.assertTrue(math.isfinite(assignment["x"]))
            self.assertTrue(math.isfinite(assignment["y"]))
            self.assertTrue(math.isfinite(assignment["z"]))
            self.assertEqual(assignment["detail"]["coordinateSource"], "GBSFLACSAlgorithm.desired_waypoints")
            self.assertEqual(assignment["detail"]["assignmentSource"], "GBSFLACSAlgorithm.step")

    def test_escort_valid_request_returns_vehicle_ids(self) -> None:
        payload = self._escort_payload()

        response = self.client.post("/api/v1/algorithms/run-once", json=payload)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "RUNNING")
        self.assertEqual(len(body["assignments"]), 6)
        self.assertEqual(
            {assignment["vehicleId"] for assignment in body["assignments"]},
            {vehicle["vehicleId"] for vehicle in payload["uavs"] + payload["usvs"]},
        )

    def test_invalid_algorithm_type_returns_4xx(self) -> None:
        payload = self._capture_payload()
        payload["algorithmType"] = "UNKNOWN"

        response = self.client.post("/api/v1/algorithms/run-once", json=payload)

        self.assertTrue(400 <= response.status_code < 500)

    def test_capture_missing_target_position_returns_4xx(self) -> None:
        payload = self._capture_payload()
        payload.pop("targetPosition")

        response = self.client.post("/api/v1/algorithms/run-once", json=payload)

        self.assertTrue(400 <= response.status_code < 500)

    def test_empty_uav_or_usv_returns_4xx(self) -> None:
        for field in ("uavs", "usvs"):
            with self.subTest(field=field):
                payload = self._capture_payload()
                payload[field] = []

                response = self.client.post("/api/v1/algorithms/run-once", json=payload)

                self.assertTrue(400 <= response.status_code < 500)

    def test_empty_vehicle_id_returns_4xx(self) -> None:
        payload = self._capture_payload()
        payload["uavs"][0]["vehicleId"] = " "

        response = self.client.post("/api/v1/algorithms/run-once", json=payload)

        self.assertTrue(400 <= response.status_code < 500)

    def test_nan_or_infinity_coordinate_returns_4xx(self) -> None:
        for raw_body in (
            '{"algorithmType":"CAPTURE","targetId":"target_01","targetPosition":{"x":NaN,"y":0,"z":0},"uavs":[{"vehicleId":"uav_01","position":{"x":0,"y":0,"z":20}}],"usvs":[{"vehicleId":"usv_01","position":{"x":10,"y":0,"z":0}}]}',
            '{"algorithmType":"CAPTURE","targetId":"target_01","targetPosition":{"x":0,"y":0,"z":0},"uavs":[{"vehicleId":"uav_01","position":{"x":Infinity,"y":0,"z":20}}],"usvs":[{"vehicleId":"usv_01","position":{"x":10,"y":0,"z":0}}]}',
        ):
            with self.subTest(raw_body=raw_body):
                response = self.client.post(
                    "/api/v1/algorithms/run-once",
                    data=raw_body,
                    headers={"content-type": "application/json"},
                )

                self.assertTrue(400 <= response.status_code < 500)

    def test_run_once_does_not_call_visual_entry_points(self) -> None:
        from adapters.capture_adapter import load_capture_module
        from adapters.escort_adapter import load_escort_module

        capture_module = load_capture_module()
        escort_module = load_escort_module()

        def forbidden(*args, **kwargs):
            raise AssertionError("visual entry point must not be called")

        original_main2 = capture_module.main2
        original_load_image = capture_module.load_image
        original_compare = capture_module.create_performance_comparison
        original_capture_show = capture_module.plt.show
        original_escort_show = escort_module.EscortGuardVisualizer.show
        original_escort_main = escort_module.main
        try:
            capture_module.main2 = forbidden
            capture_module.load_image = forbidden
            capture_module.create_performance_comparison = forbidden
            capture_module.plt.show = forbidden
            escort_module.EscortGuardVisualizer.show = forbidden
            escort_module.main = forbidden

            capture_response = self.client.post("/api/v1/algorithms/run-once", json=self._capture_payload())
            escort_response = self.client.post("/api/v1/algorithms/run-once", json=self._escort_payload())

            self.assertEqual(capture_response.status_code, 200)
            self.assertEqual(escort_response.status_code, 200)
        finally:
            capture_module.main2 = original_main2
            capture_module.load_image = original_load_image
            capture_module.create_performance_comparison = original_compare
            capture_module.plt.show = original_capture_show
            escort_module.EscortGuardVisualizer.show = original_escort_show
            escort_module.main = original_escort_main


if __name__ == "__main__":
    unittest.main()
