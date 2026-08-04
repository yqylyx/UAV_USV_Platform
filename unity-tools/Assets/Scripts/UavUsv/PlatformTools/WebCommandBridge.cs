using System;
using System.Collections;
using System.Runtime.InteropServices;
using UnityEngine;
using UnityEngine.Scripting;

namespace UavUsv.PlatformTools
{
    /// <summary>
    /// Receives Vue postMessage commands through the WebGL page and controls only
    /// presentation-side camera tools. Mission behavior remains owned by the
    /// existing simulation and ROS control layers.
    /// </summary>
    [Preserve]
    public sealed class WebCommandBridge : MonoBehaviour
    {
        [Serializable]
        private sealed class VueMessage
        {
            public string type;
            public string requestId;
            public long timestamp;
            public VuePayload payload;
        }

        [Serializable]
        private sealed class VuePayload
        {
            public string deviceCode;
            public string mode;
            public string command;
            public string action;
            public float value;
            public bool visible;
        }

        [Serializable]
        private sealed class ResponseEnvelope
        {
            public string type;
            public string requestId;
            public long timestamp;
            public ResponsePayload payload;
        }

        [Serializable]
        private sealed class ResponsePayload
        {
            public bool success;
            public string deviceCode;
            public string mode;
            public string profile;
            public string status;
            public string source = "unity-webgl";
            public bool visible;
            public float zoomPercent;
        }

        private WebDeviceObserverCamera observer;
        private WebVehicleCommandController vehicleController;

#if UNITY_WEBGL && !UNITY_EDITOR
        [DllImport("__Internal")]
        private static extern void VueWebGlPostMessage(string message);
#endif

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void Install()
        {
#if UNITY_WEBGL && !UNITY_EDITOR
            GameObject existing = GameObject.Find("WebCommandBridge");
            GameObject host = existing ? existing : new GameObject("WebCommandBridge");
            DontDestroyOnLoad(host);
            WebCommandBridge bridge = host.GetComponent<WebCommandBridge>();
            if (!bridge) bridge = host.AddComponent<WebCommandBridge>();
            WebVehicleCommandController controller = host.GetComponent<WebVehicleCommandController>();
            if (!controller) controller = host.AddComponent<WebVehicleCommandController>();
            WebTrajectoryTelemetryBridge telemetry = host.GetComponent<WebTrajectoryTelemetryBridge>();
            if (!telemetry) telemetry = host.AddComponent<WebTrajectoryTelemetryBridge>();
            telemetry.Initialize(controller);
            bridge.vehicleController = controller;
#endif
        }

        private IEnumerator Start()
        {
            while (!EnsureObserver())
                yield return null;
        }

        [Preserve]
        public static void PublishCameraInteraction(float zoomPercent)
        {
            var response = new ResponseEnvelope
            {
                type = "cameraInteraction",
                requestId = string.Empty,
                timestamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
                payload = new ResponsePayload
                {
                    success = true,
                    status = "wheel-zoom",
                    zoomPercent = zoomPercent
                }
            };
            Emit(JsonUtility.ToJson(response));
        }

        [Preserve]
        public void ReceiveFromVue(string json)
        {
            VueMessage message;
            try
            {
                message = JsonUtility.FromJson<VueMessage>(json);
            }
            catch (Exception exception)
            {
                PostCameraResult(string.Empty, false, string.Empty, string.Empty, string.Empty, "Invalid Vue message: " + exception.Message);
                return;
            }

            if (message == null || string.IsNullOrWhiteSpace(message.type))
            {
                PostCameraResult(string.Empty, false, string.Empty, string.Empty, string.Empty, "Vue message type is empty");
                return;
            }

            if (!EnsureObserver())
            {
                PostCameraResult(message.requestId, false, string.Empty, string.Empty, string.Empty, "Unity camera is not ready");
                return;
            }

            string type = message.type.Trim().ToLowerInvariant();
            VuePayload payload = message.payload ?? new VuePayload();
            switch (type)
            {
                case "selectdevice":
                    SelectDevice(message.requestId, payload.deviceCode);
                    break;
                case "focusdevice":
                    FocusDevice(message.requestId, payload.deviceCode);
                    break;
                case "switchcamera":
                    SwitchCamera(message.requestId, payload.mode, payload.deviceCode);
                    break;
                case "sendcontrolcommand":
                    ExecuteVehicleCommand(message.requestId, payload.deviceCode, payload.command);
                    break;
                case "toggletrajectory":
                    SetTrajectoryVisibility(message.requestId, payload.visible);
                    break;
                case "cameracontrol":
                    ControlCamera(message.requestId, payload.action, payload.value);
                    break;
            }
        }

