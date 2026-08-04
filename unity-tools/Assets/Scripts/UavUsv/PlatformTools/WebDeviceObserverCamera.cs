using System;
using System.Collections.Generic;
using UnityEngine;

namespace UavUsv.PlatformTools
{
    /// <summary>
    /// WebGL-only observation camera used by the Vue system overview.
    /// It never writes to mission agents and does not change ChaseCamera source code.
    /// </summary>
    public sealed class WebDeviceObserverCamera : MonoBehaviour
    {
        private enum ObservationMode
        {
            None,
            Device,
            Overview,
            Lighthouse
        }

        private readonly List<Transform> sceneTargets = new List<Transform>();
        private Camera observedCamera;
        private UavUsv.ChaseCamera chaseCamera;
        private Transform selectedSubject;
        private Transform lighthouse;
        private ObservationMode mode;
        private float desiredFieldOfView = 52f;
        private const float MinZoomScale = .42f;
        private const float MaxZoomScale = 2.25f;
        private float zoomScale = 1f;
        private float orbitYaw;
        private float orbitPitch;
        private Vector3 panOffset;
        private float lastPrimaryClickAt = -10f;

        public string CurrentDeviceCode { get; private set; } = string.Empty;
        public string CurrentModeName => ModeName(mode);
        public string CurrentProfileName => selectedSubject && IsUav(selectedSubject)
            ? "uav-overwatch"
            : selectedSubject ? "usv-chase" : CurrentModeName;
        public float ZoomPercent => Mathf.Round(zoomScale * 100f);

        public void Initialize(Camera camera, UavUsv.ChaseCamera chase)
        {
            observedCamera = camera;
            chaseCamera = chase;
            RefreshSceneTargets();
        }

        public bool TrySelectDevice(
            string requestedCode,
            out string canonicalCode,
            out string profile,
            out string error)
        {
            RefreshSceneTargets();
            string normalized = NormalizeDeviceCode(requestedCode);
            Transform match = null;
            for (int i = 0; i < sceneTargets.Count; i++)
            {
                Transform candidate = sceneTargets[i];
                if (!candidate || (!IsUsv(candidate) && !IsUav(candidate)))
                    continue;
                if (NormalizeDeviceCode(candidate.name) == normalized)
                {
                    match = candidate;
                    break;
                }
            }

            if (!match)
            {
                canonicalCode = normalized;
                profile = string.Empty;
                error = "Unity scene device not found: " + requestedCode;
                return false;
            }

            selectedSubject = match;
            CurrentDeviceCode = CanonicalDeviceCode(match);
            mode = ObservationMode.Device;
            ActivateObserver();
            canonicalCode = CurrentDeviceCode;
            profile = CurrentProfileName;
            error = string.Empty;
            return true;
        }

        public bool TrySelectFirst(
            string kind,
            out string canonicalCode,
            out string profile,
            out string error)
        {
            RefreshSceneTargets();
            bool wantUav = string.Equals(kind, "UAV", StringComparison.OrdinalIgnoreCase);
            sceneTargets.Sort((left, right) => string.Compare(
                CanonicalDeviceCode(left),
                CanonicalDeviceCode(right),
                StringComparison.OrdinalIgnoreCase
            ));
            for (int i = 0; i < sceneTargets.Count; i++)
            {
                Transform candidate = sceneTargets[i];
                if (candidate && (wantUav ? IsUav(candidate) : IsUsv(candidate)))
                    return TrySelectDevice(candidate.name, out canonicalCode, out profile, out error);
            }

            canonicalCode = string.Empty;
            profile = string.Empty;
            error = "Unity scene has no " + kind + " device";
            return false;
        }

        public void SetOverview()
        {
            mode = ObservationMode.Overview;
            ResetInteraction();
            ActivateObserver();
        }

        public void SetLighthouse()
        {
            RefreshSceneTargets();
            mode = ObservationMode.Lighthouse;
            ResetInteraction();
            ActivateObserver();
        }

        public void FitAll()
        {
            mode = ObservationMode.Overview;
            ResetInteraction();
            ActivateObserver();
        }

        public void AdjustZoom(float steps)
        {
            if (Mathf.Abs(steps) < .001f)
                return;
            zoomScale = Mathf.Clamp(
                zoomScale * Mathf.Exp(-steps * .115f),
                MinZoomScale,
                MaxZoomScale
            );
        }

        public void SetZoomPercent(float percent)
        {
            zoomScale = Mathf.Clamp(percent * .01f, MinZoomScale, MaxZoomScale);
        }

        public void ResetInteraction()
        {
            zoomScale = 1f;
            orbitYaw = 0f;
            orbitPitch = 0f;
            panOffset = Vector3.zero;
        }

