using UnityEngine;
using UnityEngine.Scripting;

namespace UavUsv.PlatformTools
{
    /// <summary>
    /// Web-platform render defaults. This additive tool changes presentation
    /// quality only and does not participate in simulation or vehicle motion.
    /// </summary>
    [Preserve]
    [DefaultExecutionOrder(12000)]
    public sealed class PlatformRenderQualityController : MonoBehaviour
    {
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void Install()
        {
            GameObject existing = GameObject.Find("PlatformRenderQualityController");
            GameObject host = existing
                ? existing
                : new GameObject("PlatformRenderQualityController");
            DontDestroyOnLoad(host);
            if (!host.GetComponent<PlatformRenderQualityController>())
                host.AddComponent<PlatformRenderQualityController>();
        }

        private void OnEnable()
        {
            ApplyQuality();
        }

        private static void ApplyQuality()
        {
            Application.targetFrameRate = 60;
            QualitySettings.vSyncCount = 0;
            QualitySettings.antiAliasing = 4;
            QualitySettings.anisotropicFiltering = AnisotropicFiltering.ForceEnable;
            QualitySettings.globalTextureMipmapLimit = 0;
            QualitySettings.lodBias = Mathf.Max(1.5f, QualitySettings.lodBias);
            QualitySettings.maximumLODLevel = 0;
            Screen.sleepTimeout = SleepTimeout.NeverSleep;
        }
    }
}
