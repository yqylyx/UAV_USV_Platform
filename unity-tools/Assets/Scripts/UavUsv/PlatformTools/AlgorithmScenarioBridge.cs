using System;
using System.Collections.Generic;
using System.Reflection;
using UnityEngine;
using UnityEngine.Scripting;

namespace UavUsv.PlatformTools
{
    /// <summary>
    /// Optional WebGL visualization adapter for external task-center algorithms.
    /// It does not change the built-in capture simulation. When an external
    /// algorithm is selected, this tool renders the authoritative algorithm
    /// frame onto the existing 3 UAV + 3 USV scene.
    /// </summary>
    [Preserve]
    [DefaultExecutionOrder(11000)]
    public sealed class AlgorithmScenarioBridge : MonoBehaviour
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
            public string algorithmCode;
            public long runId;
            public long sequence;
            public long timestamp;
            public string phase;
            public string command;
            public AgentPose[] agents;
            public TargetPose[] targets;
            public Vector2[] route;
        }

        [Serializable]
        private sealed class AgentPose
        {
            public string code;
            public string type;
            public float x;
            public float y;
            public float z;
            public float heading;
        }

        [Serializable]
        private sealed class TargetPose
        {
            public string code;
            public string type;
            public float x;
            public float y;
            public float z;
            public float heading;
            public bool visible = true;
        }

        private sealed class PoseSnapshot
        {
            public long timestamp;
            public Vector3 position;
            public Quaternion rotation;
        }

        private sealed class PoseTarget
        {
            public Transform subject;
            public readonly List<PoseSnapshot> snapshots = new List<PoseSnapshot>();
        }

        private readonly Dictionary<string, PoseTarget> poseTargets =
            new Dictionary<string, PoseTarget>(StringComparer.OrdinalIgnoreCase);

        private MultiAgentCaptureDefenseScenario scenario;
        private Transform escortTarget;
        private LineRenderer routeRenderer;
        private long lastSequence;
        private string algorithmCode = string.Empty;
        private string phase = string.Empty;
        private bool externalMode;
        private bool playbackFrozen;
        private long latestSourceTimestamp;
        private double latestFrameArrival;
        private readonly Dictionary<GameObject, bool> cleanPresentationStates = new Dictionary<GameObject, bool>();
        private const double InterpolationDelayMs = 180.0;
        private GUIStyle escortLabelStyle;
        private GUIStyle threatLabelStyle;
        private Camera missionCamera;
        private bool cameraStateCaptured;
        private Vector3 originalCameraPosition;
        private Quaternion originalCameraRotation;
        private float originalCameraFieldOfView;
        private float originalCameraOrthographicSize;
        private Vector3 externalOrigin;
        public bool IsExternalMode => externalMode;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void Install()
        {
            GameObject existing = GameObject.Find("AlgorithmScenarioBridge");
            GameObject host = existing ? existing : new GameObject("AlgorithmScenarioBridge");
            DontDestroyOnLoad(host);
            if (!host.GetComponent<AlgorithmScenarioBridge>())
                host.AddComponent<AlgorithmScenarioBridge>();
        }

        [Preserve]
        public void ReceiveFromVue(string json)
        {
            if (string.IsNullOrWhiteSpace(json)) return;
            Envelope message;
            try { message = JsonUtility.FromJson<Envelope>(json); }
            catch (Exception exception)
            {
                Debug.LogWarning("[AlgorithmScenarioBridge] Invalid message: " + exception.Message);
                return;
            }

            if (message == null || string.IsNullOrWhiteSpace(message.type)) return;
            Payload payload = message.payload ?? new Payload();
            switch (message.type.Trim().ToLowerInvariant())
            {
                case "loadscenario":
                    LoadScenario(payload.algorithmCode);
                    break;
                case "poseframe":
                    ApplyFrame(payload);
                    break;
                case "sendcontrolcommand":
                    ApplyControl(payload.command);
                    break;
            }
        }

        private void LoadScenario(string requestedAlgorithm)
        {
            EnsureScenario();
            algorithmCode = (requestedAlgorithm ?? string.Empty).Trim().ToUpperInvariant();
            externalMode = algorithmCode == "GB_SFLA_CS" || algorithmCode == "ESCORT_GUARD";
            externalOrigin = ResolveExternalOrigin();
            SetComparisonActive(!externalMode);
            lastSequence = 0;
            latestSourceTimestamp = 0;
            latestFrameArrival = Time.realtimeSinceStartupAsDouble;
            playbackFrozen = false;
            poseTargets.Clear();
            EnsureEscortTarget();

            if (scenario)
            {
                SetScenarioAutomatic(false);
                scenario.enabled = !externalMode;
                SetFleetExternal(externalMode);
                SetCleanTaskPresentation(externalMode);
            }
            if (externalMode) CaptureCameraState();
            else RestoreCameraState();
            // A target becomes visible only after an authoritative algorithm
            // frame identifies it.  Loading a capture run must not leave an
            // extra escort vessel in the scene.
            if (escortTarget) escortTarget.gameObject.SetActive(false);
            if (routeRenderer) routeRenderer.enabled = false;
        }

        private void ApplyControl(string rawCommand)
        {
            if (!externalMode || !EnsureScenario()) return;
            string command = (rawCommand ?? string.Empty).Trim().ToLowerInvariant();
            if (command == "missionstart" || command == "missionresume")
            {
                playbackFrozen = false;
                SetScenarioAutomatic(false);
                scenario.enabled = false;
                SetFleetExternal(true);
            }
            else if (command == "missionpause" || command == "missioncomplete" ||
                     command == "missioncancel" || command == "missionfail")
            {
                playbackFrozen = true;
                foreach (PoseTarget target in poseTargets.Values)
                    target.snapshots.Clear();
            }
        }

        private void ApplyFrame(Payload payload)
        {
            if (payload == null) return;
            string incomingAlgorithm = (payload.algorithmCode ?? algorithmCode).Trim().ToUpperInvariant();
            if (!externalMode || !string.Equals(algorithmCode, incomingAlgorithm, StringComparison.OrdinalIgnoreCase))
                LoadScenario(incomingAlgorithm);
            if (!externalMode || payload.sequence <= lastSequence || !EnsureScenario()) return;

            lastSequence = payload.sequence;
            if (payload.timestamp > 0)
            {
                latestSourceTimestamp = payload.timestamp;
                latestFrameArrival = Time.realtimeSinceStartupAsDouble;
            }
            phase = payload.phase ?? string.Empty;
            SetScenarioAutomatic(false);
            scenario.enabled = false;
            SetFleetExternal(true);
            SetCleanTaskPresentation(true);
            if (playbackFrozen) return;

            if (payload.agents != null)
                foreach (AgentPose item in payload.agents)
                    RegisterAgentPose(item, payload.timestamp);

            bool escortSeen = false;
            bool threatSeen = false;
            if (payload.targets != null)
            {
                foreach (TargetPose item in payload.targets)
                {
                    if (item == null) continue;
                    string kind = (item.type ?? item.code ?? string.Empty).ToUpperInvariant();
                    if (kind == "ESCORT_TARGET") escortSeen = RegisterTargetPose(item, escortTarget, payload.timestamp);
                    else if (kind == "CAPTURE_TARGET" || kind == "THREAT_TARGET" || kind == "TARGET")
                        threatSeen = RegisterTargetPose(item, scenario.targetVessel, payload.timestamp);
                }
            }

            EnsureEscortTarget();
            if (escortTarget) escortTarget.gameObject.SetActive(escortSeen);
            if (scenario.targetVessel) scenario.targetVessel.gameObject.SetActive(threatSeen);
            RenderRoute(payload.route);
        }

        private void RegisterAgentPose(AgentPose item, long timestamp)
        {
            if (item == null || string.IsNullOrWhiteSpace(item.code)) return;
            string code = NormalizeCode(item.code);
            bool isUav = code.StartsWith("UAV-", StringComparison.OrdinalIgnoreCase);
            bool isUsv = code.StartsWith("USV-", StringComparison.OrdinalIgnoreCase);
            if (!isUav && !isUsv) return;
            if (!int.TryParse(code.Substring(4), out int ordinal)) return;
            Transform[] fleet = isUav ? scenario.drones : scenario.boats;
            int index = ordinal - 1;
            if (fleet == null || index < 0 || index >= fleet.Length || !fleet[index]) return;
            RegisterPose(code, fleet[index], item.x, item.y, item.z, item.heading, isUav, timestamp);
        }

        private bool RegisterTargetPose(TargetPose item, Transform subject, long timestamp)
        {
            if (!item.visible || !subject) return false;
            RegisterPose(item.code ?? item.type, subject, item.x, item.y, item.z, item.heading, false, timestamp);
            return true;
        }

        private void RegisterPose(string code, Transform subject, float x, float y, float z, float heading, bool isUav, long timestamp)
        {
            if (!subject) return;
            Vector3 world = externalOrigin +
                            new Vector3(x, isUav ? Mathf.Max(2f, z) : .42f, y);
            string key = code ?? subject.name;
            if (!poseTargets.TryGetValue(key, out PoseTarget target))
            {
                target = new PoseTarget { subject = subject };
                poseTargets[key] = target;
                subject.position = world;
                subject.rotation = Quaternion.Euler(0f, 90f - heading, 0f);
            }
            PoseSnapshot snapshot = new PoseSnapshot
            {
                timestamp = timestamp > 0 ? timestamp : DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
                position = world,
                rotation = Quaternion.Euler(0f, 90f - heading, 0f)
            };
            if (target.snapshots.Count > 0 && snapshot.timestamp <= target.snapshots[target.snapshots.Count - 1].timestamp)
                return;
            if (Vector3.Distance(subject.position, world) > 45f)
            {
                target.snapshots.Clear();
                subject.position = world;
                subject.rotation = snapshot.rotation;
            }
            target.snapshots.Add(snapshot);
            while (target.snapshots.Count > 24) target.snapshots.RemoveAt(0);
        }

        private void LateUpdate()
        {
            if (!externalMode || playbackFrozen || poseTargets.Count == 0) return;
            double renderTimestamp = latestSourceTimestamp > 0
                ? latestSourceTimestamp + (Time.realtimeSinceStartupAsDouble - latestFrameArrival) * 1000.0 - InterpolationDelayMs
                : DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() - InterpolationDelayMs;
            foreach (PoseTarget target in poseTargets.Values)
            {
                if (!target.subject || target.snapshots.Count == 0) continue;
                while (target.snapshots.Count >= 3 && target.snapshots[1].timestamp <= renderTimestamp)
                    target.snapshots.RemoveAt(0);
                if (target.snapshots.Count == 1)
                {
                    PoseSnapshot only = target.snapshots[0];
                    target.subject.position = only.position;
                    target.subject.rotation = only.rotation;
                    continue;
                }
                PoseSnapshot from = target.snapshots[0];
                PoseSnapshot to = target.snapshots[1];
                float duration = Mathf.Max(1f, to.timestamp - from.timestamp);
                float t = Mathf.Clamp01((float)(renderTimestamp - from.timestamp) / duration);
                target.subject.position = Vector3.LerpUnclamped(from.position, to.position, t);
                target.subject.rotation = Quaternion.Slerp(from.rotation, to.rotation, t);
            }
            UpdateMissionCamera();
        }

        private void CaptureCameraState()
        {
            Camera current = Camera.main;
            if (!current || cameraStateCaptured) return;
            missionCamera = current;
            originalCameraPosition = current.transform.position;
            originalCameraRotation = current.transform.rotation;
            originalCameraFieldOfView = current.fieldOfView;
            originalCameraOrthographicSize = current.orthographicSize;
            cameraStateCaptured = true;
        }

        private static void SetComparisonActive(bool active)
        {
            Camera current = Camera.main;
            if (!current)
                return;
            UavUsv.GazeboComparisonCamera comparison =
                current.GetComponent<UavUsv.GazeboComparisonCamera>();
            if (comparison)
                comparison.comparisonActive = active;
        }

        private void UpdateMissionCamera()
        {
            if (!externalMode || playbackFrozen || poseTargets.Count == 0) return;
            if (!missionCamera) missionCamera = Camera.main;
            if (!missionCamera) return;
            CaptureCameraState();

            bool hasSubject = false;
            float minX = float.MaxValue, maxX = float.MinValue;
            float minZ = float.MaxValue, maxZ = float.MinValue;
            foreach (PoseTarget target in poseTargets.Values)
            {
                if (!target.subject || !target.subject.gameObject.activeInHierarchy) continue;
                Vector3 point = target.subject.position;
                minX = Mathf.Min(minX, point.x);
                maxX = Mathf.Max(maxX, point.x);
                minZ = Mathf.Min(minZ, point.z);
                maxZ = Mathf.Max(maxZ, point.z);
                hasSubject = true;
            }
            if (!hasSubject) return;

            Vector3 center = new Vector3((minX + maxX) * .5f, 1.2f, (minZ + maxZ) * .5f);
            float span = Mathf.Max(maxX - minX, maxZ - minZ);
            float height = Mathf.Clamp(27f + span * .68f, 34f, 68f);
            Vector3 desiredPosition = center + new Vector3(0f, height, -height * .58f);
            Quaternion desiredRotation = Quaternion.LookRotation(center - desiredPosition, Vector3.up);
            float blend = 1f - Mathf.Exp(-2.8f * Time.unscaledDeltaTime);
            missionCamera.transform.position = Vector3.Lerp(missionCamera.transform.position, desiredPosition, blend);
            missionCamera.transform.rotation = Quaternion.Slerp(missionCamera.transform.rotation, desiredRotation, blend);
            if (missionCamera.orthographic)
            {
                float desiredSize = Mathf.Clamp(13f + span * .58f, 18f, 42f);
                missionCamera.orthographicSize = Mathf.Lerp(missionCamera.orthographicSize, desiredSize, blend);
            }
            else
            {
                missionCamera.fieldOfView = Mathf.Lerp(missionCamera.fieldOfView, 50f, blend);
            }
        }

        private void RestoreCameraState()
        {
            if (!cameraStateCaptured || !missionCamera) return;
            missionCamera.transform.position = originalCameraPosition;
            missionCamera.transform.rotation = originalCameraRotation;
            missionCamera.fieldOfView = originalCameraFieldOfView;
            missionCamera.orthographicSize = originalCameraOrthographicSize;
            cameraStateCaptured = false;
            missionCamera = null;
        }

        private bool EnsureScenario()
        {
            if (!scenario) scenario = FindObjectOfType<MultiAgentCaptureDefenseScenario>(true);
            if (scenario) EnsureEscortTarget();
            return scenario;
        }

        private Vector3 ResolveExternalOrigin()
        {
            UnityScenarioCompatibilityInstaller installer =
                FindObjectOfType<UnityScenarioCompatibilityInstaller>(true);
            if (installer && installer.Ready)
                return installer.MissionOrigin;
            if (scenario && scenario.targetVessel)
            {
                Vector3 position = scenario.targetVessel.position;
                return new Vector3(position.x, 0f, position.z);
            }
            return Vector3.zero;
        }

        private void EnsureEscortTarget()
        {
            if (escortTarget || !scenario || !scenario.targetVessel) return;
            GameObject existingEscort = GameObject.Find("friendly_ship");
            if (existingEscort)
            {
                escortTarget = existingEscort.transform;
                return;
            }
            GameObject clone = Instantiate(scenario.targetVessel.gameObject);
            clone.name = "EscortTarget";
            escortTarget = clone.transform;
            foreach (Renderer renderer in clone.GetComponentsInChildren<Renderer>(true))
            {
                Material material = renderer.material;
                if (material.HasProperty("_Color")) material.color = new Color(.14f, .8f, 1f);
                if (material.HasProperty("_EmissionColor"))
                {
                    material.EnableKeyword("_EMISSION");
                    material.SetColor("_EmissionColor", new Color(.02f, .28f, .42f));
                }
            }
            escortTarget.gameObject.SetActive(false);
        }

        private void SetFleetExternal(bool active)
        {
            if (!scenario) return;
            MethodInfo setter = scenario.GetType().GetMethod(
                "SetExternalControl",
                BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic
            );
            if (setter == null) return;
            if (scenario.boats != null)
                foreach (Transform boat in scenario.boats)
                    if (boat) setter.Invoke(scenario, new object[] { boat, active });
            if (scenario.drones != null)
                foreach (Transform drone in scenario.drones)
                    if (drone) setter.Invoke(scenario, new object[] { drone, active });
        }

        private void SetScenarioAutomatic(bool automatic)
        {
            if (!scenario) return;
            Type type = scenario.GetType();
            MethodInfo setter = type.GetMethod(
                "SetAutomatic",
                BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic
            );
            if (setter != null)
            {
                setter.Invoke(scenario, new object[] { automatic });
                return;
            }

            FieldInfo field = type.GetField(
                "automatic",
                BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic
            );
            if (field != null && field.FieldType == typeof(bool))
                field.SetValue(scenario, automatic);
        }

        private void SetCleanTaskPresentation(bool clean)
        {
            if (!scenario) return;
            if (!clean)
            {
                foreach (KeyValuePair<GameObject, bool> item in cleanPresentationStates)
                    if (item.Key) item.Key.SetActive(item.Value);
                cleanPresentationStates.Clear();
                return;
            }

            HideTaskClutter(scenario.shoreBase);
            if (scenario.obstacles == null) return;
            foreach (Transform obstacle in scenario.obstacles)
            {
                if (!obstacle) continue;
                string objectName = obstacle.name.ToLowerInvariant();
                if (objectName.Contains("lighthouse") || objectName.Contains("shorebase") ||
                    objectName.Contains("shore_command_base") ||
                    objectName.Contains("island_uav_base") ||
                    objectName.Contains("helipad"))
                    HideTaskClutter(obstacle);
            }

            // Scene bootstrap references are not guaranteed to be present in
            // the obstacle list in every WebGL build.  Match the generated
            // presentation roots as a fallback while keeping their collision
            // geometry represented by the backend safety map.
            foreach (Transform item in FindObjectsOfType<Transform>(true))
            {
                if (!item) continue;
                string objectName = item.name.ToLowerInvariant();
                if (objectName == "navigationlighthouse" || objectName == "shorebasestation" ||
                    objectName == "shore_command_base" ||
                    objectName == "island_uav_base" ||
                    objectName.StartsWith("helipad"))
                    HideTaskClutter(item);
            }
        }

        private void HideTaskClutter(Transform subject)
        {
            if (!subject) return;
            GameObject item = subject.gameObject;
            if (!cleanPresentationStates.ContainsKey(item)) cleanPresentationStates[item] = item.activeSelf;
            item.SetActive(false);
        }

        private void OnDestroy()
        {
            RestoreCameraState();
            SetCleanTaskPresentation(false);
        }

        private void RenderRoute(Vector2[] route)
        {
            if (algorithmCode != "ESCORT_GUARD" || route == null || route.Length < 2)
            {
                if (routeRenderer) routeRenderer.enabled = false;
                return;
            }
            if (!routeRenderer)
            {
                GameObject host = new GameObject("EscortRoute");
                host.transform.SetParent(transform, false);
                routeRenderer = host.AddComponent<LineRenderer>();
                routeRenderer.useWorldSpace = true;
                routeRenderer.widthMultiplier = .16f;
                routeRenderer.material = new Material(Shader.Find("Sprites/Default"));
                routeRenderer.startColor = new Color(.15f, .9f, 1f, .75f);
                routeRenderer.endColor = new Color(.15f, .9f, 1f, .2f);
            }
            routeRenderer.enabled = true;
            routeRenderer.positionCount = route.Length;
            for (int i = 0; i < route.Length; i++)
                routeRenderer.SetPosition(
                    i,
                    externalOrigin + new Vector3(route[i].x, .65f, route[i].y)
                );
        }

        private void OnGUI()
        {
            if (!externalMode || !Camera.main) return;
            EnsureStyles();
            DrawWorldLabel(escortTarget, "ESCORT", escortLabelStyle);
            if (scenario && algorithmCode == "ESCORT_GUARD")
                DrawWorldLabel(scenario.targetVessel, "THREAT", threatLabelStyle);
        }

        private void EnsureStyles()
        {
            if (escortLabelStyle != null) return;
            escortLabelStyle = new GUIStyle(GUI.skin.box)
            {
                alignment = TextAnchor.MiddleCenter,
                fontStyle = FontStyle.Bold,
                normal = { textColor = new Color(.35f, .95f, 1f) }
            };
            threatLabelStyle = new GUIStyle(GUI.skin.box)
            {
                alignment = TextAnchor.MiddleCenter,
                fontStyle = FontStyle.Bold,
                normal = { textColor = new Color(1f, .3f, .3f) }
            };
        }

        private static void DrawWorldLabel(Transform subject, string text, GUIStyle style)
        {
            if (!subject || !subject.gameObject.activeInHierarchy) return;
            Vector3 point = Camera.main.WorldToScreenPoint(subject.position + Vector3.up * 3.8f);
            if (point.z <= 0f) return;
            GUI.Box(new Rect(point.x - 42f, Screen.height - point.y - 12f, 84f, 24f), text, style);
        }

        private static string NormalizeCode(string code)
        {
            string normalized = code.Trim().ToUpperInvariant().Replace('_', '-');
            if (normalized.Length == 5 && (normalized.StartsWith("UAV-") || normalized.StartsWith("USV-")))
                normalized = normalized.Substring(0, 4) + "0" + normalized.Substring(4);
            return normalized;
        }
    }
}
