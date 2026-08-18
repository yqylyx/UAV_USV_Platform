using System;
using System.Runtime.InteropServices;
using UnityEngine;
using UnityEngine.Scripting;

namespace UavUsv.PlatformTools
{
    /// <summary>
    /// Browser visual-sensor adapter.
    ///
    /// The primary path renders six sensor cameras to GPU RenderTextures and
    /// composites them directly into the existing Unity WebGL canvas. No video
    /// frame crosses the JS boundary, so the browser avoids synchronous
    /// ReadPixels, JPEG encoding and Base64 copies. The previous JPEG bridge is
    /// retained as an opt-in compatibility fallback only.
    /// </summary>
    [Preserve]
    [DefaultExecutionOrder(12000)]
    public sealed class UnityVisualSensorBridge : MonoBehaviour
    {
        [Serializable]
        private sealed class SubscriptionPayload
        {
            public bool enabled;
            public string focusedCameraId;
            public float thumbnailFps = 1f;
            public float focusedFps = 4f;
            public string displayMode = "grid";
            public string quality = "720p";
            public int targetFps = 30;
            public bool gpuDirect = true;
            public bool jpegFallback;
        }

        [Serializable]
        private sealed class IncomingMessage
        {
            public string type;
            public SubscriptionPayload payload;
        }

        [Serializable]
        private sealed class ReadyPayload
        {
            public bool ready;
            public string source;
            public int cameraCount;
            public bool gpuDirect;
            public string[] qualityProfiles;
            public int maxTargetFps;
        }

        [Serializable]
        private sealed class FramePayload
        {
            public string cameraId;
            public string deviceCode;
            public string viewType;
            public string source;
            public int width;
            public int height;
            public long timestampMs;
            public int sequence;
            public string jpegBase64;
        }

        [Serializable]
        private sealed class StreamStatsPayload
        {
            public bool active;
            public bool gpuDirect;
            public string displayMode;
            public string requestedQuality;
            public string activeQuality;
            public string focusedCameraId;
            public int cameraCount;
            public int streamWidth;
            public int streamHeight;
            public int targetFps;
            public float measuredFps;
            public float renderMs;
            public bool adaptiveFallback;
            public long timestampMs;
        }

        [Serializable]
        private sealed class BridgeEnvelope<T>
        {
            public string type;
            public string requestId = "";
            public long timestamp;
            public T payload;
        }

        private static readonly string[] CameraIds =
        {
            "uav_01", "uav_02", "uav_03",
            "usv_01", "usv_02", "usv_03"
        };

        private static readonly string[] DeviceCodes =
        {
            "UAV-01", "UAV-02", "UAV-03",
            "USV-01", "USV-02", "USV-03"
        };

        private const int HdWidth = 1280;
        private const int HdHeight = 720;
        private const int FullHdWidth = 1920;
        private const int FullHdHeight = 1080;
        private const float StatsIntervalSeconds = 1f;

#if UNITY_WEBGL && !UNITY_EDITOR
        [DllImport("__Internal")]
        private static extern void VueWebGlPostMessage(string message);
#endif

        private UavUsv.SensorViewPip sensorSuite;
        private Camera captureCamera;
        private readonly RenderTexture[] liveTextures = new RenderTexture[6];
        private RenderTexture thumbnailRenderTexture;
        private RenderTexture focusedRenderTexture;
        private Texture2D thumbnailTexture;
        private Texture2D focusedTexture;
        private readonly float[] nextCaptureTimes = new float[6];

        private bool subscribed;
        private bool gpuDirect = true;
        private bool jpegFallback;
        private string displayMode = "grid";
        private string focusedCameraId = "uav_01";
        private string requestedQuality = "720p";
        private string activeQuality = "720p";
        private int targetFps = 30;
        private float thumbnailFps = 1f;
        private float focusedFps = 4f;
        private int sequence;
        private int roundRobinIndex;
        private bool focusedTurn = true;
        private bool readyPosted;

        private int liveWidth = HdWidth;
        private int liveHeight = HdHeight;
        private float nextRenderTime;
        private float statsWindowStartedAt;
        private int renderedFramesInWindow;
        private float measuredFps;
        private float smoothedRenderMs;
        private int slow1080pWindows;
        private bool adaptiveFallback;

