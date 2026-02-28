#if UNITY_EDITOR
using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using MCPForUnity.Editor.Helpers;
using MCPForUnity.Editor.Tools;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;

namespace UniCli.Editor.Tools
{
#if UNITY_2021_3_OR_NEWER
    [McpForUnityTool("manage_addressables")]
    public static class ManageAddressables
    {
        public static object HandleCommand(JObject @params)
        {
            string action = @params["action"]?.ToString()?.ToLowerInvariant();
            if (string.IsNullOrEmpty(action))
            {
                return new ErrorResponse("Action parameter is required.");
            }

            if (!TryGetAddressablesContext(out AddressablesContext context, out ErrorResponse error))
            {
                return error;
            }

            try
            {
                switch (action)
                {
                    case "list_groups":
                        return ListGroups(context);
                    case "create_group":
                        return CreateGroup(context, @params["name"]?.ToString());
                    case "add_entry":
                        return AddEntry(context, @params["path"]?.ToString(), @params["group"]?.ToString());
                    case "remove_entry":
                        return RemoveEntry(
                            context,
                            @params["guid"]?.ToString(),
                            @params["path"]?.ToString(),
                            @params["group"]?.ToString()
                        );
                    case "set_label":
                        return SetLabel(
                            context,
                            @params["label"]?.ToString(),
                            @params["enabled"]?.ToObject<bool?>() ?? true,
                            @params["guid"]?.ToString(),
                            @params["path"]?.ToString()
                        );
                    case "get_settings":
                        return GetSettings(context);
                    case "build":
                        return BuildAddressables(context);
                    default:
                        return new ErrorResponse(
                            $"Unknown action: '{action}'. Valid actions are: list_groups, create_group, add_entry, remove_entry, set_label, get_settings, build."
                        );
                }
            }
            catch (Exception e)
            {
                return new ErrorResponse($"manage_addressables action '{action}' failed: {e.Message}");
            }
        }

        private static object ListGroups(AddressablesContext context)
        {
            IList groups = GetGroups(context.Settings);
            List<object> groupData = new List<object>();

            foreach (object group in groups)
            {
                if (group == null)
                {
                    continue;
                }

                string groupName = GetStringProperty(group, "Name") ?? "<unnamed>";
                IList entries = GetEntries(group);

                groupData.Add(new
                {
                    name = groupName,
                    guid = GetStringProperty(group, "Guid"),
                    readOnly = GetBoolProperty(group, "ReadOnly"),
                    entryCount = entries.Count,
                });
            }

            return new SuccessResponse(
                $"Found {groupData.Count} Addressables group(s).",
                new { count = groupData.Count, groups = groupData }
            );
        }

        private static object CreateGroup(AddressablesContext context, string groupName)
        {
            if (string.IsNullOrEmpty(groupName))
            {
                return new ErrorResponse("'name' is required for create_group.");
            }

            object existing = InvokeInstanceMethod(context.Settings, "FindGroup", groupName);
            if (existing != null)
            {
                return new ErrorResponse($"Addressables group '{groupName}' already exists.");
            }

            object created = InvokeCreateGroup(context.Settings, context.GroupSchemaType, groupName);
            if (created == null)
            {
                return new ErrorResponse("Failed to create Addressables group.");
            }

            EditorUtility.SetDirty(context.Settings as UnityEngine.Object);
            AssetDatabase.SaveAssets();

            return new SuccessResponse($"Created Addressables group '{groupName}'.");
        }

        private static object AddEntry(AddressablesContext context, string path, string groupName)
        {
            if (string.IsNullOrEmpty(path))
            {
                return new ErrorResponse("'path' is required for add_entry.");
            }

            string normalizedPath = path.Replace("\\", "/");
            string guid = AssetDatabase.AssetPathToGUID(normalizedPath);
            if (string.IsNullOrEmpty(guid))
            {
                return new ErrorResponse($"No asset found at '{normalizedPath}'.");
            }

            if (string.IsNullOrEmpty(groupName))
            {
                return new ErrorResponse("'group' is required for add_entry.");
            }

            object group = InvokeInstanceMethod(context.Settings, "FindGroup", groupName);
            if (group == null)
            {
                return new ErrorResponse($"Addressables group '{groupName}' not found.");
            }

            MethodInfo createOrMoveMethod = context.SettingsType
                .GetMethods(BindingFlags.Instance | BindingFlags.Public)
                .FirstOrDefault(m =>
                    m.Name == "CreateOrMoveEntry"
                    && m.GetParameters().Length >= 2
                    && m.GetParameters()[0].ParameterType == typeof(string)
                    && m.GetParameters()[1].ParameterType.IsAssignableFrom(context.GroupType));