        public void ReleaseToOriginalCamera()
        {
            SetComparisonActive(false);
            mode = ObservationMode.None;
            if (chaseCamera)
                chaseCamera.enabled = true;
        }

        public void SetGazeboComparison()
        {
            mode = ObservationMode.None;
            if (chaseCamera)
                chaseCamera.enabled = false;
            SetComparisonActive(true);
        }

        public bool RecenterCurrentDevice(out string error)
        {
            if (!selectedSubject)
            {
                if (!string.IsNullOrWhiteSpace(CurrentDeviceCode) &&
                    TrySelectDevice(CurrentDeviceCode, out _, out _, out error))
                    return true;

                return TrySelectFirst("UAV", out _, out _, out error);
            }

            mode = ObservationMode.Device;
            ActivateObserver();
            error = string.Empty;
            return true;
        }

        private void ActivateObserver()
        {
            SetComparisonActive(false);
            if (!observedCamera)
                observedCamera = GetComponent<Camera>();
            if (!chaseCamera)
                chaseCamera = GetComponent<UavUsv.ChaseCamera>();
            if (chaseCamera)
                chaseCamera.enabled = false;
        }

        private void LateUpdate()
        {
            if (mode == ObservationMode.None || !observedCamera)
                return;

            HandleInteractiveInput();
            RefreshSceneTargets();
            Vector3 desiredPosition;
            Vector3 focusPoint;

            if (mode == ObservationMode.Device && selectedSubject)
                CalculateDeviceView(out desiredPosition, out focusPoint);
            else if (mode == ObservationMode.Lighthouse)
                CalculateLighthouseView(out desiredPosition, out focusPoint);
            else
                CalculateOverview(out desiredPosition, out focusPoint);

            ApplyInteractiveTransform(ref desiredPosition, ref focusPoint);

            desiredPosition.y = Mathf.Max(desiredPosition.y, 2.4f);
            Quaternion desiredRotation = Quaternion.LookRotation(
                focusPoint - desiredPosition,
                Vector3.up
            );
            float positionT = 1f - Mathf.Exp(-3.2f * Time.unscaledDeltaTime);
            float rotationT = 1f - Mathf.Exp(-4.8f * Time.unscaledDeltaTime);
            float fovT = 1f - Mathf.Exp(-3.5f * Time.unscaledDeltaTime);
            transform.position = Vector3.Lerp(transform.position, desiredPosition, positionT);
            transform.rotation = Quaternion.Slerp(transform.rotation, desiredRotation, rotationT);
            observedCamera.fieldOfView = Mathf.Lerp(
                observedCamera.fieldOfView,
                desiredFieldOfView,
                fovT
            );
        }

        private void HandleInteractiveInput()
        {
            float wheel = Input.mouseScrollDelta.y;
            if (Mathf.Abs(wheel) > .001f)
                AdjustZoom(wheel);

            if (Input.GetMouseButton(1))
            {
                orbitYaw += Input.GetAxis("Mouse X") * 2.2f;
                orbitPitch = Mathf.Clamp(
                    orbitPitch - Input.GetAxis("Mouse Y") * 1.8f,
                    -28f,
                    38f
                );
            }

            bool panning = Input.GetMouseButton(2) ||
                           (Input.GetKey(KeyCode.LeftShift) && Input.GetMouseButton(0));
            if (panning)
            {
                float distance = Mathf.Max(8f, Vector3.Distance(transform.position, panOffset));
                float scale = Mathf.Clamp(distance * .0018f, .025f, .34f);
                Vector3 right = transform.right;
                Vector3 forward = Vector3.ProjectOnPlane(transform.forward, Vector3.up).normalized;
                panOffset += (-right * Input.GetAxis("Mouse X") -
                              forward * Input.GetAxis("Mouse Y")) * scale;
                panOffset.y = 0f;
            }

            if (Input.GetMouseButtonDown(0) && !Input.GetKey(KeyCode.LeftShift))
            {
                float now = Time.unscaledTime;
                if (now - lastPrimaryClickAt <= .32f)
                    FitAll();
                lastPrimaryClickAt = now;
            }

            if (Input.GetKeyDown(KeyCode.Home))
                FitAll();
        }

        private void ApplyInteractiveTransform(ref Vector3 position, ref Vector3 focus)
        {
            focus += panOffset;
            position += panOffset;
            Vector3 offset = position - focus;
            float distance = Mathf.Max(4f, offset.magnitude) * zoomScale;
            Quaternion rotation = Quaternion.Euler(orbitPitch, orbitYaw, 0f);
            Vector3 direction = rotation * offset.normalized;
            position = focus + direction * distance;
        }