        private Camera presentationCamera;
        private int presentationCullingMask;
        private CameraClearFlags presentationClearFlags;
        private Color presentationBackground;
        private bool presentationMuted;
        private int previousTargetFrameRate;
        private int previousVSyncCount;
        private bool performanceSettingsApplied;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void Install()
        {
            if (FindObjectOfType<UnityVisualSensorBridge>())
                return;
            var host = new GameObject("UnityVisualSensorBridge");
            DontDestroyOnLoad(host);
            host.AddComponent<UnityVisualSensorBridge>();
        }

        private void LateUpdate()
        {
            EnsureSensorSuite();
            if (!sensorSuite || !subscribed)
                return;

            if (gpuDirect && displayMode != "off")
            {
                RenderDirectViewsIfDue();
                // GPU direct owns the single WebGL canvas.  The remaining
                // camera cards still need individually-addressed frames, so
                // publish low-rate JPEG thumbnails alongside the focused
                // canvas instead of returning before legacy capture runs.
                if (jpegFallback)
                    CaptureLegacyFrameIfDue();
                return;
            }

            CaptureLegacyFrameIfDue();
        }

        [Preserve]
        public void ReceiveFromVue(string json)
        {
            try
            {
                IncomingMessage message = JsonUtility.FromJson<IncomingMessage>(json);
                if (message == null ||
                    !string.Equals(message.type, "visualSensorSubscribe", StringComparison.OrdinalIgnoreCase))
                    return;

                SubscriptionPayload payload = message.payload ?? new SubscriptionPayload();
                if (!payload.enabled)
                {
                    StopSubscription();
                    return;
                }

                string nextMode = NormalizeDisplayMode(payload.displayMode);
                string nextQuality = NormalizeQuality(payload.quality);
                bool qualityChanged = !string.Equals(requestedQuality, nextQuality, StringComparison.Ordinal);

                subscribed = true;
                gpuDirect = payload.gpuDirect;
                jpegFallback = payload.jpegFallback;
                displayMode = nextMode;
                requestedQuality = nextQuality;
                targetFps = Mathf.Clamp(payload.targetFps <= 0 ? 30 : payload.targetFps, 15, 60);
                thumbnailFps = Mathf.Clamp(payload.thumbnailFps <= 0f ? 1f : payload.thumbnailFps, .2f, 2f);
                focusedFps = Mathf.Clamp(payload.focusedFps <= 0f ? 4f : payload.focusedFps, 1f, 8f);
                if (Array.IndexOf(CameraIds, payload.focusedCameraId) >= 0)
                    focusedCameraId = payload.focusedCameraId;

                if (qualityChanged || adaptiveFallback)
                {
                    activeQuality = requestedQuality;
                    adaptiveFallback = false;
                    slow1080pWindows = 0;
                    ReleaseLiveResources();
                }

                float immediate = Time.realtimeSinceStartup - 1f;
                for (int i = 0; i < nextCaptureTimes.Length; i++)
                    nextCaptureTimes[i] = immediate;
                nextRenderTime = immediate;
                statsWindowStartedAt = Time.realtimeSinceStartup;
                renderedFramesInWindow = 0;
                measuredFps = 0f;
                smoothedRenderMs = 0f;

                if (gpuDirect && displayMode != "off")
                {
                    ApplyDirectDisplaySettings();
                    EnsureLiveResources();
                    if (jpegFallback)
                        EnsureLegacyCaptureResources();
                }
                else
                {
                    RestoreDirectDisplaySettings();
                    EnsureLegacyCaptureResources();
                }

                PostStreamStats();
            }
            catch (Exception exception)
            {
                Debug.LogWarning("Unity visual sensor subscription rejected: " + exception.Message);
            }
        }

        private void StopSubscription()
        {
            subscribed = false;
            displayMode = "off";
            jpegFallback = false;
            RestoreDirectDisplaySettings();
            ReleaseLiveResources();
            PostStreamStats();
        }

