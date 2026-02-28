#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using MCPForUnity.Editor.Helpers;
using MCPForUnity.Editor.Tools;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;

namespace UniCli.Editor.Tools
{
    [McpForUnityTool("manage_shader_graph")]
    public static class ManageShaderGraph
    {
        public static object HandleCommand(JObject @params)
        {
            string action = @params["action"]?.ToString()?.ToLowerInvariant();
            if (string.IsNullOrEmpty(action))
            {
                return new ErrorResponse("Action parameter is required.");
            }

            try
            {
                switch (action)
                {
                    case "list_graphs":
                        return ListGraphs();
                    case "get_graph_info":
                        return GetGraphInfo(@params["path"]?.ToString());
                    case "create_shader":
                        return CreateShader(
                            @params["path"]?.ToString(),
                            @params["name"]?.ToString(),
                            @params["content"]?.ToString()
                        );
                    case "compile_info":
                        return GetCompileInfo(@params["path"]?.ToString());
                    case "read_source":
                        return ReadSource(@params["path"]?.ToString());
                    case "list_variants":
                        return ListVariants(@params["path"]?.ToString());
                    default:
                        return new ErrorResponse(
                            $"Unknown action: '{action}'. Valid actions are: list_graphs, get_graph_info, create_shader, compile_info, read_source, list_variants."
                        );
                }
            }
            catch (Exception e)
            {
                return new ErrorResponse($"manage_shader_graph action '{action}' failed: {e.Message}");
            }
        }

        private static object ListGraphs()
        {
            string[] guids = AssetDatabase.FindAssets("shadergraph");
            List<object> graphs = guids
                .Select(AssetDatabase.GUIDToAssetPath)
                .Where(path => !string.IsNullOrEmpty(path) && path.EndsWith(".shadergraph", StringComparison.OrdinalIgnoreCase))
                .Distinct()
                .Select(path => new
                {
                    path,
                    fileName = Path.GetFileName(path),
                })
                .Cast<object>()
                .ToList();

            return new SuccessResponse(
                $"Found {graphs.Count} Shader Graph asset(s).",
                new { count = graphs.Count, graphs }
            );
        }

        private static object GetGraphInfo(string path)
        {
            if (string.IsNullOrEmpty(path))
            {
                return new ErrorResponse("'path' is required for get_graph_info.");
            }

            string normalizedPath = NormalizeAssetPath(path);
            if (!normalizedPath.EndsWith(".shadergraph", StringComparison.OrdinalIgnoreCase))
            {
                return new ErrorResponse("get_graph_info expects a .shadergraph file path.");
            }

            string absolutePath = GetAbsolutePath(normalizedPath);
            if (absolutePath == null || !File.Exists(absolutePath))
            {
                return new ErrorResponse($"Shader Graph file not found at '{normalizedPath}'.");
            }

            string jsonText = File.ReadAllText(absolutePath);
            JObject graphJson;
            try
            {
                graphJson = JObject.Parse(jsonText);
            }
            catch (Exception e)
            {
                return new ErrorResponse($"Failed to parse Shader Graph JSON: {e.Message}");
            }

            int nodeCount = CountGraphNodes(graphJson);
            List<object> properties = ExtractGraphProperties(graphJson);
            List<string> targets = ExtractTargets(graphJson);

            return new SuccessResponse(
                $"Shader Graph info retrieved for '{normalizedPath}'.",
                new
                {
                    path = normalizedPath,
                    nodeCount,
                    propertyCount = properties.Count,
                    properties,
                    targets,
                }
            );
        }

        private static object CreateShader(string path, string name, string content)
        {
            if (string.IsNullOrEmpty(path))
            {
                return new ErrorResponse("'path' is required for create_shader.");
            }

            string normalizedPath = NormalizeAssetPath(path);
            if (!normalizedPath.EndsWith(".shader", StringComparison.OrdinalIgnoreCase))
            {
                return new ErrorResponse("create_shader expects a .shader path.");
            }

            string absolutePath = GetAbsolutePath(normalizedPath);
            if (absolutePath == null)
            {
                return new ErrorResponse("create_shader path must be under Assets/ or Packages/.");
            }

            string directory = Path.GetDirectoryName(absolutePath);
            if (!string.IsNullOrEmpty(directory) && !Directory.Exists(directory))
            {
                Directory.CreateDirectory(directory);
            }

            string shaderName = string.IsNullOrEmpty(name)
                ? Path.GetFileNameWithoutExtension(normalizedPath)
                : name;
            string finalContent = string.IsNullOrEmpty(content)
                ? GenerateDefaultShader(shaderName)
                : content;

            File.WriteAllText(absolutePath, finalContent, new System.Text.UTF8Encoding(false));
            AssetDatabase.ImportAsset(normalizedPath, ImportAssetOptions.ForceSynchronousImport);
            AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);

            return new SuccessResponse(
                $"Shader created at '{normalizedPath}'.",
                new { path = normalizedPath, shaderName }
            );
        }