            if (createOrMoveMethod == null)
            {
                return new ErrorResponse("Addressables API mismatch: CreateOrMoveEntry method was not found.");
            }

            object[] args = BuildDefaultArguments(createOrMoveMethod.GetParameters());
            args[0] = guid;
            args[1] = group;
            object entry = createOrMoveMethod.Invoke(context.Settings, args);

            if (entry == null)
            {
                return new ErrorResponse("Failed to create or move Addressables entry.");
            }

            EditorUtility.SetDirty(context.Settings as UnityEngine.Object);
            AssetDatabase.SaveAssets();

            return new SuccessResponse(
                $"Added '{normalizedPath}' to group '{groupName}'.",
                new { guid, path = normalizedPath, group = groupName }
            );
        }

        private static object RemoveEntry(AddressablesContext context, string guid, string path, string groupName)
        {
            string targetGuid = !string.IsNullOrEmpty(guid) ? guid : AssetDatabase.AssetPathToGUID(path ?? string.Empty);
            if (string.IsNullOrEmpty(targetGuid))
            {
                return new ErrorResponse("'guid' or a valid 'path' is required for remove_entry.");
            }

            object entry = FindAssetEntry(context, targetGuid);
            if (entry == null)
            {
                return new ErrorResponse($"Addressables entry '{targetGuid}' not found.");
            }

            object parentGroup = GetPropertyValue(entry, "parentGroup");
            if (parentGroup == null && !string.IsNullOrEmpty(groupName))
            {
                parentGroup = InvokeInstanceMethod(context.Settings, "FindGroup", groupName);
            }

            if (parentGroup == null)
            {
                return new ErrorResponse("Could not resolve the entry's group.");
            }

            object removed = InvokeInstanceMethod(parentGroup, "RemoveAssetEntry", entry);
            bool success = removed is bool removedBool ? removedBool : removed != null;
            if (!success)
            {
                return new ErrorResponse($"Failed to remove entry '{targetGuid}'.");
            }

            EditorUtility.SetDirty(context.Settings as UnityEngine.Object);
            AssetDatabase.SaveAssets();

            return new SuccessResponse($"Removed Addressables entry '{targetGuid}'.");
        }

        private static object SetLabel(AddressablesContext context, string label, bool enabled, string guid, string path)
        {
            if (string.IsNullOrEmpty(label))
            {
                return new ErrorResponse("'label' is required for set_label.");
            }

            EnsureLabelExists(context.Settings, label);

            List<object> targets = ResolveTargetEntries(context, guid, path);
            if (targets.Count == 0)
            {
                return new ErrorResponse("No matching Addressables entries found for set_label.");
            }

            int updated = 0;
            foreach (object entry in targets)
            {
                if (InvokeSetLabel(entry, label, enabled))
                {
                    updated++;
                }
            }

            EditorUtility.SetDirty(context.Settings as UnityEngine.Object);
            AssetDatabase.SaveAssets();

            return new SuccessResponse(
                $"Updated label '{label}' on {updated} entr{(updated == 1 ? "y" : "ies") }.",
                new { label, enabled, updated }
            );
        }

        private static object GetSettings(AddressablesContext context)
        {
            IList groups = GetGroups(context.Settings);
            List<object> groupSummaries = new List<object>();
            int totalEntries = 0;

            foreach (object group in groups)
            {
                if (group == null)
                {
                    continue;
                }

                IList entries = GetEntries(group);
                totalEntries += entries.Count;

                groupSummaries.Add(new
                {
                    name = GetStringProperty(group, "Name"),
                    entryCount = entries.Count,
                });
            }

            return new SuccessResponse(
                "Retrieved Addressables settings.",
                new
                {
                    hasSettings = context.Settings != null,
                    defaultGroup = GetStringProperty(GetPropertyValue(context.Settings, "DefaultGroup"), "Name"),
                    activeProfileId = GetStringProperty(context.Settings, "activeProfileId"),
                    groupCount = groups.Count,
                    entryCount = totalEntries,
                    groups = groupSummaries,
                }
            );
        }

        private static object BuildAddressables(AddressablesContext context)
        {
            MethodInfo buildMethod = context.SettingsType.GetMethods(BindingFlags.Public | BindingFlags.Static)
                .FirstOrDefault(m => m.Name == "BuildPlayerContent" && m.GetParameters().Length == 0);
            if (buildMethod == null)
            {
                return new ErrorResponse("Addressables API mismatch: BuildPlayerContent() was not found.");
            }

