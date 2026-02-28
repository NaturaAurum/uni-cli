#if UNITY_EDITOR
using System;
using MCPForUnity.Editor.Helpers;
using MCPForUnity.Editor.Services;
using UnityEditor;
using UnityEngine;

public static class UniCliBenchBoot
{
    [InitializeOnLoadMethod]
    public static void AutoStartHttpBridge()
    {
        try
        {
            Debug.Log("[UniCliBenchBoot] Auto-start hook invoked.");
            EditorConfigurationCache.Instance.SetUseHttpTransport(true);
            EditorPrefs.SetString("MCPForUnity.HttpTransportScope", "local");
            EditorPrefs.SetString("MCPForUnity.HttpUrl", "http://127.0.0.1:8080");
            StartHttpBridgeAsync();
        }
        catch (Exception ex)
        {
            Debug.LogError($"[UniCliBenchBoot] Auto-start failed: {ex}");
        }
    }

    private static async void StartHttpBridgeAsync()
    {
        try
        {
            var started = await MCPServiceLocator.Bridge.StartAsync();
            Debug.Log($"[UniCliBenchBoot] Bridge start result: {started}");

            var verify = await MCPServiceLocator.Bridge.VerifyAsync();
            Debug.Log($"[UniCliBenchBoot] Verify: success={verify.Success}, message={verify.Message}");

            if (!started || !verify.Success)
            {
                Debug.LogError(
                    $"[UniCliBenchBoot] HTTP bridge auto-start verify failed. started={started}, verify={verify.Success}, msg={verify.Message}");
                return;
            }

            Debug.Log("[UniCliBenchBoot] Auto-started HTTP bridge.");
        }
        catch (Exception ex)
        {
            Debug.LogError($"[UniCliBenchBoot] Auto-start async failed: {ex}");
        }
    }

    public static void StartHttpBridgeForCi()
    {
        EditorConfigurationCache.Instance.SetUseHttpTransport(true);
        EditorPrefs.SetString("MCPForUnity.HttpTransportScope", "local");
        EditorPrefs.SetString("MCPForUnity.HttpUrl", "http://127.0.0.1:8080");

        var started = MCPServiceLocator.Bridge.StartAsync().GetAwaiter().GetResult();
        Debug.Log($"[UniCliBenchBoot] Bridge start result: {started}");

        var verify = MCPServiceLocator.Bridge.VerifyAsync().GetAwaiter().GetResult();
        Debug.Log($"[UniCliBenchBoot] Verify: success={verify.Success}, message={verify.Message}");

        if (!started || !verify.Success)
        {
            throw new System.Exception($"HTTP bridge start failed. started={started}, verify={verify.Success}, msg={verify.Message}");
        }
    }
}
#endif
