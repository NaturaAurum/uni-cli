#if UNITY_EDITOR

using UnityEditor;
using UnityEngine;
using MCPForUnity.Editor.Services.Transport.Transports;

namespace UniCli.Editor
{
    /// <summary>Ensures StdioBridge TCP listener starts on domain reload.</summary>
    [InitializeOnLoad]
    public static class StdioBridgeAutoStart
    {
        static StdioBridgeAutoStart()
        {
            bool useHttp = EditorPrefs.GetBool("MCPForUnity.UseHttpTransport", true);
            if (useHttp)
            {
                EditorPrefs.SetBool("MCPForUnity.UseHttpTransport", false);
            }

            if (!StdioBridgeHost.IsRunning)
            {
                EditorApplication.delayCall += () =>
                {
                    if (!StdioBridgeHost.IsRunning)
                    {
                        StdioBridgeHost.Start();
                    }
                };
            }
        }
    }
}

#endif
