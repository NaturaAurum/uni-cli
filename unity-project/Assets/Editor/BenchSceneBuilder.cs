#if UNITY_EDITOR
using System;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

public static class BenchSceneBuilder
{
    private const string BenchScenesDir = "Assets/BenchScenes";
    private const string BenchScriptsDir = "Assets/BenchScripts";

    [MenuItem("Tools/Bench/Build Small Scene")]
    public static void BuildSmallSceneMenu()
    {
        BuildSmallScene();
    }

    [MenuItem("Tools/Bench/Build Medium Scene")]
    public static void BuildMediumSceneMenu()
    {
        BuildMediumScene();
    }

    [MenuItem("Tools/Bench/Build Large Scene")]
    public static void BuildLargeSceneMenu()
    {
        BuildLargeScene();
    }

    public static void BuildSmallScene()
    {
        BuildScene(
            sceneFileName: "SmallBench.unity",
            objectCount: 5,
            materialCount: 1,
            scriptCount: 0,
            parentMode: ParentMode.Small
        );
    }

    public static void BuildMediumScene()
    {
        BuildScene(
            sceneFileName: "MediumBench.unity",
            objectCount: 50,
            materialCount: 5,
            scriptCount: 10,
            parentMode: ParentMode.Medium
        );
    }

    public static void BuildLargeScene()
    {
        BuildScene(
            sceneFileName: "LargeBench.unity",
            objectCount: 200,
            materialCount: 20,
            scriptCount: 50,
            parentMode: ParentMode.Large
        );
    }

    private enum ParentMode
    {
        Small,
        Medium,
        Large,
    }

    private static void BuildScene(
        string sceneFileName,
        int objectCount,
        int materialCount,
        int scriptCount,
        ParentMode parentMode)
    {
        EnsureFolder(BenchScenesDir);
        EnsureFolder(BenchScriptsDir);

        CleanupNamedAssets(Path.Combine(BenchScenesDir, "Bench_Mat_"), ".mat");
        SyncScriptAssets(scriptCount);

        var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        var materials = CreateMaterials(materialCount);

        switch (parentMode)
        {
            case ParentMode.Small:
                BuildSmallHierarchy(materials);
                break;
            case ParentMode.Medium:
                BuildMediumHierarchy(objectCount, materials);
                break;
            case ParentMode.Large:
                BuildLargeHierarchy(objectCount, materials);
                break;
            default:
                throw new ArgumentOutOfRangeException(nameof(parentMode), parentMode, null);
        }

        var scenePath = $"{BenchScenesDir}/{sceneFileName}";
        EditorSceneManager.SaveScene(scene, scenePath);
        AssetDatabase.SaveAssets();
        AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
        Debug.Log($"[BenchSceneBuilder] Built {sceneFileName} at {scenePath}");
    }

    private static void BuildSmallHierarchy(Material[] materials)
    {
        var parent = new GameObject("Bench_Obj_001");
        parent.transform.position = new Vector3(0f, 0f, 0f);

        var cubeA = CreatePrimitive("Bench_Obj_002", PrimitiveType.Cube, new Vector3(-2f, 0f, 0f), materials[0]);
        var cubeB = CreatePrimitive("Bench_Obj_003", PrimitiveType.Cube, new Vector3(2f, 0f, 0f), materials[0]);
        var sphereA = CreatePrimitive("Bench_Obj_004", PrimitiveType.Sphere, new Vector3(0f, 0f, 2f), materials[0]);
        var sphereB = CreatePrimitive("Bench_Obj_005", PrimitiveType.Sphere, new Vector3(0f, 0f, -2f), materials[0]);

        cubeA.transform.SetParent(parent.transform);
        cubeB.transform.SetParent(parent.transform);
        sphereA.transform.SetParent(parent.transform);
        sphereB.transform.SetParent(parent.transform);
    }

    private static void BuildMediumHierarchy(int objectCount, Material[] materials)
    {
        if (objectCount != 50)
        {
            throw new ArgumentException("Medium benchmark scene must contain exactly 50 objects.");
        }

        var roots = new GameObject[10];
        for (var i = 0; i < roots.Length; i++)
        {
            var obj = new GameObject(FormatObjectName(i + 1));
            obj.transform.position = new Vector3(i * 2f, 0f, 0f);
            roots[i] = obj;
        }

        for (var i = 0; i < 40; i++)
        {
            var index = i + 11;
            var primitive = (i % 2 == 0) ? PrimitiveType.Cube : PrimitiveType.Sphere;
            var obj = CreatePrimitive(
                FormatObjectName(index),
                primitive,
                new Vector3(i % 5, 1f, i / 5),
                materials[i % materials.Length]
            );
            obj.transform.SetParent(roots[i % roots.Length].transform);
        }
    }