        private void ControlCamera(string requestId, string rawAction, float value)
        {
            string action = (rawAction ?? string.Empty).Trim().ToLowerInvariant();
            bool success = true;
            string status;
            switch (action)
            {
                case "fitall":
                case "reset":
                    observer.FitAll();
                    status = "Global view fitted to the complete fleet";
                    break;
                case "zoomdelta":
                    observer.AdjustZoom(value);
                    status = "Camera zoom adjusted";
                    break;
                case "setzoom":
                    observer.SetZoomPercent(value);
                    status = "Camera zoom set";
                    break;
                default:
                    success = false;
                    status = "Unknown camera action: " + rawAction;
                    break;
            }

            var response = new ResponseEnvelope
            {
                type = "cameraAdjusted",
                requestId = requestId ?? string.Empty,
                timestamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
                payload = new ResponsePayload
                {
                    success = success,
                    deviceCode = observer.CurrentDeviceCode,
                    mode = observer.CurrentModeName,
                    profile = observer.CurrentProfileName,
                    status = status,
                    zoomPercent = observer.ZoomPercent
                }
            };
            Emit(JsonUtility.ToJson(response));
        }

        private bool EnsureObserver()
        {
            if (observer)
                return true;
            Camera camera = Camera.main;
            if (!camera)
                return false;
            UavUsv.ChaseCamera chase = camera.GetComponent<UavUsv.ChaseCamera>();
            if (!chase)
                return false;
            observer = camera.GetComponent<WebDeviceObserverCamera>();
            if (!observer)
                observer = camera.gameObject.AddComponent<WebDeviceObserverCamera>();
            observer.Initialize(camera, chase);
            return true;
        }

        private bool EnsureVehicleController()
        {
            if (!vehicleController)
                vehicleController = GetComponent<WebVehicleCommandController>();
            if (!vehicleController)
                vehicleController = gameObject.AddComponent<WebVehicleCommandController>();
            WebTrajectoryTelemetryBridge telemetry = GetComponent<WebTrajectoryTelemetryBridge>();
            if (!telemetry)
                telemetry = gameObject.AddComponent<WebTrajectoryTelemetryBridge>();
            telemetry.Initialize(vehicleController);
            return vehicleController && vehicleController.EnsureScenario();
        }

        private void SelectDevice(string requestId, string requestedCode)
        {
            bool success = observer.TrySelectDevice(
                requestedCode,
                out string code,
                out string profile,
                out string error
            );
            PostCameraResult(
                requestId,
                success,
                code,
                success ? observer.CurrentModeName : "device-follow",
                profile,
                success ? "Camera following " + code : error
            );
        }

        private void FocusDevice(string requestId, string requestedCode)
        {
            if (!string.IsNullOrWhiteSpace(requestedCode))
            {
                SelectDevice(requestId, requestedCode);
                return;
            }

            bool success = observer.RecenterCurrentDevice(out string error);
            PostCameraResult(
                requestId,
                success,
                observer.CurrentDeviceCode,
                observer.CurrentModeName,
                observer.CurrentProfileName,
                success ? "Camera recentered" : error
            );
        }