        private void EnsureSensorSuite()
        {
            if (!sensorSuite)
                sensorSuite = FindObjectOfType<UavUsv.SensorViewPip>(true);
            if (!sensorSuite)
                return;

            if (!captureCamera)
            {
                var host = new GameObject("Unity Visual Sensor Capture Camera");
                host.transform.SetParent(transform, false);
                captureCamera = host.AddComponent<Camera>();
                captureCamera.enabled = false;
                captureCamera.nearClipPlane = .15f;
                captureCamera.farClipPlane = 5500f;
                captureCamera.allowHDR = false;
                captureCamera.allowMSAA = false;
                captureCamera.useOcclusionCulling = true;
            }

            if (!readyPosted)
            {
                readyPosted = true;
                Post("visualSensorBridgeReady", new ReadyPayload
                {
                    ready = true,
                    source = "Unity WebGL GPU Direct",
                    cameraCount = CameraIds.Length,
                    gpuDirect = true,
                    qualityProfiles = new[] { "720p", "1080p" },
                    maxTargetFps = 60
                });
            }
        }

        private void ApplyDirectDisplaySettings()
        {
            if (!performanceSettingsApplied)
            {
                previousTargetFrameRate = Application.targetFrameRate;
                previousVSyncCount = QualitySettings.vSyncCount;
                performanceSettingsApplied = true;
            }
            QualitySettings.vSyncCount = 0;
            Application.targetFrameRate = targetFps;

            if (!presentationCamera)
                presentationCamera = Camera.main;
            if (presentationCamera && !presentationMuted)
            {
                presentationCullingMask = presentationCamera.cullingMask;
                presentationClearFlags = presentationCamera.clearFlags;
                presentationBackground = presentationCamera.backgroundColor;
                presentationCamera.cullingMask = 0;
                presentationCamera.clearFlags = CameraClearFlags.SolidColor;
                presentationCamera.backgroundColor = Color.black;
                presentationMuted = true;
            }
        }

        private void RestoreDirectDisplaySettings()
        {
            if (presentationCamera && presentationMuted)
            {
                presentationCamera.cullingMask = presentationCullingMask;
                presentationCamera.clearFlags = presentationClearFlags;
                presentationCamera.backgroundColor = presentationBackground;
            }
            presentationMuted = false;

            if (performanceSettingsApplied)
            {
                Application.targetFrameRate = previousTargetFrameRate;
                QualitySettings.vSyncCount = previousVSyncCount;
                performanceSettingsApplied = false;
            }
        }

        private void RenderDirectViewsIfDue()
        {
            float now = Time.realtimeSinceStartup;
            if (now < nextRenderTime)
                return;

            float interval = 1f / Mathf.Max(15, targetFps);
            nextRenderTime = now + interval;
            EnsureLiveResources();
            if (!captureCamera || !liveTextures[0])
                return;

            float renderStartedAt = Time.realtimeSinceStartup;
            if (displayMode == "focus")
            {
                int focusedIndex = Array.IndexOf(CameraIds, focusedCameraId);
                if (focusedIndex < 0)
                    focusedIndex = 0;
                RenderCameraToTexture(focusedIndex, liveTextures[focusedIndex]);
            }
            else
            {
                for (int index = 0; index < CameraIds.Length; index++)
                    RenderCameraToTexture(index, liveTextures[index]);
            }
            float renderMs = (Time.realtimeSinceStartup - renderStartedAt) * 1000f;
            smoothedRenderMs = smoothedRenderMs <= 0f
                ? renderMs
                : Mathf.Lerp(smoothedRenderMs, renderMs, .18f);
            renderedFramesInWindow++;

            float windowDuration = now - statsWindowStartedAt;
            if (windowDuration >= StatsIntervalSeconds)
            {
                measuredFps = renderedFramesInWindow / Mathf.Max(.001f, windowDuration);
                renderedFramesInWindow = 0;
                statsWindowStartedAt = now;
                EvaluateAdaptiveQuality();
                PostStreamStats();
            }
        }

        private void EvaluateAdaptiveQuality()
        {
            if (requestedQuality != "1080p" || adaptiveFallback)
                return;

            // A background browser tab can deliberately throttle requestAnimationFrame
            // to 1 FPS even when GPU rendering is fast. Use the real render cost,
            // rather than presentation cadence, when deciding whether 1080P is too
            // expensive for this device.
            float frameBudgetMs = 1000f / Mathf.Max(15, targetFps);
            if (smoothedRenderMs > frameBudgetMs * .82f)
                slow1080pWindows++;
            else
                slow1080pWindows = Mathf.Max(0, slow1080pWindows - 1);

            // Six concurrent 1080P cameras are allowed first. Only after four
            // consecutive slow windows do we protect motion stability by
            // transparently falling back to six 720P GPU streams.
            if (slow1080pWindows < 4)
                return;

            adaptiveFallback = true;
            activeQuality = "720p";
            ReleaseLiveResources();
            EnsureLiveResources();
        }

