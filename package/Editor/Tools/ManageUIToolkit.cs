#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Xml.Linq;
using MCPForUnity.Editor.Helpers;
using MCPForUnity.Editor.Tools;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;
using UnityEngine.UIElements;

namespace UniCli.Editor.Tools
{
    [McpForUnityTool("manage_ui_toolkit")]
    public static class ManageUIToolkit
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
                    case "list_documents":
                        return ListDocuments();
                    case "list_stylesheets":
                        return ListStylesheets();
                    case "get_document_info":
                        return GetDocumentInfo(@params["path"]?.ToString());
                    case "create_uxml":
                        return CreateTextAsset(
                            @params["path"]?.ToString(),
                            @params["content"]?.ToString(),
                            ".uxml",
                            GenerateDefaultUxmlTemplate(@params["name"]?.ToString())
                        );
                    case "create_uss":
                        return CreateTextAsset(
                            @params["path"]?.ToString(),
                            @params["content"]?.ToString(),
                            ".uss",
                            GenerateDefaultUssTemplate()
                        );
                    case "read_file":
                        return ReadFile(@params["path"]?.ToString());
                    default:
                        return new ErrorResponse(
                            $"Unknown action: '{action}'. Valid actions are: list_documents, list_stylesheets, get_document_info, create_uxml, create_uss, read_file."
                        );
                }
            }
            catch (Exception e)
            {
                return new ErrorResponse($"manage_ui_toolkit action '{action}' failed: {e.Message}");
            }
        }

        private static object ListDocuments()
        {
            string[] guids = AssetDatabase.FindAssets("t:VisualTreeAsset");
            List<object> documents = guids
                .Select(AssetDatabase.GUIDToAssetPath)
                .Where(path => !string.IsNullOrEmpty(path))
                .Select(path => new
                {
                    path,
                    fileName = Path.GetFileName(path),
                })
                .Cast<object>()
                .ToList();

            return new SuccessResponse(
                $"Found {documents.Count} UI Toolkit document(s).",
                new { count = documents.Count, documents }
            );
        }

        private static object ListStylesheets()
        {
            string[] guids = AssetDatabase.FindAssets("t:StyleSheet");
            List<object> stylesheets = guids
                .Select(AssetDatabase.GUIDToAssetPath)
                .Where(path => !string.IsNullOrEmpty(path))
                .Select(path => new
                {
                    path,
                    fileName = Path.GetFileName(path),
                })
                .Cast<object>()
                .ToList();

            return new SuccessResponse(
                $"Found {stylesheets.Count} UI Toolkit stylesheet(s).",
                new { count = stylesheets.Count, stylesheets }
            );
        }

        private static object GetDocumentInfo(string path)
        {
            if (string.IsNullOrEmpty(path))
            {
                return new ErrorResponse("'path' is required for get_document_info.");
            }

            string normalizedPath = NormalizeProjectRelativePath(path);
            VisualTreeAsset document = AssetDatabase.LoadAssetAtPath<VisualTreeAsset>(normalizedPath);
            if (document == null)
            {
                return new ErrorResponse($"No VisualTreeAsset found at '{normalizedPath}'.");
            }

            string text = ReadProjectRelativeText(normalizedPath);
            if (text == null)
            {
                return new ErrorResponse($"Unable to read file contents for '{normalizedPath}'.");
            }

            ParseUxmlMetadata(text, out List<string> referencedStylesheets, out List<string> templateNames);

            return new SuccessResponse(
                $"Document info retrieved for '{normalizedPath}'.",
                new
                {
                    path = normalizedPath,
                    assetName = document.name,
                    referencedStylesheets,
                    templateNames,
                }
            );
        }

        private static object CreateTextAsset(string path, string content, string requiredExtension, string defaultTemplate)
        {
            if (string.IsNullOrEmpty(path))
            {
                return new ErrorResponse("'path' is required.");
            }

            string normalizedPath = NormalizeProjectRelativePath(path);
            if (!normalizedPath.EndsWith(requiredExtension, StringComparison.OrdinalIgnoreCase))
            {
                return new ErrorResponse($"Path must end with '{requiredExtension}'.");
            }

            string absolutePath = GetAbsoluteProjectPath(normalizedPath);
            if (absolutePath == null)
            {
                return new ErrorResponse($"Path '{normalizedPath}' must be under Assets/ or Packages/.");
            }

            string directory = Path.GetDirectoryName(absolutePath);
            if (!string.IsNullOrEmpty(directory) && !Directory.Exists(directory))
            {
                Directory.CreateDirectory(directory);
            }

            string finalContent = string.IsNullOrEmpty(content) ? defaultTemplate : content;
            File.WriteAllText(absolutePath, finalContent, new System.Text.UTF8Encoding(false));
            AssetDatabase.ImportAsset(normalizedPath, ImportAssetOptions.ForceSynchronousImport);
            AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);

            return new SuccessResponse(
                $"Created '{normalizedPath}'.",
                new { path = normalizedPath, length = finalContent.Length }
            );
        }

        private static object ReadFile(string path)
        {
            if (string.IsNullOrEmpty(path))
            {
                return new ErrorResponse("'path' is required for read_file.");
            }

            string normalizedPath = NormalizeProjectRelativePath(path);
            string extension = Path.GetExtension(normalizedPath) ?? string.Empty;
            if (!extension.Equals(".uxml", StringComparison.OrdinalIgnoreCase)
                && !extension.Equals(".uss", StringComparison.OrdinalIgnoreCase))
            {
                return new ErrorResponse("read_file only supports .uxml and .uss files.");
            }

            string text = ReadProjectRelativeText(normalizedPath);
            if (text == null)
            {
                return new ErrorResponse($"File not found at '{normalizedPath}'.");
            }

            return new SuccessResponse(
                $"Read '{normalizedPath}'.",
                new
                {
                    path = normalizedPath,
                    content = text,
                    length = text.Length,
                }
            );
        }

        private static void ParseUxmlMetadata(string uxmlText, out List<string> stylesheets, out List<string> templates)
        {
            stylesheets = new List<string>();
            templates = new List<string>();

            try
            {
                XDocument document = XDocument.Parse(uxmlText);
                IEnumerable<XElement> elements = document.Descendants();

                foreach (XElement element in elements)
                {
                    string localName = element.Name.LocalName;
                    if (string.Equals(localName, "Style", StringComparison.OrdinalIgnoreCase))
                    {
                        string src = element.Attributes().FirstOrDefault(a => a.Name.LocalName == "src")?.Value;
                        if (!string.IsNullOrEmpty(src) && !stylesheets.Contains(src))
                        {
                            stylesheets.Add(src);
                        }
                    }

                    if (string.Equals(localName, "Template", StringComparison.OrdinalIgnoreCase))
                    {
                        string templateName = element.Attributes().FirstOrDefault(a => a.Name.LocalName == "name")?.Value;
                        if (string.IsNullOrEmpty(templateName))
                        {
                            templateName = element.Attributes().FirstOrDefault(a => a.Name.LocalName == "src")?.Value;
                        }

                        if (!string.IsNullOrEmpty(templateName) && !templates.Contains(templateName))
                        {
                            templates.Add(templateName);
                        }
                    }
                }
            }
            catch
            {
                stylesheets = new List<string>();
                templates = new List<string>();
            }
        }

        private static string GenerateDefaultUxmlTemplate(string name)
        {
            string safeName = string.IsNullOrEmpty(name) ? "Root" : name;
            return "<ui:UXML xmlns:ui=\"UnityEngine.UIElements\" xmlns:uie=\"UnityEditor.UIElements\">\n"
                + "    <ui:VisualElement name=\""
                + safeName
                + "\" class=\"root\">\n"
                + "        <ui:Label text=\"Hello UI Toolkit\" />\n"
                + "    </ui:VisualElement>\n"
                + "</ui:UXML>\n";
        }

        private static string GenerateDefaultUssTemplate()
        {
            return ".root {\n"
                + "    flex-grow: 1;\n"
                + "    padding: 8px;\n"
                + "}\n";
        }

        private static string NormalizeProjectRelativePath(string path)
        {
            return path.Replace("\\", "/").Trim();
        }

        private static string ReadProjectRelativeText(string path)
        {
            string absolutePath = GetAbsoluteProjectPath(path);
            return absolutePath != null && File.Exists(absolutePath) ? File.ReadAllText(absolutePath) : null;
        }

        private static string GetAbsoluteProjectPath(string projectRelativePath)
        {
            if (!projectRelativePath.StartsWith("Assets/", StringComparison.Ordinal)
                && !projectRelativePath.StartsWith("Packages/", StringComparison.Ordinal))
            {
                return null;
            }

            return Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), projectRelativePath));
        }
    }
}
#endif