        private static object GetCompileInfo(string path)
        {
            Shader shader = ResolveShader(path, out string resolvedPath, out ErrorResponse error);
            if (shader == null)
            {
                return error;
            }

            List<object> messages = GetShaderMessages(shader);
            int variantCount = GetShaderVariantCount(shader);
            int propertyCount = ShaderUtil.GetPropertyCount(shader);

            return new SuccessResponse(
                $"Compilation info retrieved for shader '{shader.name}'.",
                new
                {
                    path = resolvedPath,
                    shader = shader.name,
                    propertyCount,
                    variantCount,
                    messageCount = messages.Count,
                    messages,
                }
            );
        }

        private static object ReadSource(string path)
        {
            if (string.IsNullOrEmpty(path))
            {
                return new ErrorResponse("'path' is required for read_source.");
            }

            string normalizedPath = NormalizeAssetPath(path);
            string absolutePath = GetAbsolutePath(normalizedPath);
            if (absolutePath == null || !File.Exists(absolutePath))
            {
                return new ErrorResponse($"File not found at '{normalizedPath}'.");
            }

            string source = File.ReadAllText(absolutePath);
            return new SuccessResponse(
                $"Read source from '{normalizedPath}'.",
                new
                {
                    path = normalizedPath,
                    content = source,
                    length = source.Length,
                }
            );
        }

        private static object ListVariants(string path)
        {
            Shader shader = ResolveShader(path, out string resolvedPath, out ErrorResponse error);
            if (shader == null)
            {
                return error;
            }

            int variantCount = GetShaderVariantCount(shader);
            List<object> snippets = GetKeywordSpace(shader)
                .Take(32)
                .Select(keyword => new { keyword })
                .Cast<object>()
                .ToList();

            return new SuccessResponse(
                $"Variant info retrieved for shader '{shader.name}'.",
                new
                {
                    path = resolvedPath,
                    shader = shader.name,
                    variantCount,
                    keywordCount = snippets.Count,
                    keywords = snippets,
                }
            );
        }

        private static Shader ResolveShader(string path, out string resolvedPath, out ErrorResponse error)
        {
            resolvedPath = null;
            error = null;

            if (string.IsNullOrEmpty(path))
            {
                error = new ErrorResponse("'path' is required.");
                return null;
            }

            resolvedPath = NormalizeAssetPath(path);
            UnityEngine.Object mainAsset = AssetDatabase.LoadMainAssetAtPath(resolvedPath);
            if (mainAsset is Shader directShader)
            {
                return directShader;
            }

            UnityEngine.Object[] allAssets = AssetDatabase.LoadAllAssetsAtPath(resolvedPath);
            Shader nestedShader = allAssets.OfType<Shader>().FirstOrDefault();
            if (nestedShader != null)
            {
                return nestedShader;
            }

            if (resolvedPath.EndsWith(".shader", StringComparison.OrdinalIgnoreCase))
            {
                string shaderName = Path.GetFileNameWithoutExtension(resolvedPath);
                Shader found = Shader.Find(shaderName);
                if (found != null)
                {
                    return found;
                }
            }

            error = new ErrorResponse($"No shader could be resolved from '{resolvedPath}'.");
            return null;
        }

        private static int CountGraphNodes(JObject graphJson)
        {
            if (graphJson == null)
            {
                return 0;
            }

            int objectIdCount = graphJson
                .Descendants()
                .OfType<JProperty>()
                .Count(property => property.Name == "m_ObjectId");
            return objectIdCount;
        }

        private static List<object> ExtractGraphProperties(JObject graphJson)
        {
            List<object> properties = new List<object>();
            HashSet<string> seen = new HashSet<string>(StringComparer.Ordinal);
            if (graphJson == null)
            {
                return properties;
            }

            IEnumerable<JObject> propertyObjects = graphJson
                .Descendants()
                .OfType<JObject>()
                .Where(obj =>
                    obj.Property("m_Name") != null
                    && (obj.Property("m_Value") != null || obj.Property("m_DefaultValue") != null || obj.Property("m_Type") != null));

            foreach (JObject propertyObject in propertyObjects)
            {
                string name = propertyObject["m_Name"]?.ToString();
                if (string.IsNullOrEmpty(name))
                {
                    continue;
                }

                string type = propertyObject["m_Type"]?.ToString()
                    ?? propertyObject["m_Value"]?["m_Type"]?.ToString()
                    ?? "Unknown";
                string reference = propertyObject["m_ReferenceName"]?.ToString() ?? propertyObject["m_RefName"]?.ToString();

                if (seen.Add(name))
                {
                    properties.Add(new
                    {
                        name,
                        type,
                        reference,
                    });
                }
            }

            return properties;
        }