            buildMethod.Invoke(null, null);
            AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
            return new SuccessResponse("Addressables build triggered.");
        }

        private static bool TryGetAddressablesContext(out AddressablesContext context, out ErrorResponse error)
        {
            context = default;
            error = null;

            Type settingsDefaultObjectType = Type.GetType(
                "UnityEditor.AddressableAssets.Settings.AddressableAssetSettingsDefaultObject, Unity.Addressables.Editor"
            );
            Type settingsType = Type.GetType(
                "UnityEditor.AddressableAssets.Settings.AddressableAssetSettings, Unity.Addressables.Editor"
            );
            Type groupType = Type.GetType(
                "UnityEditor.AddressableAssets.Settings.AddressableAssetGroup, Unity.Addressables.Editor"
            );
            Type entryType = Type.GetType(
                "UnityEditor.AddressableAssets.Settings.AddressableAssetEntry, Unity.Addressables.Editor"
            );
            Type groupSchemaType = Type.GetType(
                "UnityEditor.AddressableAssets.Settings.AddressableAssetGroupSchema, Unity.Addressables.Editor"
            );

            if (settingsDefaultObjectType == null || settingsType == null || groupType == null || entryType == null)
            {
                error = new ErrorResponse(
                    "Addressables package (com.unity.addressables) not installed. Install it from Package Manager to use this tool."
                );
                return false;
            }

            PropertyInfo settingsProperty = settingsDefaultObjectType.GetProperty("Settings", BindingFlags.Public | BindingFlags.Static);
            object settings = settingsProperty?.GetValue(null, null);
            if (settings == null)
            {
                error = new ErrorResponse(
                    "Addressables settings asset not found. Open Addressables Groups window to create settings first."
                );
                return false;
            }

            context = new AddressablesContext(settings, settingsType, groupType, entryType, groupSchemaType);
            return true;
        }

        private static IList GetGroups(object settings)
        {
            object groups = GetPropertyValue(settings, "groups");
            return groups as IList ?? new List<object>();
        }

        private static IList GetEntries(object group)
        {
            object entries = GetPropertyValue(group, "entries");
            return entries as IList ?? (entries as IEnumerable)?.Cast<object>().ToList() ?? new List<object>();
        }

        private static void EnsureLabelExists(object settings, string label)
        {
            MethodInfo addLabelMethod = settings
                .GetType()
                .GetMethods(BindingFlags.Instance | BindingFlags.Public)
                .FirstOrDefault(m => m.Name == "AddLabel" && m.GetParameters().Length >= 1 && m.GetParameters()[0].ParameterType == typeof(string));
            if (addLabelMethod == null)
            {
                return;
            }

            object[] args = BuildDefaultArguments(addLabelMethod.GetParameters());
            args[0] = label;
            addLabelMethod.Invoke(settings, args);
        }

        private static List<object> ResolveTargetEntries(AddressablesContext context, string guid, string path)
        {
            List<object> result = new List<object>();

            string targetGuid = !string.IsNullOrEmpty(guid) ? guid : AssetDatabase.AssetPathToGUID(path ?? string.Empty);
            if (!string.IsNullOrEmpty(targetGuid))
            {
                object entry = FindAssetEntry(context, targetGuid);
                if (entry != null)
                {
                    result.Add(entry);
                }

                return result;
            }

            IList groups = GetGroups(context.Settings);
            foreach (object group in groups)
            {
                if (group == null)
                {
                    continue;
                }

                foreach (object entry in GetEntries(group))
                {
                    if (entry != null)
                    {
                        result.Add(entry);
                    }
                }
            }

            return result;
        }

        private static object FindAssetEntry(AddressablesContext context, string guid)
        {
            MethodInfo findMethod = context.SettingsType.GetMethods(BindingFlags.Instance | BindingFlags.Public)
                .FirstOrDefault(m => m.Name == "FindAssetEntry" && m.GetParameters().Length >= 1 && m.GetParameters()[0].ParameterType == typeof(string));
            if (findMethod == null)
            {
                return null;
            }

            object[] args = BuildDefaultArguments(findMethod.GetParameters());
            args[0] = guid;
            return findMethod.Invoke(context.Settings, args);
        }