        private void EnsureLiveResources()
        {
            bool useFullHd = activeQuality == "1080p";
            int nextWidth = useFullHd ? FullHdWidth : HdWidth;
            int nextHeight = useFullHd ? FullHdHeight : HdHeight;
            if (liveTextures[0] && liveWidth == nextWidth && liveHeight == nextHeight)
                return;

            ReleaseLiveResources();
            liveWidth = nextWidth;
            liveHeight = nextHeight;
            for (int i = 0; i < liveTextures.Length; i++)
            {
                liveTextures[i] = CreateRenderTexture(
                    liveWidth,
                    liveHeight,
                    "Unity Sensor Live " + DeviceCodes[i]);
                liveTextures[i].Create();
            }
        }

        private static RenderTexture CreateRenderTexture(int width, int height, string name)
        {
            return new RenderTexture(width, height, 16, RenderTextureFormat.ARGB32)
            {
                name = name,
                antiAliasing = 1,
                useMipMap = false,
                autoGenerateMips = false,
                filterMode = FilterMode.Bilinear,
                wrapMode = TextureWrapMode.Clamp
            };
        }

        private void RenderCameraToTexture(int index, RenderTexture target)
        {
            if (!target || !TryGetPose(index, out Vector3 position, out Quaternion rotation, out float fov))
                return;

            ConfigureCaptureCamera(position, rotation, fov);
            captureCamera.targetTexture = target;
            try
            {
                captureCamera.Render();
            }
            finally
            {
                captureCamera.targetTexture = null;
            }
        }

        private void ConfigureCaptureCamera(Vector3 position, Quaternion rotation, float fov)
        {
            Camera source = presentationCamera ? presentationCamera : Camera.main;
            if (source)
            {
                captureCamera.clearFlags = presentationMuted
                    ? presentationClearFlags
                    : source.clearFlags;
                captureCamera.backgroundColor = presentationMuted
                    ? presentationBackground
                    : source.backgroundColor;
                captureCamera.cullingMask = presentationMuted
                    ? presentationCullingMask
                    : source.cullingMask;
                captureCamera.farClipPlane = source.farClipPlane;
            }
            captureCamera.transform.SetPositionAndRotation(position, rotation);
            captureCamera.fieldOfView = fov;
            captureCamera.aspect = 16f / 9f;
        }

        private void OnGUI()
        {
            if (!subscribed || !gpuDirect || displayMode == "off" || !liveTextures[0])
                return;
            if (Event.current.type != EventType.Repaint)
                return;

            GUI.depth = -10000;
            Color previousColor = GUI.color;
            GUI.color = Color.black;
            GUI.DrawTexture(new Rect(0f, 0f, Screen.width, Screen.height), Texture2D.whiteTexture);
            GUI.color = Color.white;

            if (displayMode == "focus")
            {
                int index = Array.IndexOf(CameraIds, focusedCameraId);
                if (index < 0)
                    index = 0;
                DrawTextureFitted(liveTextures[index],
                    new Rect(0f, 0f, Screen.width, Screen.height),
                    false);
            }
            else
            {
                const float gap = 4f;
                float cellWidth = (Screen.width - gap * 4f) / 3f;
                float cellHeight = (Screen.height - gap * 3f) / 2f;
                for (int i = 0; i < liveTextures.Length; i++)
                {
                    int column = i % 3;
                    int row = i / 3;
                    Rect cell = new Rect(
                        gap + column * (cellWidth + gap),
                        gap + row * (cellHeight + gap),
                        cellWidth,
                        cellHeight);
                    DrawTextureFitted(liveTextures[i], cell, true);
                }
            }

            GUI.color = previousColor;
        }

        private static void DrawTextureFitted(Texture texture, Rect bounds, bool crop)
        {
            if (!texture)
                return;
            GUI.DrawTexture(
                bounds,
                texture,
                crop ? ScaleMode.ScaleAndCrop : ScaleMode.ScaleToFit,
                false);
        }