        private void CalculateDeviceView(out Vector3 position, out Vector3 focus)
        {
            Vector3 groupCenter;
            float spread;
            CalculateGroupFrame(out groupCenter, out spread);

            Vector3 forward = DeviceForward(selectedSubject);
            Vector3 subject = selectedSubject.position;
            GetVisualMetrics(
                selectedSubject,
                out float visualRadius,
                out float visualTop,
                out float visualCenterHeight
            );
            if (IsUav(selectedSubject))
            {
                float height = Mathf.Clamp(
                    Mathf.Max(25f + spread * .22f, visualTop + 18f),
                    25f,
                    60f
                );
                float back = Mathf.Clamp(
                    Mathf.Max(8f + spread * .055f, visualRadius * 2.1f),
                    8f,
                    24f
                );
                position = subject - forward * back + Vector3.up * height;
                focus = Vector3.Lerp(subject, groupCenter, .72f) +
                    Vector3.up * Mathf.Max(1.2f, visualCenterHeight);
                desiredFieldOfView = Mathf.Clamp(55f + spread * .16f, 55f, 72f);
                return;
            }

            float distance = Mathf.Clamp(
                Mathf.Max(14f + spread * .31f, visualRadius * 2.35f),
                14f,
                48f
            );
            float heightUsv = Mathf.Clamp(
                Mathf.Max(7f + spread * .095f, visualTop + 4f),
                7f,
                24f
            );
            Vector3 subjectLook = subject +
                forward * Mathf.Max(5.5f, visualRadius) +
                Vector3.up * Mathf.Max(2.4f, visualCenterHeight);
            position = subject - forward * distance + Vector3.up * heightUsv;
            focus = Vector3.Lerp(
                subjectLook,
                groupCenter + Vector3.up * Mathf.Max(2.2f, visualCenterHeight),
                .56f
            );
            desiredFieldOfView = Mathf.Clamp(52f + spread * .2f, 52f, 72f);
        }

        private static void GetVisualMetrics(
            Transform subject,
            out float radius,
            out float top,
            out float centerHeight)
        {
            radius = 0f;
            top = 0f;
            centerHeight = 0f;
            if (!subject)
                return;

            Renderer[] renderers = subject.GetComponentsInChildren<Renderer>(false);
            Bounds bounds = default;
            bool found = false;
            for (int i = 0; i < renderers.Length; i++)
            {
                Renderer renderer = renderers[i];
                if (!renderer || !renderer.enabled ||
                    !renderer.gameObject.activeInHierarchy)
                    continue;

                if (!found)
                {
                    bounds = renderer.bounds;
                    found = true;
                }
                else
                {
                    bounds.Encapsulate(renderer.bounds);
                }
            }

            if (!found)
                return;

            radius = Mathf.Max(bounds.extents.x, bounds.extents.z);
            top = Mathf.Max(0f, bounds.max.y - subject.position.y);
            centerHeight = Mathf.Max(0f, bounds.center.y - subject.position.y);
        }

        private void CalculateOverview(out Vector3 position, out Vector3 focus)
        {
            Vector3 groupCenter;
            float spread;
            CalculateGroupFrame(out groupCenter, out spread);
            focus = groupCenter + Vector3.up * 1.2f;
            desiredFieldOfView = 58f;
            Vector3 viewOffsetDirection =
                (Quaternion.Euler(62f, -35f, 0f) * Vector3.back).normalized;
            float distance = CalculateOverviewDistance(
                focus,
                viewOffsetDirection,
                spread,
                desiredFieldOfView
            );
            position = focus + viewOffsetDirection * distance;
        }

        private float CalculateOverviewDistance(
            Vector3 focus,
            Vector3 viewOffsetDirection,
            float spread,
            float verticalFieldOfView)
        {
            float aspect = observedCamera
                ? Mathf.Max(.75f, observedCamera.aspect)
                : 16f / 9f;
            float halfVertical = verticalFieldOfView * .5f * Mathf.Deg2Rad;
            float tanVertical = Mathf.Max(.25f, Mathf.Tan(halfVertical));
            float tanHorizontal = Mathf.Max(.25f, tanVertical * aspect);
            Quaternion viewRotation = Quaternion.LookRotation(
                -viewOffsetDirection,
                Vector3.up
            );
            Quaternion inverseView = Quaternion.Inverse(viewRotation);
            float requiredDistance = Mathf.Max(110f, 78f + spread * 1.65f);

            for (int i = 0; i < sceneTargets.Count; i++)
            {
                Transform item = sceneTargets[i];
                if (!item)
                    continue;

                Vector3 local = inverseView * (item.position - focus);
                GetVisualMetrics(item, out float radius, out float top, out _);
                float padding = Mathf.Max(7f, radius * 1.35f, top * .8f);
                float verticalDistance =
                    (Mathf.Abs(local.y) + padding) / tanVertical - local.z;
                float horizontalDistance =
                    (Mathf.Abs(local.x) + padding) / tanHorizontal - local.z;
                requiredDistance = Mathf.Max(
                    requiredDistance,
                    verticalDistance,
                    horizontalDistance
                );
            }

            return Mathf.Clamp(requiredDistance * 1.18f, 110f, 560f);
        }