        private static bool InvokeSetLabel(object entry, string label, bool enabled)
        {
            MethodInfo setLabelMethod = entry
                .GetType()
                .GetMethods(BindingFlags.Instance | BindingFlags.Public)
                .FirstOrDefault(m =>
                    m.Name == "SetLabel"
                    && m.GetParameters().Length >= 2
                    && m.GetParameters()[0].ParameterType == typeof(string)
                    && m.GetParameters()[1].ParameterType == typeof(bool));
            if (setLabelMethod == null)
            {
                return false;
            }

            object[] args = BuildDefaultArguments(setLabelMethod.GetParameters());
            args[0] = label;
            args[1] = enabled;
            object result = setLabelMethod.Invoke(entry, args);
            return result is bool boolResult ? boolResult : true;
        }

        private static object InvokeCreateGroup(object settings, Type groupSchemaType, string groupName)
        {
            MethodInfo createGroupMethod = settings
                .GetType()
                .GetMethods(BindingFlags.Instance | BindingFlags.Public)
                .Where(m => m.Name == "CreateGroup")
                .OrderByDescending(m => m.GetParameters().Length)
                .FirstOrDefault();
            if (createGroupMethod == null)
            {
                return null;
            }

            ParameterInfo[] parameters = createGroupMethod.GetParameters();
            object[] args = BuildDefaultArguments(parameters);

            if (parameters.Length > 0)
            {
                args[0] = groupName;
            }

            for (int i = 1; i < parameters.Length; i++)
            {
                ParameterInfo parameter = parameters[i];
                if (parameter.ParameterType == typeof(bool))
                {
                    args[i] = false;
                }
                else if (parameter.ParameterType.IsArray)
                {
                    args[i] = Array.CreateInstance(parameter.ParameterType.GetElementType(), 0);
                }
                else if (
                    groupSchemaType != null
                    && parameter.ParameterType.IsGenericType
                    && parameter.ParameterType.GetGenericArguments().Length == 1
                    && parameter.ParameterType.GetGenericArguments()[0] == groupSchemaType)
                {
                    args[i] = Activator.CreateInstance(parameter.ParameterType);
                }
            }

            return createGroupMethod.Invoke(settings, args);
        }

        private static object InvokeInstanceMethod(object target, string methodName, params object[] methodArgs)
        {
            if (target == null)
            {
                return null;
            }

            MethodInfo method = target
                .GetType()
                .GetMethods(BindingFlags.Instance | BindingFlags.Public)
                .FirstOrDefault(m => m.Name == methodName && m.GetParameters().Length == methodArgs.Length);
            return method?.Invoke(target, methodArgs);
        }

        private static object[] BuildDefaultArguments(ParameterInfo[] parameters)
        {
            object[] args = new object[parameters.Length];
            for (int i = 0; i < parameters.Length; i++)
            {
                Type parameterType = parameters[i].ParameterType;
                if (parameters[i].HasDefaultValue)
                {
                    args[i] = parameters[i].DefaultValue;
                }
                else if (parameterType == typeof(bool))
                {
                    args[i] = false;
                }
                else if (parameterType.IsValueType)
                {
                    args[i] = Activator.CreateInstance(parameterType);
                }
                else
                {
                    args[i] = null;
                }
            }

            return args;
        }

        private static object GetPropertyValue(object target, string propertyName)
        {
            if (target == null)
            {
                return null;
            }

            PropertyInfo property = target
                .GetType()
                .GetProperty(propertyName, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.IgnoreCase);
            return property?.GetValue(target, null);
        }

        private static string GetStringProperty(object target, string propertyName)
        {
            return GetPropertyValue(target, propertyName)?.ToString();
        }

        private static bool GetBoolProperty(object target, string propertyName)
        {
            object value = GetPropertyValue(target, propertyName);
            return value is bool boolValue && boolValue;
        }

        private readonly struct AddressablesContext
        {
            public AddressablesContext(object settings, Type settingsType, Type groupType, Type entryType, Type groupSchemaType)
            {
                Settings = settings;
                SettingsType = settingsType;
                GroupType = groupType;
                EntryType = entryType;
                GroupSchemaType = groupSchemaType;
            }

            public object Settings { get; }
            public Type SettingsType { get; }
            public Type GroupType { get; }
            public Type EntryType { get; }
            public Type GroupSchemaType { get; }
        }
    }
#else
    [McpForUnityTool("manage_addressables")]
    public static class ManageAddressables
    {
        public static object HandleCommand(JObject @params)
        {
            return new ErrorResponse("manage_addressables requires Unity 2021.3 or newer.");
        }
    }
#endif
}
#endif