    private static void BuildLargeHierarchy(int objectCount, Material[] materials)
    {
        if (objectCount != 200)
        {
            throw new ArgumentException("Large benchmark scene must contain exactly 200 objects.");
        }

        var objects = new GameObject[objectCount + 1];

        for (var i = 1; i <= objectCount; i++)
        {
            var primitive = (i % 2 == 0) ? PrimitiveType.Cube : PrimitiveType.Sphere;
            var obj = CreatePrimitive(
                FormatObjectName(i),
                primitive,
                new Vector3((i % 10) * 1.5f, (i / 10) * 0.2f, (i % 7) * 1.3f),
                materials[(i - 1) % materials.Length]
            );
            objects[i] = obj;
        }

        for (var i = 1; i <= 10; i++)
        {
            objects[i].transform.SetParent(null);
        }

        for (var i = 11; i <= 60; i++)
        {
            var parentIndex = 1 + ((i - 11) % 10);
            objects[i].transform.SetParent(objects[parentIndex].transform);
        }

        for (var i = 61; i <= 200; i++)
        {
            var parentIndex = 11 + ((i - 61) % 50);
            objects[i].transform.SetParent(objects[parentIndex].transform);
        }
    }

    private static Material[] CreateMaterials(int count)
    {
        var materials = new Material[count];
        for (var i = 0; i < count; i++)
        {
            var assetPath = $"{BenchScenesDir}/{FormatMaterialName(i + 1)}.mat";
            var material = new Material(Shader.Find("Standard"));
            var hue = (i * 0.097f) % 1f;
            material.color = Color.HSVToRGB(hue, 0.55f, 0.9f);
            AssetDatabase.CreateAsset(material, assetPath);
            materials[i] = AssetDatabase.LoadAssetAtPath<Material>(assetPath);
        }

        return materials;
    }

    private static GameObject CreatePrimitive(string name, PrimitiveType primitiveType, Vector3 position, Material material)
    {
        var go = GameObject.CreatePrimitive(primitiveType);
        go.name = name;
        go.transform.position = position;

        var renderer = go.GetComponent<Renderer>();
        if (renderer != null)
        {
            renderer.sharedMaterial = material;
        }

        return go;
    }

    private static void SyncScriptAssets(int scriptCount)
    {
        CleanupNamedAssets(Path.Combine(BenchScriptsDir, "Bench_Script_"), ".cs");

        for (var i = 1; i <= scriptCount; i++)
        {
            var className = FormatScriptName(i);
            var scriptPath = $"{BenchScriptsDir}/{className}.cs";
            var contents =
                "using UnityEngine;\n\n" +
                $"public sealed class {className} : MonoBehaviour\n" +
                "{\n" +
                "}\n";
            File.WriteAllText(scriptPath, contents);
        }
    }

    private static void CleanupNamedAssets(string assetPrefixPath, string extension)
    {
        var projectRoot = Path.GetDirectoryName(Application.dataPath) ?? string.Empty;
        var relativePrefix = assetPrefixPath.Replace("\\", "/");
        var physicalPrefix = Path.Combine(projectRoot, relativePrefix).Replace("\\", "/");
        var directoryPath = Path.GetDirectoryName(physicalPrefix);
        if (string.IsNullOrEmpty(directoryPath) || !Directory.Exists(directoryPath))
        {
            return;
        }

        var prefixName = Path.GetFileName(physicalPrefix);
        var files = Directory.GetFiles(directoryPath, "*" + extension, SearchOption.TopDirectoryOnly);
        foreach (var filePath in files)
        {
            var fileName = Path.GetFileNameWithoutExtension(filePath);
            if (!fileName.StartsWith(prefixName, StringComparison.Ordinal))
            {
                continue;
            }

            var normalized = filePath.Replace("\\", "/");
            var rel = "Assets" + normalized.Substring(Application.dataPath.Replace("\\", "/").Length);
            AssetDatabase.DeleteAsset(rel);
        }
    }

    private static void EnsureFolder(string assetPath)
    {
        if (AssetDatabase.IsValidFolder(assetPath))
        {
            return;
        }

        var parts = assetPath.Split('/');
        var current = parts[0];
        for (var i = 1; i < parts.Length; i++)
        {
            var next = current + "/" + parts[i];
            if (!AssetDatabase.IsValidFolder(next))
            {
                AssetDatabase.CreateFolder(current, parts[i]);
            }

            current = next;
        }
    }

    private static string FormatObjectName(int index)
    {
        return $"Bench_Obj_{index:000}";
    }

    private static string FormatMaterialName(int index)
    {
        return $"Bench_Mat_{index:000}";
    }

    private static string FormatScriptName(int index)
    {
        return $"Bench_Script_{index:000}";
    }
}
#endif