        private void SwitchCamera(string requestId, string requestedMode, string requestedDeviceCode)
        {
            string mode = string.IsNullOrWhiteSpace(requestedMode)
                ? "overview"
                : requestedMode.Trim().ToLowerInvariant();
            if (mode == "overview")
            {
                observer.SetOverview();
                PostCameraResult(requestId, true, string.Empty, "overview", "overview", "Global overview active");
                return;
            }
            if (mode == "lighthouse")
            {
                observer.SetLighthouse();
                PostCameraResult(requestId, true, string.Empty, "lighthouse", "lighthouse", "Lighthouse view active");
                return;
            }
            if (mode == "action")
            {
                observer.ReleaseToOriginalCamera();
                PostCameraResult(requestId, true, string.Empty, "action", "action", "Original action camera restored");
                return;
            }
            if (mode == "comparison" || mode == "gazebo-comparison")
            {
                observer.SetGazeboComparison();
                PostCameraResult(requestId, true, string.Empty, "comparison", "gazebo-comparison", "Gazebo comparison view active");
                return;
            }
            if (mode == "device-follow")
            {
                bool success;
                string error;
                if (!string.IsNullOrWhiteSpace(requestedDeviceCode))
                {
                    success = observer.TrySelectDevice(
                        requestedDeviceCode,
                        out _,
                        out _,
                        out error
                    );
                }
                else
                {
                    success = observer.RecenterCurrentDevice(out error);
                }
                PostCameraResult(
                    requestId,
                    success,
                    observer.CurrentDeviceCode,
                    mode,
                    observer.CurrentProfileName,
                    success ? "Device view active" : error
                );
                return;
            }
            if (mode == "follow-usv" || mode == "follow-uav")
            {
                bool success = observer.TrySelectFirst(
                    mode == "follow-uav" ? "UAV" : "USV",
                    out string code,
                    out string profile,
                    out string error
                );
                PostCameraResult(requestId, success, code, "device-follow", profile, success ? "Camera following " + code : error);
                return;
            }

            PostCameraResult(requestId, false, observer.CurrentDeviceCode, mode, string.Empty, "Unknown camera mode: " + requestedMode);
        }

        private void PostCameraResult(
            string requestId,
            bool success,
            string deviceCode,
            string mode,
            string profile,
            string status)
        {
            var response = new ResponseEnvelope
            {
                type = "cameraChanged",
                requestId = requestId ?? string.Empty,
                timestamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
                payload = new ResponsePayload
                {
                    success = success,
                    deviceCode = deviceCode ?? string.Empty,
                    mode = mode ?? string.Empty,
                    profile = profile ?? string.Empty,
                    status = status ?? string.Empty
                }
            };
            Emit(JsonUtility.ToJson(response));
        }

        private void ExecuteVehicleCommand(string requestId, string deviceCode, string command)
        {
            string state = "ERROR";
            string detail = "Unity vehicle controller is not ready";
            bool success = EnsureVehicleController() &&
                vehicleController.TryExecute(command, deviceCode, out state, out detail);
            var response = new ResponseEnvelope
            {
                type = "commandAck",
                requestId = requestId ?? string.Empty,
                timestamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
                payload = new ResponsePayload
                {
                    success = success,
                    deviceCode = deviceCode ?? string.Empty,
                    mode = observer ? observer.CurrentModeName : string.Empty,
                    profile = observer ? observer.CurrentProfileName : string.Empty,
                    status = success ? state + ": " + detail : detail
                }
            };
            Emit(JsonUtility.ToJson(response));
        }

        private void SetTrajectoryVisibility(string requestId, bool visible)
        {
            UavUsv.MultiAgentCaptureDefenseScenario scenario =
                FindObjectOfType<UavUsv.MultiAgentCaptureDefenseScenario>(true);
            bool success = scenario;
            if (scenario)
                scenario.showDebugOverlays = visible;

            var response = new ResponseEnvelope
            {
                type = "trajectoryVisibilityChanged",
                requestId = requestId ?? string.Empty,
                timestamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
                payload = new ResponsePayload
                {
                    success = success,
                    deviceCode = observer ? observer.CurrentDeviceCode : string.Empty,
                    mode = observer ? observer.CurrentModeName : string.Empty,
                    profile = observer ? observer.CurrentProfileName : string.Empty,
                    visible = visible,
                    status = success
                        ? (visible ? "Trajectory overlays visible" : "Trajectory overlays hidden")
                        : "Unity scenario is not ready"
                }
            };
            Emit(JsonUtility.ToJson(response));
        }

        private static void Emit(string json)
        {
#if UNITY_WEBGL && !UNITY_EDITOR
            VueWebGlPostMessage(json);
#else
            Debug.Log("[WebCommandBridge] " + json);
#endif
        }
    }
}
