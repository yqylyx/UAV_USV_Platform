using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Scripting;

namespace UavUsv.PlatformTools
{
    /// <summary>
    /// Web presentation control adapter. It overlays per-vehicle commands on the
    /// existing scenario without changing the scenario's source implementation.
    /// </summary>
    [Preserve]
    public sealed class WebVehicleCommandController : MonoBehaviour
    {
        private enum OverrideMode { Hold, Takeoff, Return, Land, Stop }

        private sealed class VehicleOverride
        {
            public OverrideMode mode;
            public Vector3 target;
            public string state;
            public Vector3? finalTarget;
        }

        private readonly Dictionary<Transform, VehicleOverride> overrides =
            new Dictionary<Transform, VehicleOverride>();
        private MultiAgentCaptureDefenseScenario scenario;

        public bool EnsureScenario()
        {
            if (!scenario)
                scenario = FindObjectOfType<MultiAgentCaptureDefenseScenario>();
            return scenario;
        }

        public bool TryExecute(string rawCommand, string rawDeviceCode, out string state, out string detail)
        {
            state = "ERROR";
            detail = string.Empty;
            if (!EnsureScenario())
            {
                detail = "Capture scenario is not ready";
                return false;
            }

            string command = (rawCommand ?? string.Empty).Trim().ToLowerInvariant();
            if (TryExecuteMissionCommand(command, out state, out detail))
                return true;
            if (!TryResolve(rawDeviceCode, out Transform subject, out bool isUav, out int index))
            {
                detail = "Unknown vehicle: " + (rawDeviceCode ?? string.Empty);
                return false;
            }

            switch (command)
            {
                case "uavtakeoff":
                    if (!isUav) return Reject("UAV command sent to USV", out state, out detail);
                    SetOverride(subject, OverrideMode.Takeoff,
                        new Vector3(subject.position.x, Mathf.Max(scenario.droneAltitude, subject.position.y), subject.position.z),
                        "TAKING_OFF");
                    state = "TAKING_OFF";
                    break;
                case "uavhover":
                    if (!isUav) return Reject("UAV command sent to USV", out state, out detail);
                    SetOverride(subject, OverrideMode.Hold, subject.position, "HOLDING");
                    state = "HOLDING";
                    break;
                case "uavresume":
                    if (!isUav) return Reject("UAV command sent to USV", out state, out detail);
                    overrides.Remove(subject);
                    scenario.automatic = true;
                    state = "AIRBORNE";
                    break;
                case "uavreturn":
                    if (!isUav) return Reject("UAV command sent to USV", out state, out detail);
                    Vector3 airHome = DroneHome(index);
                    airHome.y = Mathf.Max(scenario.droneAltitude, subject.position.y);
                    SetOverride(subject, OverrideMode.Return, airHome, "RETURNING");
                    state = "RETURNING";
                    break;
                case "uavland":
                case "uavemergencyland":
                    if (!isUav) return Reject("UAV command sent to USV", out state, out detail);
                    Vector3 landingPad = DroneHome(index);
                    Vector3 landingApproach = landingPad;
                    landingApproach.y = Mathf.Max(scenario.droneAltitude, subject.position.y);
                    SetOverride(subject, OverrideMode.Land, landingApproach, "LANDING", landingPad);
                    state = "LANDING";
                    break;
                case "usvdepart":
                    if (isUav) return Reject("USV command sent to UAV", out state, out detail);
                    overrides.Remove(subject);
                    scenario.automatic = true;
                    state = "SAILING";
                    break;
                case "usvhold":
                    if (isUav) return Reject("USV command sent to UAV", out state, out detail);
                    SetOverride(subject, OverrideMode.Hold, subject.position, "HOLDING");
                    state = "HOLDING";
                    break;
                case "usvresume":
                    if (isUav) return Reject("USV command sent to UAV", out state, out detail);
                    overrides.Remove(subject);
                    scenario.automatic = true;
                    state = "SAILING";
                    break;
                case "usvreturn":
                    if (isUav) return Reject("USV command sent to UAV", out state, out detail);
                    SetOverride(subject, OverrideMode.Return, BoatHome(index), "RETURNING");
                    state = "RETURNING";
                    break;
                case "usvstop":
                case "usvemergencystop":
                    if (isUav) return Reject("USV command sent to UAV", out state, out detail);
                    SetOverride(subject, OverrideMode.Stop, subject.position, "STOPPED");
                    state = "STOPPED";
                    break;
                default:
                    detail = "Unsupported equipment command: " + command;
                    return false;
            }

            detail = command + " accepted for " + rawDeviceCode;
            return true;
        }

