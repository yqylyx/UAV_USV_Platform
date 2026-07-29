using System;
using System.Collections;
using System.Runtime.InteropServices;
using UnityEngine;
using UnityEngine.Scripting;

namespace UavUsv.PlatformTools
{
    /// <summary>
    /// Additive compatibility layer between the Vue platform and the current
    /// Unity scene. It coordinates presentation cameras only; simulation,
    /// mission and terrain source files remain untouched.
    /// </summary>
    [Preserve]
    [DefaultExecutionOrder(9000)]
    public sealed class UnityPlatformCompatibilityBridge : MonoBehaviour
    {
        [Serializable]
        private sealed class Envelope
        {
            public string type;
            public Payload payload;
        }

        [Serializable]
        private sealed class Payload
        {
            public string mode;
            public string algorithmCode;
        }

        [Serializable]
        private sealed class ReadyPayload
        {
            public bool ready;
            public bool controlsReady;
            public bool cameraReady;
            public bool algorithmReady;
            public bool visualSensorReady;
            public int deviceCount;
            public string buildId;
            public string[] capabilities;
        }

        [Serializable]
        private sealed class BridgeEnvelope<T>
        {
            public string type;
            public string requestId = "";
            public long timestamp;
            public T payload;
        }

        public const string BuildId = "unity-f24959c-platform-v3";

#if UNITY_WEBGL && !UNITY_EDITOR
        [DllImport("__Internal")]
        private static extern void VueWebGlPostMessage(string message);
#endif

        private UavUsv.GazeboComparisonCamera comparisonCamera;
        private bool readyPosted;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void Install()
        {
            GameObject existing = GameObject.Find("UnityPlatformCompatibilityBridge");
            GameObject host = existing
                ? existing
                : new GameObject("UnityPlatformCompatibilityBridge");
            DontDestroyOnLoad(host);
            if (!host.GetComponent<UnityPlatformCompatibilityBridge>())
                host.AddComponent<UnityPlatformCompatibilityBridge>();
        }

        private IEnumerator Start()
        {
            // Runtime installers all use AfterSceneLoad. Waiting a few frames
            // makes the capability report authoritative instead of optimistic.
            for (int frame = 0; frame < 120 && !DependenciesReady(); frame++)
                yield return null;
            PostReady();
        }

        [Preserve]
        public void ReceiveFromVue(string json)
        {
            if (string.IsNullOrWhiteSpace(json))
                return;

            Envelope message;
            try
            {
                message = JsonUtility.FromJson<Envelope>(json);
            }
            catch (Exception exception)
            {
                Debug.LogWarning("[UnityPlatformCompatibilityBridge] Invalid message: " + exception.Message);
                return;
            }

            if (message == null || string.IsNullOrWhiteSpace(message.type))
                return;

            string type = message.type.Trim().ToLowerInvariant();
            string mode = message.payload != null
                ? (message.payload.mode ?? string.Empty).Trim().ToLowerInvariant()
                : string.Empty;

            if (type == "switchcamera" &&
                (mode == "comparison" || mode == "gazebo-comparison"))
            {
                SetComparisonActive(true);
                return;
            }

            if (type == "selectdevice" ||
                type == "focusdevice" ||
                type == "switchcamera" ||
                type == "loadscenario" ||
                type == "poseframe")
            {
                SetComparisonActive(false);
            }
        }

        public void SetComparisonActive(bool active)
        {
            if (!comparisonCamera && Camera.main)
                comparisonCamera = Camera.main.GetComponent<UavUsv.GazeboComparisonCamera>();
            if (comparisonCamera)
                comparisonCamera.comparisonActive = active;
        }

        private bool DependenciesReady()
        {
            if (!Camera.main)
                return false;
            if (!comparisonCamera)
                comparisonCamera = Camera.main.GetComponent<UavUsv.GazeboComparisonCamera>();
            UavUsv.SensorViewPip sensorView =
                FindObjectOfType<UavUsv.SensorViewPip>(true);
            if (sensorView)
            {
                sensorView.visible = false;
                sensorView.enabled = false;
            }
            UnityScenarioCompatibilityInstaller scenarioInstaller =
                FindObjectOfType<UnityScenarioCompatibilityInstaller>(true);
            return FindObjectOfType<WebCommandBridge>(true) &&
                   FindObjectOfType<AlgorithmScenarioBridge>(true) &&
                   FindObjectOfType<UnityVisualSensorBridge>(true) &&
                   scenarioInstaller &&
                   scenarioInstaller.Ready &&
                   sensorView;
        }

        private void PostReady()
        {
            if (readyPosted)
                return;
            readyPosted = true;
            bool controlsReady = FindObjectOfType<WebCommandBridge>(true);
            bool cameraReady = Camera.main &&
                               Camera.main.GetComponent<UavUsv.ChaseCamera>();
            bool algorithmReady = FindObjectOfType<AlgorithmScenarioBridge>(true);
            bool visualReady = FindObjectOfType<UnityVisualSensorBridge>(true);
            Post("platformBridgeReady", new ReadyPayload
            {
                ready = controlsReady && cameraReady && algorithmReady && visualReady,
                controlsReady = controlsReady,
                cameraReady = cameraReady,
                algorithmReady = algorithmReady,
                visualSensorReady = visualReady,
                deviceCount = 6,
                buildId = BuildId,
                capabilities = new[]
                {
                    "camera-control",
                    "vehicle-control",
                    "trajectory-telemetry",
                    "local-capture-scenario",
                    "algorithm-scenario",
                    "visual-sensor",
                    "gpu-visual-sensor",
                    "visual-720p",
                    "visual-1080p",
                    "gazebo-comparison"
                }
            });
        }

        private static void Post<T>(string type, T payload)
        {
            var envelope = new BridgeEnvelope<T>
            {
                type = type,
                timestamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
                payload = payload
            };
            string json = JsonUtility.ToJson(envelope);
#if UNITY_WEBGL && !UNITY_EDITOR
            VueWebGlPostMessage(json);
#else
            Debug.Log("[UnityPlatformCompatibilityBridge] " + json);
#endif
        }
    }
}