        private void CaptureLegacyFrameIfDue()
        {
            EnsureLegacyCaptureResources();
            float now = Time.realtimeSinceStartup;
            int activeFocusedIndex = Array.IndexOf(CameraIds, focusedCameraId);
            bool prioritizeFocused = !gpuDirect && focusedFps > thumbnailFps + .1f;
            int focusedIndex = prioritizeFocused
                ? activeFocusedIndex
                : -1;
            bool focusedDue = focusedIndex >= 0 && now >= nextCaptureTimes[focusedIndex];
            // The selected camera is already presented by the GPU-direct
            // canvas. Excluding it from JPEG capture keeps the readback budget
            // available for the five visible thumbnail channels.
            int thumbnailIndex = FindDueThumbnail(now, activeFocusedIndex);

            if (focusedDue && (focusedTurn || thumbnailIndex < 0))
            {
                nextCaptureTimes[focusedIndex] = now + 1f / Mathf.Max(1f, focusedFps);
                focusedTurn = false;
                CaptureJpegFrame(focusedIndex, true);
                return;
            }
            if (thumbnailIndex >= 0)
            {
                nextCaptureTimes[thumbnailIndex] = now + 1f / Mathf.Max(.2f, thumbnailFps);
                roundRobinIndex = (thumbnailIndex + 1) % CameraIds.Length;
                focusedTurn = true;
                CaptureJpegFrame(thumbnailIndex, false);
                return;
            }
            if (focusedDue)
            {
                nextCaptureTimes[focusedIndex] = now + 1f / Mathf.Max(1f, focusedFps);
                focusedTurn = false;
                CaptureJpegFrame(focusedIndex, true);
            }
        }

        private int FindDueThumbnail(float now, int focusedIndex)
        {
            for (int offset = 0; offset < CameraIds.Length; offset++)
            {
                int index = (roundRobinIndex + offset) % CameraIds.Length;
                if (index == focusedIndex || now < nextCaptureTimes[index])
                    continue;
                return index;
            }
            return -1;
        }

        private void EnsureLegacyCaptureResources()
        {
            if (!thumbnailRenderTexture)
            {
                thumbnailRenderTexture = CreateRenderTexture(256, 144, "Unity Sensor Thumbnail");
                thumbnailTexture = new Texture2D(256, 144, TextureFormat.RGB24, false);
            }
            if (!focusedRenderTexture)
            {
                focusedRenderTexture = CreateRenderTexture(512, 288, "Unity Sensor Focus");
                focusedTexture = new Texture2D(512, 288, TextureFormat.RGB24, false);
            }
        }

        private void CaptureJpegFrame(int index, bool focused)
        {
            if (!jpegFallback && gpuDirect)
                return;
            if (!TryGetPose(index, out Vector3 position, out Quaternion rotation, out float fov))
                return;

            ConfigureCaptureCamera(position, rotation, fov);
            RenderTexture target = focused ? focusedRenderTexture : thumbnailRenderTexture;
            Texture2D texture = focused ? focusedTexture : thumbnailTexture;
            captureCamera.targetTexture = target;
            RenderTexture previous = RenderTexture.active;
            try
            {
                captureCamera.Render();
                RenderTexture.active = target;
                texture.ReadPixels(new Rect(0, 0, target.width, target.height), 0, 0, false);
                byte[] jpeg = ImageConversion.EncodeToJPG(texture, focused ? 46 : 38);
                if (jpeg == null || jpeg.Length == 0)
                    return;

                sequence++;
                Post("visualSensorFrame", new FramePayload
                {
                    cameraId = CameraIds[index],
                    deviceCode = DeviceCodes[index],
                    viewType = index < 3 ? "DOWN" : "FORWARD",
                    source = "Unity WebGL JPEG Fallback",
                    width = target.width,
                    height = target.height,
                    timestampMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
                    sequence = sequence,
                    jpegBase64 = Convert.ToBase64String(jpeg)
                });
            }
            finally
            {
                RenderTexture.active = previous;
                captureCamera.targetTexture = null;
            }
        }

