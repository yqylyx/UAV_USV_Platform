using System;
using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using UnityEngine;
using UnityEngine.Scripting;

namespace UavUsv.PlatformTools
{
    /// <summary>
    /// Reattaches the optional local capture scenario to the current Gazebo
    /// visualization scene without changing SimulationBootstrap.
    /// </summary>
    [Preserve]
    [DefaultExecutionOrder(-500)]
    public sealed class UnityScenarioCompatibilityInstaller : MonoBehaviour
    {
        private struct Pose
        {
            public Vector3 position;
            public Quaternion rotation;
        }

        public bool Ready { get; private set; }
        public MultiAgentCaptureDefenseScenario Scenario { get; private set; }
        public Vector3 MissionOrigin { get; private set; }

        private Transform[] boats;
        private Transform[] drones;
        private Transform targetVessel;
        private Transform targetPoint;
        private Pose[] boatPoses;
        private Pose[] dronePoses;
        private Pose targetPose;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void Install()
        {
            GameObject existing = GameObject.Find("UnityScenarioCompatibilityInstaller");
            GameObject host = existing
                ? existing
                : new GameObject("UnityScenarioCompatibilityInstaller");
            DontDestroyOnLoad(host);
            if (!host.GetComponent<UnityScenarioCompatibilityInstaller>())
                host.AddComponent<UnityScenarioCompatibilityInstaller>();
        }

        private IEnumerator Start()
        {
            while (!BindCurrentScene())
                yield return null;

            // Let the scenario initialize its private renderers, then restore
            // the Gazebo spawn layout and keep it idle until START_MISSION.
            yield return null;
            RestoreGazeboFormation();
            Scenario.automatic = false;
            Scenario.enabled = false;
            Ready = true;
        }

        private bool BindCurrentScene()
        {
            boats = FindFleet("usv");
            drones = FindFleet("uav");
            targetVessel = FindExact("enemy_ship");
            Transform shoreBase = FindExact("shore_command_base");
            Transform islandBase = FindExact("island_uav_base");
            Transform friendlyShip = FindExact("friendly_ship");
            Transform[] pads =
            {
                FindExact("pad_01"),
                FindExact("pad_02"),
                FindExact("pad_03")
            };

            if (boats == null || drones == null || !targetVessel ||
                !shoreBase || !pads[0] || !pads[1] || !pads[2])
                return false;

            CaptureInitialPoses();
            if (!targetPoint)
            {
                targetPoint = new GameObject("platform_target_point").transform;
                targetPoint.SetPositionAndRotation(targetPose.position, targetPose.rotation);
            }

            Transform[] obstacles = BuildObstacles(shoreBase, islandBase, friendlyShip);
            AgentSensorSuite[] boatSensors = BuildSensors(
                boats,
                AgentSensorSuite.SensorKind.Surface,
                38f,
                52f,
                obstacles
            );
            AgentSensorSuite[] droneSensors = BuildSensors(
                drones,
                AgentSensorSuite.SensorKind.Air,
                30f,
                52f,
                obstacles
            );
            DroneVisual[] visuals = new DroneVisual[drones.Length];
            for (int i = 0; i < drones.Length; i++)
                visuals[i] = drones[i] ? drones[i].GetComponent<DroneVisual>() : null;

            Scenario = FindObjectOfType<MultiAgentCaptureDefenseScenario>(true);
            if (!Scenario)
            {
                GameObject simulation = GameObject.Find("UAV-USV Simulation");
                Scenario = (simulation ? simulation : gameObject)
                    .AddComponent<MultiAgentCaptureDefenseScenario>();
            }

            Scenario.shoreBase = shoreBase;
            Scenario.dronePads = pads;
            Scenario.targetPoint = targetPoint;
            Scenario.targetVessel = targetVessel;
            Scenario.dynamicBarrier = null;
            Scenario.obstacles = obstacles;
            Scenario.boats = boats;
            Scenario.drones = drones;
            Scenario.droneVisuals = visuals;
            Scenario.boatSensors = boatSensors;
            Scenario.droneSensors = droneSensors;
            Scenario.automatic = false;
            Scenario.showDebugOverlays = true;
            SetTargetCenter(targetPose.position);
            return true;
        }

