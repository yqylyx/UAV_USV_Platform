using System;
using System.Runtime.InteropServices;
using UnityEngine;

namespace UavUsv.PlatformTools
{
    /// <summary>
    /// Browser-only visual sensor adapter. It reuses the device transforms that
    /// already drive SensorViewPip and exports six local Unity camera views to
    /// Vue. Mission and vehicle behaviour are never modified.
    /// </summary>
    public sealed class UnityVisualSensorBridge : MonoBehaviour
    {
        [Serializable]
        private sealed class SubscriptionPayload
        {
            public bool enabled;
            public string focusedCameraId;
            public float thumbnailFps = 1f;
            public float focusedFps = 4f;
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

#if UNITY_WEBGL && !UNITY_EDITOR
        [DllImport("__Internal")]
        private static extern void VueWebGlPostMessage(string message);
#endif

        private UavUsv.SensorViewPip sensorSuite;
        private Camera captureCamera;
        private RenderTexture thumbnailRenderTexture;
        private RenderTexture focusedRenderTexture;
        private Texture2D thumbnailTexture;
        private Texture2D focusedTexture;
        private readonly float[] nextCaptureTimes = new float[6];
        private bool subscribed;
        private string focusedCameraId = "uav_01";
        private float thumbnailFps = 1f;
        private float focusedFps = 4f;
        private int sequence;
        private int roundRobinIndex;
        private bool focusedTurn = true;
        private bool readyPosted;

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

            float now = Time.realtimeSinceStartup;
            bool prioritizeFocused = focusedFps > thumbnailFps + .1f;
            int focusedIndex = prioritizeFocused
                ? Array.IndexOf(CameraIds, focusedCameraId)
                : -1;
            bool focusedDue = focusedIndex >= 0 && now >= nextCaptureTimes[focusedIndex];
            int thumbnailIndex = FindDueThumbnail(now, focusedIndex);

            if (focusedDue && (focusedTurn || thumbnailIndex < 0))
            {
                nextCaptureTimes[focusedIndex] = now + 1f / Mathf.Max(1f, focusedFps);
                focusedTurn = false;
                Capture(focusedIndex, true);
                return;
            }

            if (thumbnailIndex >= 0)
            {
                nextCaptureTimes[thumbnailIndex] = now + 1f / Mathf.Max(.2f, thumbnailFps);
                roundRobinIndex = (thumbnailIndex + 1) % CameraIds.Length;
                focusedTurn = true;
                Capture(thumbnailIndex, false);
                return;
            }

            if (focusedDue)
            {
                nextCaptureTimes[focusedIndex] = now + 1f / Mathf.Max(1f, focusedFps);
                focusedTurn = false;
                Capture(focusedIndex, true);
            }
        }

        private int FindDueThumbnail(float now, int focusedIndex)
        {
            for (int offset = 0; offset < CameraIds.Length; offset++)
            {
                int index = (roundRobinIndex + offset) % CameraIds.Length;
                if (index == focusedIndex)
                    continue;
                if (now < nextCaptureTimes[index])
                    continue;
                return index;
            }
            return -1;
        }

        public void ReceiveFromVue(string json)
        {
            try
            {
                IncomingMessage message = JsonUtility.FromJson<IncomingMessage>(json);
                if (message == null ||
                    !string.Equals(message.type, "visualSensorSubscribe", StringComparison.OrdinalIgnoreCase))
                    return;

                SubscriptionPayload payload = message.payload ?? new SubscriptionPayload();
                subscribed = payload.enabled;
                if (Array.IndexOf(CameraIds, payload.focusedCameraId) >= 0)
                    focusedCameraId = payload.focusedCameraId;
                thumbnailFps = Mathf.Clamp(payload.thumbnailFps <= 0f ? 1f : payload.thumbnailFps, .2f, 2f);
                focusedFps = Mathf.Clamp(payload.focusedFps <= 0f ? 4f : payload.focusedFps, 1f, 8f);
                if (subscribed)
                {
                    float immediate = Time.realtimeSinceStartup - 1f;
                    for (int i = 0; i < nextCaptureTimes.Length; i++)
                        nextCaptureTimes[i] = immediate;
                }
            }
            catch (Exception exception)
            {
                Debug.LogWarning("Unity visual sensor subscription rejected: " + exception.Message);
            }
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
            }

            EnsureCaptureResources();
            if (!readyPosted)
            {
                readyPosted = true;
                Post("visualSensorBridgeReady", new ReadyPayload
                {
                    ready = true,
                    source = "Unity WebGL",
                    cameraCount = CameraIds.Length
                });
            }
        }

        private void EnsureCaptureResources()
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

        private static RenderTexture CreateRenderTexture(int width, int height, string name)
        {
            return new RenderTexture(width, height, 16, RenderTextureFormat.ARGB32)
            {
                name = name,
                antiAliasing = 1,
                useMipMap = false,
                autoGenerateMips = false
            };
        }

        private void Capture(int index, bool focused)
        {
            if (!TryGetPose(index, out Vector3 position, out Quaternion rotation, out float fov))
                return;

            Camera main = Camera.main;
            if (main)
            {
                captureCamera.clearFlags = main.clearFlags;
                captureCamera.backgroundColor = main.backgroundColor;
                captureCamera.cullingMask = main.cullingMask;
                captureCamera.farClipPlane = main.farClipPlane;
            }
            captureCamera.transform.SetPositionAndRotation(position, rotation);
            captureCamera.fieldOfView = fov;

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
                    source = "Unity WebGL",
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
                position = uav.position + Vector3.down * Mathf.Max(1.4f, sensorSuite.uavCameraDrop);
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

        private void OnDestroy()
        {
            if (thumbnailRenderTexture)
            {
                thumbnailRenderTexture.Release();
                Destroy(thumbnailRenderTexture);
            }
            if (focusedRenderTexture)
            {
                focusedRenderTexture.Release();
                Destroy(focusedRenderTexture);
            }
            if (thumbnailTexture)
                Destroy(thumbnailTexture);
            if (focusedTexture)
                Destroy(focusedTexture);
            if (captureCamera)
                Destroy(captureCamera.gameObject);
        }
    }
}