        private bool TryGetPose(int index, out Vector3 position, out Quaternion rotation, out float fov)
        {
            position = Vector3.zero;
            rotation = Quaternion.identity;
            fov = 55f;

            if (index < 3)
            {
                Transform[] uavs = sensorSuite.uavs;
                if (uavs == null || index >= uavs.Length || !uavs[index])
                    return false;
                Transform uav = uavs[index];
                Vector3 forward = Vector3.ProjectOnPlane(uav.forward, Vector3.up);
                if (forward.sqrMagnitude < .001f)
                    forward = Vector3.ProjectOnPlane(uav.right, Vector3.up);
                if (forward.sqrMagnitude < .001f)
                    forward = Vector3.forward;
                position = uav.position + Vector3.down * Mathf.Max(.9f, sensorSuite.uavCameraHeight);
                rotation = Quaternion.LookRotation(Vector3.down, forward.normalized);
                fov = 70f;
                return true;
            }

            int usvIndex = index - 3;
            Transform[] usvs = sensorSuite.usvs;
            if (usvs == null || usvIndex >= usvs.Length || !usvs[usvIndex])
                return false;
            Transform usv = usvs[usvIndex];
            Vector3 usvForward = usv.right;
            position = usv.position + Vector3.up * Mathf.Max(3.2f, sensorSuite.usvCameraHeight) +
                       usvForward * Mathf.Max(5.4f, sensorSuite.usvCameraForward);
            Vector3 lookPoint = position + usvForward * 28f + Vector3.up * .2f;
            if (sensorSuite.lookAt)
                lookPoint = Vector3.Lerp(lookPoint, sensorSuite.lookAt.position + Vector3.up * 1.5f, .18f);
            rotation = Quaternion.LookRotation((lookPoint - position).normalized, Vector3.up);
            fov = 58f;
            return true;
        }

        private void PostStreamStats()
        {
            Post("visualSensorStreamStats", new StreamStatsPayload
            {
                active = subscribed && gpuDirect && displayMode != "off",
                gpuDirect = gpuDirect,
                displayMode = displayMode,
                requestedQuality = requestedQuality,
                activeQuality = activeQuality,
                focusedCameraId = focusedCameraId,
                cameraCount = CameraIds.Length,
                streamWidth = liveWidth,
                streamHeight = liveHeight,
                targetFps = targetFps,
                measuredFps = Mathf.Round(measuredFps * 10f) / 10f,
                renderMs = Mathf.Round(smoothedRenderMs * 10f) / 10f,
                adaptiveFallback = adaptiveFallback,
                timestampMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()
            });
        }

        private static string NormalizeDisplayMode(string mode)
        {
            string normalized = (mode ?? string.Empty).Trim().ToLowerInvariant();
            return normalized == "focus" || normalized == "off" ? normalized : "grid";
        }

        private static string NormalizeQuality(string quality)
        {
            return string.Equals(
                (quality ?? string.Empty).Trim(),
                "1080p",
                StringComparison.OrdinalIgnoreCase)
                ? "1080p"
                : "720p";
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
            Debug.Log("[UnityVisualSensorBridge] " + json);
#endif
        }

        private void ReleaseLiveResources()
        {
            for (int i = 0; i < liveTextures.Length; i++)
            {
                if (!liveTextures[i])
                    continue;
                liveTextures[i].Release();
                Destroy(liveTextures[i]);
                liveTextures[i] = null;
            }
        }

        private void ReleaseLegacyResources()
        {
            if (thumbnailRenderTexture)
            {
                thumbnailRenderTexture.Release();
                Destroy(thumbnailRenderTexture);
                thumbnailRenderTexture = null;
            }
            if (focusedRenderTexture)
            {
                focusedRenderTexture.Release();
                Destroy(focusedRenderTexture);
                focusedRenderTexture = null;
            }
            if (thumbnailTexture)
            {
                Destroy(thumbnailTexture);
                thumbnailTexture = null;
            }
            if (focusedTexture)
            {
                Destroy(focusedTexture);
                focusedTexture = null;
            }
        }

        private void OnDisable()
        {
            RestoreDirectDisplaySettings();
        }

        private void OnDestroy()
        {
            RestoreDirectDisplaySettings();
            ReleaseLiveResources();
            ReleaseLegacyResources();
            if (captureCamera)
                Destroy(captureCamera.gameObject);
        }
    }
}