        private void CaptureInitialPoses()
        {
            boatPoses = Capture(boats);
            dronePoses = Capture(drones);
            targetPose = new Pose
            {
                position = targetVessel.position,
                rotation = targetVessel.rotation
            };
            MissionOrigin = new Vector3(
                targetPose.position.x,
                0f,
                targetPose.position.z
            );
        }

        private void RestoreGazeboFormation()
        {
            Restore(boats, boatPoses);
            for (int i = 0; i < drones.Length; i++)
                if (drones[i])
                    drones[i].SetParent(null, true);
            Restore(drones, dronePoses);
            targetPoint.SetPositionAndRotation(targetPose.position, targetPose.rotation);
            targetVessel.SetPositionAndRotation(targetPose.position, targetPose.rotation);

            float clearance = Mathf.Max(14f, Scenario.boatTargetClearance + 2f);
            for (int i = 0; i < boats.Length; i++)
            {
                if (!boats[i])
                    continue;
                Vector3 delta = boats[i].position - targetVessel.position;
                delta.y = 0f;
                if (delta.magnitude >= clearance)
                    continue;
                if (delta.sqrMagnitude < .01f)
                {
                    float angle = i * 120f * Mathf.Deg2Rad;
                    delta = new Vector3(Mathf.Cos(angle), 0f, Mathf.Sin(angle));
                }
                boats[i].position = targetVessel.position +
                                    delta.normalized * clearance +
                                    Vector3.up * .42f;
            }
        }

        private void SetTargetCenter(Vector3 unityPosition)
        {
            FieldInfo field = typeof(MultiAgentCaptureDefenseScenario).GetField(
                "targetCenterEnu",
                BindingFlags.Instance | BindingFlags.NonPublic
            );
            if (field == null)
                return;
            Vector3 enu = Coordinates.ToEnu(unityPosition);
            field.SetValue(Scenario, new Vector3(enu.x, enu.y, 0f));
        }

        private static Transform[] FindFleet(string prefix)
        {
            Transform[] result = new Transform[3];
            for (int i = 0; i < result.Length; i++)
                result[i] = FindExact(prefix + "_0" + (i + 1));
            return result[0] && result[1] && result[2] ? result : null;
        }

        private static Transform FindExact(string objectName)
        {
            foreach (Transform item in FindObjectsOfType<Transform>(true))
                if (item && string.Equals(item.name, objectName, StringComparison.OrdinalIgnoreCase))
                    return item;
            return null;
        }

        private static Transform[] BuildObstacles(params Transform[] candidates)
        {
            var result = new List<Transform>();
            foreach (Transform item in candidates)
                if (item && !result.Contains(item))
                    result.Add(item);
            return result.ToArray();
        }

        private static AgentSensorSuite[] BuildSensors(
            Transform[] fleet,
            AgentSensorSuite.SensorKind kind,
            float lidarRange,
            float radarRange,
            Transform[] obstacles)
        {
            var sensors = new AgentSensorSuite[fleet.Length];
            for (int i = 0; i < fleet.Length; i++)
            {
                AgentSensorSuite sensor = fleet[i].GetComponent<AgentSensorSuite>();
                if (!sensor)
                    sensor = fleet[i].gameObject.AddComponent<AgentSensorSuite>();
                sensor.Configure(kind, lidarRange, radarRange, obstacles);
                sensor.drawDebugRays = false;
                sensors[i] = sensor;
            }
            return sensors;
        }

        private static Pose[] Capture(Transform[] fleet)
        {
            var poses = new Pose[fleet.Length];
            for (int i = 0; i < fleet.Length; i++)
            {
                poses[i] = new Pose
                {
                    position = fleet[i].position,
                    rotation = fleet[i].rotation
                };
            }
            return poses;
        }

        private static void Restore(Transform[] fleet, Pose[] poses)
        {
            for (int i = 0; i < fleet.Length && i < poses.Length; i++)
                if (fleet[i])
                    fleet[i].SetPositionAndRotation(poses[i].position, poses[i].rotation);
        }
    }
}