        private static List<string> ExtractTargets(JObject graphJson)
        {
            List<string> targets = new List<string>();
            if (graphJson == null)
            {
                return targets;
            }

            foreach (JProperty property in graphJson.Descendants().OfType<JProperty>())
            {
                if (property.Name == "m_ActiveTargets" && property.Value is JArray targetArray)
                {
                    foreach (JToken target in targetArray)
                    {
                        string value = target["m_Id"]?.ToString() ?? target["m_Type"]?.ToString() ?? target.ToString();
                        if (!string.IsNullOrEmpty(value) && !targets.Contains(value))
                        {
                            targets.Add(value);
                        }
                    }
                }
            }

            return targets;
        }

        private static List<object> GetShaderMessages(Shader shader)
        {
            List<object> result = new List<object>();

            MethodInfo getMessages = typeof(ShaderUtil)
                .GetMethods(BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic)
                .FirstOrDefault(method => method.Name == "GetShaderMessages" && method.GetParameters().Length == 1);
            if (getMessages == null)
            {
                return result;
            }

            object value = getMessages.Invoke(null, new object[] { shader });
            if (!(value is Array messageArray))
            {
                return result;
            }

            foreach (object message in messageArray)
            {
                if (message == null)
                {
                    continue;
                }

                Type type = message.GetType();
                result.Add(new
                {
                    message = GetFieldOrProperty(type, message, "message"),
                    severity = GetFieldOrProperty(type, message, "severity"),
                    platform = GetFieldOrProperty(type, message, "platform"),
                    file = GetFieldOrProperty(type, message, "file"),
                    line = GetFieldOrProperty(type, message, "line"),
                });
            }

            return result;
        }

        private static int GetShaderVariantCount(Shader shader)
        {
            MethodInfo variantMethod = typeof(ShaderUtil)
                .GetMethods(BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic)
                .FirstOrDefault(method =>
                    method.Name == "GetVariantCount"
                    && method.GetParameters().Length == 2
                    && method.GetParameters()[0].ParameterType == typeof(Shader)
                    && method.GetParameters()[1].ParameterType == typeof(bool));
            if (variantMethod != null)
            {
                object value = variantMethod.Invoke(null, new object[] { shader, true });
                return value is int intValue ? intValue : 0;
            }

            MethodInfo legacyVariantMethod = typeof(ShaderUtil)
                .GetMethods(BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic)
                .FirstOrDefault(method => method.Name == "GetVariantCount" && method.GetParameters().Length == 1);
            if (legacyVariantMethod != null)
            {
                object value = legacyVariantMethod.Invoke(null, new object[] { shader });
                return value is int intValue ? intValue : 0;
            }

            return 0;
        }

        private static IEnumerable<string> GetKeywordSpace(Shader shader)
        {
            int propertyCount = ShaderUtil.GetPropertyCount(shader);
            for (int i = 0; i < propertyCount; i++)
            {
                string name = ShaderUtil.GetPropertyName(shader, i);
                if (!string.IsNullOrEmpty(name))
                {
                    yield return name;
                }
            }
        }

        private static object GetFieldOrProperty(Type type, object instance, string name)
        {
            FieldInfo field = type.GetField(name, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.IgnoreCase);
            if (field != null)
            {
                return field.GetValue(instance);
            }

            PropertyInfo property = type.GetProperty(name, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.IgnoreCase);
            return property?.GetValue(instance, null);
        }

        private static string NormalizeAssetPath(string path)
        {
            return path.Replace("\\", "/").Trim();
        }

        private static string GetAbsolutePath(string assetPath)
        {
            if (!assetPath.StartsWith("Assets/", StringComparison.Ordinal)
                && !assetPath.StartsWith("Packages/", StringComparison.Ordinal))
            {
                return null;
            }

            return Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), assetPath));
        }

        private static string GenerateDefaultShader(string shaderName)
        {
            return "Shader \""
                + shaderName
                + "\"\n{\n"
                + "    Properties\n    {\n"
                + "        _BaseColor (\"Base Color\", Color) = (1,1,1,1)\n"
                + "    }\n"
                + "    SubShader\n    {\n"
                + "        Tags { \"RenderType\"=\"Opaque\" }\n"
                + "        Pass\n        {\n"
                + "            HLSLPROGRAM\n"
                + "            #pragma vertex vert\n"
                + "            #pragma fragment frag\n"
                + "\n"
                + "            struct Attributes { float4 positionOS : POSITION; };\n"
                + "            struct Varyings { float4 positionCS : SV_POSITION; };\n"
                + "            float4 _BaseColor;\n"
                + "\n"
                + "            Varyings vert(Attributes v)\n            {\n"
                + "                Varyings o;\n"
                + "                o.positionCS = UnityObjectToClipPos(v.positionOS);\n"
                + "                return o;\n"
                + "            }\n"
                + "\n"
                + "            float4 frag(Varyings i) : SV_Target\n            {\n"
                + "                return _BaseColor;\n"
                + "            }\n"
                + "            ENDHLSL\n"
                + "        }\n"
                + "    }\n"
                + "}\n";
        }
    }
}
#endif
