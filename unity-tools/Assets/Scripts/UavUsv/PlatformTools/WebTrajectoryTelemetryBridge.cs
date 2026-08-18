using System;
using System.Runtime.InteropServices;
using UnityEngine;
using UnityEngine.Scripting;

namespace UavUsv.PlatformTools
{
    [Preserve]
    public sealed class WebTrajectoryTelemetryBridge : MonoBehaviour
    {
        [Serializable] private sealed class Envelope { public string type = "trajectoryFrame"; public long timestamp; public FramePayload payload; }
        [Serializable] private sealed class FramePayload
        {
            public long sequence;
            public string source = "unity-webgl";
            public string coordinateSystem = "UNITY_XZ";
            public MissionPayload mission;
            public AgentPayload[] agents;
        }
        [Serializable] private sealed class MissionPayload
        {
            public string phase;
            public float elapsed;
            public float captureRadius;
            public float defenseRadius;
            public bool captureReady;
            public bool formationHolding;
        }
        [Serializable] private sealed class AgentPayload
        {
            public string code;
            public string type;
            public float x;
            public float y;
            public float z;
            public float yaw;
            public string state;
        }

#if UNITY_WEBGL && !UNITY_EDITOR
        [DllImport("__Internal")]
        private static extern void VueWebGlPostMessage(string message);
#endif

        private MultiAgentCaptureDefenseScenario scenario;
        private WebVehicleCommandController controller;
        private AlgorithmScenarioBridge algorithmBridge;
        private float nextPublishAt;
        private long sequence;

        public void Initialize(WebVehicleCommandController commandController)
        {
            controller = commandController;
        }

        private void Update()
        {
            if (Time.unscaledTime < nextPublishAt) return;
            nextPublishAt = Time.unscaledTime + .2f;
            if (!algorithmBridge)
                algorithmBridge = FindObjectOfType<AlgorithmScenarioBridge>(true);
            if (algorithmBridge && algorithmBridge.IsExternalMode)
                return;
            if (!scenario) scenario = FindObjectOfType<MultiAgentCaptureDefenseScenario>();
            if (!scenario || !scenario.targetPoint) return;
            if (!controller) controller = GetComponent<WebVehicleCommandController>();
            EmitFrame();
        }

        private void EmitFrame()
        {
            int boatCount = scenario.boats != null ? scenario.boats.Length : 0;
            int droneCount = scenario.drones != null ? scenario.drones.Length : 0;
            AgentPayload[] agents = new AgentPayload[boatCount + droneCount + 1];
            int cursor = 0;
            for (int i = 0; i < boatCount; i++)
                agents[cursor++] = BuildAgent(scenario.boats[i], "usv-" + (i + 1).ToString("00"), "USV", false);
            for (int i = 0; i < droneCount; i++)
                agents[cursor++] = BuildAgent(scenario.drones[i], "uav-" + (i + 1).ToString("00"), "UAV", true);
            agents[cursor] = BuildAgent(scenario.targetPoint, "target", "TARGET", false);

            var envelope = new Envelope
            {
                timestamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
                payload = new FramePayload
                {
                    sequence = ++sequence,
                    mission = new MissionPayload
                    {
                        phase = scenario.Status,
                        elapsed = scenario.MissionElapsed,
                        captureRadius = scenario.captureRadius,
                        defenseRadius = scenario.defenseRadius,
                        captureReady = scenario.CaptureReady,
                        formationHolding = scenario.FormationHolding
                    },
                    agents = agents
                }
            };
            Emit(JsonUtility.ToJson(envelope));
        }

        private AgentPayload BuildAgent(Transform subject, string code, string type, bool isUav)
        {
            Vector3 position = subject ? subject.position : Vector3.zero;
            return new AgentPayload
            {
                code = code,
                type = type,
                x = position.x,
                y = position.y,
                z = position.z,
                yaw = subject ? subject.eulerAngles.y : 0f,
                state = type == "TARGET" ? "ACTIVE" : (controller ? controller.StateFor(subject, isUav) : "UNKNOWN")
            };
        }

        private static void Emit(string json)
        {
#if UNITY_WEBGL && !UNITY_EDITOR
            VueWebGlPostMessage(json);
#else
            Debug.Log("[WebTrajectoryTelemetryBridge] " + json);
#endif
        }
    }
}