        private void CalculateLighthouseView(out Vector3 position, out Vector3 focus)
        {
            Vector3 groupCenter;
            float spread;
            CalculateGroupFrame(out groupCenter, out spread);
            if (!lighthouse)
            {
                CalculateOverview(out position, out focus);
                return;
            }

            Vector3 outward = lighthouse.position - groupCenter;
            outward.y = 0f;
            if (outward.sqrMagnitude < .01f)
                outward = Vector3.back;
            outward.Normalize();
            position = lighthouse.position + outward * 12f + Vector3.up * 24f;
            focus = Vector3.Lerp(lighthouse.position, groupCenter, .8f) + Vector3.up * 2f;
            desiredFieldOfView = Mathf.Clamp(56f + spread * .12f, 56f, 70f);
        }

        private void CalculateGroupFrame(out Vector3 center, out float spread)
        {
            center = Vector3.zero;
            int count = 0;
            for (int i = 0; i < sceneTargets.Count; i++)
            {
                Transform item = sceneTargets[i];
                if (!item)
                    continue;
                center += item.position;
                count++;
            }

            if (count == 0)
            {
                center = selectedSubject ? selectedSubject.position : Vector3.zero;
                spread = 1f;
                return;
            }

            center /= count;
            spread = 1f;
            for (int i = 0; i < sceneTargets.Count; i++)
            {
                Transform item = sceneTargets[i];
                if (!item)
                    continue;
                Vector3 delta = item.position - center;
                delta.y *= .35f;
                spread = Mathf.Max(spread, delta.magnitude);
            }
        }

        private void RefreshSceneTargets()
        {
            sceneTargets.Clear();
            if (!chaseCamera)
                chaseCamera = GetComponent<UavUsv.ChaseCamera>();
            if (chaseCamera)
            {
                lighthouse = chaseCamera.lookAt;
                Transform[] targets = chaseCamera.groupTargets;
                if (targets != null)
                {
                    for (int i = 0; i < targets.Length; i++)
                    {
                        if (targets[i] && !sceneTargets.Contains(targets[i]))
                            sceneTargets.Add(targets[i]);
                    }
                }
            }
        }

        private static Vector3 DeviceForward(Transform subject)
        {
            Vector3 forward = IsUsv(subject) ? subject.right : subject.forward;
            forward.y = 0f;
            return forward.sqrMagnitude > .001f ? forward.normalized : Vector3.forward;
        }

        private static bool IsUsv(Transform subject)
        {
            return subject &&
                   NormalizeDeviceCode(subject.name).StartsWith(
                       "USV-",
                       StringComparison.OrdinalIgnoreCase
                   );
        }

        private static bool IsUav(Transform subject)
        {
            return subject &&
                   NormalizeDeviceCode(subject.name).StartsWith(
                       "UAV-",
                       StringComparison.OrdinalIgnoreCase
                   );
        }

        private void SetComparisonActive(bool active)
        {
            UavUsv.GazeboComparisonCamera comparison =
                GetComponent<UavUsv.GazeboComparisonCamera>();
            if (comparison)
                comparison.comparisonActive = active;
        }

        public static string NormalizeDeviceCode(string value)
        {
            if (string.IsNullOrWhiteSpace(value))
                return string.Empty;
            string upper = value.Trim().ToUpperInvariant().Replace("_", "-");
            string prefix = upper.StartsWith("UAV") ? "UAV" : upper.StartsWith("USV") ? "USV" : string.Empty;
            if (string.IsNullOrEmpty(prefix))
                return upper;
            string digits = string.Empty;
            for (int i = prefix.Length; i < upper.Length; i++)
            {
                if (char.IsDigit(upper[i]))
                    digits += upper[i];
            }
            if (!int.TryParse(digits, out int index))
                return upper;
            return prefix + "-" + index.ToString("00");
        }

        private static string CanonicalDeviceCode(Transform subject)
        {
            return NormalizeDeviceCode(subject ? subject.name : string.Empty);
        }

        private static string ModeName(ObservationMode value)
        {
            switch (value)
            {
                case ObservationMode.Device: return "device-follow";
                case ObservationMode.Overview: return "overview";
                case ObservationMode.Lighthouse: return "lighthouse";
                default: return "action";
            }
        }

        private void OnDestroy()
        {
            if (chaseCamera)
                chaseCamera.enabled = true;
        }
    }
}