        private bool TryExecuteMissionCommand(string command, out string state, out string detail)
        {
            state = "RUNNING";
            detail = string.Empty;
            switch (command)
            {
                case "missionstart":
                    scenario.enabled = true;
                    scenario.automatic = true;
                    scenario.NotifyBaseDispatch();
                    detail = "Mission dispatch started";
                    return true;
                case "missionpause":
                    scenario.automatic = false;
                    scenario.enabled = false;
                    state = "PAUSED";
                    detail = "Mission simulation paused";
                    return true;
                case "missionresume":
                    scenario.enabled = true;
                    scenario.automatic = true;
                    detail = "Mission simulation resumed";
                    return true;
                case "missionreturn":
                    scenario.automatic = false;
                    scenario.enabled = false;
                    state = "RETURNING";
                    detail = "Mission return delegated to vehicle commands";
                    return true;
                case "missioncomplete":
                    scenario.automatic = false;
                    scenario.enabled = false;
                    state = "COMPLETED";
                    detail = "Mission completion confirmed";
                    return true;
                case "missionfail":
                case "missioncancel":
                    scenario.automatic = false;
                    scenario.enabled = false;
                    state = command == "missionfail" ? "FAILED" : "CANCELLED";
                    detail = "Mission stopped by platform command";
                    return true;
                default:
                    return false;
            }
        }

        public string StateFor(Transform subject, bool isUav)
        {
            if (subject && overrides.TryGetValue(subject, out VehicleOverride item))
                return item.state;
            if (!subject) return "OFFLINE";
            return isUav
                ? (subject.position.y > 1.5f ? "AIRBORNE" : "GROUNDED")
                : "SAILING";
        }

        private void LateUpdate()
        {
            if (!EnsureScenario() || overrides.Count == 0)
                return;

            foreach (KeyValuePair<Transform, VehicleOverride> pair in overrides)
            {
                Transform subject = pair.Key;
                VehicleOverride item = pair.Value;
                if (!subject) continue;

                if (item.mode == OverrideMode.Hold || item.mode == OverrideMode.Stop)
                {
                    subject.position = item.target;
                    continue;
                }

                bool droneSubject = subject.name.IndexOf("UAV", StringComparison.OrdinalIgnoreCase) >= 0;
                float speed = item.mode == OverrideMode.Land
                    ? (droneSubject && item.finalTarget.HasValue && Mathf.Abs(item.target.y - item.finalTarget.Value.y) > .25f
                        ? Mathf.Max(4f, scenario.droneSpeed)
                        : Mathf.Max(1.5f, scenario.droneTakeoffClimbSpeed))
                    : (subject.name.IndexOf("UAV", StringComparison.OrdinalIgnoreCase) >= 0
                        ? scenario.droneSpeed
                        : scenario.boatSpeed);
                subject.position = Vector3.MoveTowards(subject.position, item.target, speed * Time.deltaTime);
                if ((subject.position - item.target).sqrMagnitude > .04f)
                    continue;

                if (item.mode == OverrideMode.Takeoff)
                {
                    item.mode = OverrideMode.Hold;
                    item.state = "AIRBORNE";
                    item.target = subject.position;
                }
                else if (item.mode == OverrideMode.Land)
                {
                    if (item.finalTarget.HasValue && (item.target - item.finalTarget.Value).sqrMagnitude > .04f)
                    {
                        item.target = item.finalTarget.Value;
                    }
                    else
                    {
                        item.mode = OverrideMode.Hold;
                        item.state = "GROUNDED";
                        item.target = subject.position;
                        item.finalTarget = null;
                    }
                }
                else if (item.mode == OverrideMode.Return)
                {
                    item.mode = OverrideMode.Hold;
                    item.state = "HOLDING";
                    item.target = subject.position;
                }
            }
        }

        private void SetOverride(Transform subject, OverrideMode mode, Vector3 target, string state, Vector3? finalTarget = null)
        {
            overrides[subject] = new VehicleOverride
            {
                mode = mode,
                target = target,
                state = state,
                finalTarget = finalTarget
            };
        }

        private bool TryResolve(string rawCode, out Transform subject, out bool isUav, out int index)
        {
            subject = null;
            isUav = false;
            index = -1;
            string code = (rawCode ?? string.Empty).Trim().ToLowerInvariant();
            isUav = code.StartsWith("uav-");
            bool isUsv = code.StartsWith("usv-");
            if (!isUav && !isUsv) return false;
            if (!int.TryParse(code.Substring(4), out int ordinal)) return false;
            index = ordinal - 1;
            Transform[] collection = isUav ? scenario.drones : scenario.boats;
            if (collection == null || index < 0 || index >= collection.Length || !collection[index]) return false;
            subject = collection[index];
            return true;
        }

        private Vector3 DroneHome(int index)
        {
            if (scenario.dronePads != null && index >= 0 && index < scenario.dronePads.Length && scenario.dronePads[index])
                return scenario.dronePads[index].position;
            return scenario.shoreBase ? scenario.shoreBase.position : Vector3.zero;
        }

        private Vector3 BoatHome(int index)
        {
            Vector3 home = scenario.shoreBase ? scenario.shoreBase.position : Vector3.zero;
            home += new Vector3((index - 1) * 5f, .42f, 7f);
            home.y = .42f;
            return home;
        }

        private static bool Reject(string message, out string state, out string detail)
        {
            state = "ERROR";
            detail = message;
            return false;
        }
    }
}
