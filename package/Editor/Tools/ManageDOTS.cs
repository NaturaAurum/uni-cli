#if UNITY_EDITOR
using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using MCPForUnity.Editor.Helpers;
using MCPForUnity.Editor.Tools;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace UniCli.Editor.Tools
{
    [McpForUnityTool("manage_dots")]
    public static class ManageDOTS
    {
        public static object HandleCommand(JObject @params)
        {
            string action = @params["action"]?.ToString()?.ToLowerInvariant();
            if (string.IsNullOrEmpty(action))
            {
                return new ErrorResponse("Action parameter is required.");
            }

            if (!TryGetDotsContext(out DotsContext context, out ErrorResponse error))
            {
                return error;
            }

            try
            {
                switch (action)
                {
                    case "list_worlds":
                        return ListWorlds(context);
                    case "query_entities":
                        return QueryEntities(
                            context,
                            @params["world"]?.ToString(),
                            @params["components"] as JArray,
                            @params["limit"]?.ToObject<int?>() ?? 20
                        );
                    case "get_component_data":
                        return GetComponentData(
                            context,
                            @params["world"]?.ToString(),
                            @params["entity_index"]?.ToObject<int?>() ?? -1,
                            @params["entity_version"]?.ToObject<int?>() ?? 1,
                            @params["component"]?.ToString()
                        );
                    case "list_systems":
                        return ListSystems(context, @params["world"]?.ToString());
                    case "get_world_info":
                        return GetWorldInfo(context, @params["world"]?.ToString());
                    default:
                        return new ErrorResponse(
                            $"Unknown action: '{action}'. Valid actions are: list_worlds, query_entities, get_component_data, list_systems, get_world_info."
                        );
                }
            }
            catch (Exception e)
            {
                return new ErrorResponse($"manage_dots action '{action}' failed: {e.Message}");
            }
        }

        private static object ListWorlds(DotsContext context)
        {
            List<object> worlds = new List<object>();
            foreach (object world in EnumerateWorlds(context))
            {
                worlds.Add(new
                {
                    name = GetStringProperty(world, "Name"),
                    isCreated = GetBoolProperty(world, "IsCreated"),
                    flags = GetPropertyValue(world, "Flags")?.ToString(),
                });
            }

            return new SuccessResponse(
                $"Found {worlds.Count} DOTS world(s).",
                new { count = worlds.Count, worlds }
            );
        }

        private static object QueryEntities(DotsContext context, string worldName, JArray componentNames, int limit)
        {
            object world = ResolveWorld(context, worldName);
            if (world == null)
            {
                return new ErrorResponse("DOTS world not found.");
            }

            List<Type> requestedComponents = ResolveComponentTypes(componentNames);
            if (componentNames != null && componentNames.Count > 0 && requestedComponents.Count == 0)
            {
                return new ErrorResponse("None of the requested component types could be resolved.");
            }

            object entityManager = GetPropertyValue(world, "EntityManager");
            if (entityManager == null)
            {
                return new ErrorResponse("EntityManager is not available for the selected world.");
            }

            object query = CreateEntityQuery(context, entityManager, requestedComponents);
            if (query == null)
            {
                return new ErrorResponse("Failed to create entity query.");
            }

            int totalCount = Convert.ToInt32(InvokeInstanceMethod(query, "CalculateEntityCount") ?? 0);
            List<object> preview = BuildEntityPreview(context, query, Mathf.Max(1, limit));
            InvokeDispose(query);

            return new SuccessResponse(
                $"Query returned {totalCount} entit{(totalCount == 1 ? "y" : "ies") }.",
                new
                {
                    world = GetStringProperty(world, "Name"),
                    components = requestedComponents.Select(t => t.FullName).ToArray(),
                    count = totalCount,
                    entities = preview,
                }
            );
        }

        private static object GetComponentData(DotsContext context, string worldName, int entityIndex, int entityVersion, string componentName)
        {
            if (entityIndex < 0)
            {
                return new ErrorResponse("'entity_index' must be provided and >= 0.");
            }

            if (string.IsNullOrEmpty(componentName))
            {
                return new ErrorResponse("'component' is required for get_component_data.");
            }

            Type componentType = ResolveComponentType(componentName);
            if (componentType == null)
            {
                return new ErrorResponse($"Component type '{componentName}' could not be resolved.");
            }

            object world = ResolveWorld(context, worldName);
            if (world == null)
            {
                return new ErrorResponse("DOTS world not found.");
            }

            object entityManager = GetPropertyValue(world, "EntityManager");
            if (entityManager == null)
            {
                return new ErrorResponse("EntityManager is not available for the selected world.");
            }

            object entity = CreateEntityStruct(context, entityIndex, entityVersion);
            if (!EntityHasComponent(context, entityManager, entity, componentType))
            {
                return new ErrorResponse(
                    $"Entity ({entityIndex}:{entityVersion}) does not contain component '{componentType.FullName}'."
                );
            }

            MethodInfo genericGetter = context.EntityManagerType
                .GetMethods(BindingFlags.Instance | BindingFlags.Public)
                .FirstOrDefault(m =>
                    m.Name == "GetComponentData"
                    && m.IsGenericMethodDefinition
                    && m.GetParameters().Length == 1
                    && m.GetParameters()[0].ParameterType == context.EntityType);
            if (genericGetter == null)
            {
                return new ErrorResponse("DOTS API mismatch: EntityManager.GetComponentData<T>(Entity) not found.");
            }

            object componentData = genericGetter.MakeGenericMethod(componentType).Invoke(entityManager, new[] { entity });
            object serialized = SerializeObject(componentData);

            return new SuccessResponse(
                "Component data retrieved.",
                new
                {
                    world = GetStringProperty(world, "Name"),
                    entity = new { index = entityIndex, version = entityVersion },
                    component = componentType.FullName,
                    data = serialized,
                }
            );
        }

        private static object ListSystems(DotsContext context, string worldName)
        {
            object world = ResolveWorld(context, worldName);
            if (world == null)
            {
                return new ErrorResponse("DOTS world not found.");
            }

            List<object> systems = GetSystems(world)
                .Select(system => new
                {
                    type = system.GetType().FullName,
                    name = GetStringProperty(system, "Name") ?? system.GetType().Name,
                    enabled = GetBoolProperty(system, "Enabled"),
                })
                .Cast<object>()
                .ToList();

            return new SuccessResponse(
                $"Found {systems.Count} system(s) in world '{GetStringProperty(world, "Name")}'.",
                new { world = GetStringProperty(world, "Name"), count = systems.Count, systems }
            );
        }

        private static object GetWorldInfo(DotsContext context, string worldName)
        {
            object world = ResolveWorld(context, worldName);
            if (world == null)
            {
                return new ErrorResponse("DOTS world not found.");
            }

            object entityManager = GetPropertyValue(world, "EntityManager");
            int entityCount = 0;
            if (entityManager != null)
            {
                object universalQuery = GetPropertyValue(entityManager, "UniversalQuery");
                if (universalQuery != null)
                {
                    entityCount = Convert.ToInt32(InvokeInstanceMethod(universalQuery, "CalculateEntityCount") ?? 0);
                    InvokeDispose(universalQuery);
                }
            }

            List<object> systems = GetSystems(world)
                .Select(system => new
                {
                    type = system.GetType().FullName,
                    enabled = GetBoolProperty(system, "Enabled"),
                })
                .Cast<object>()
                .ToList();

            return new SuccessResponse(
                $"Retrieved info for world '{GetStringProperty(world, "Name")}'.",
                new
                {
                    name = GetStringProperty(world, "Name"),
                    isCreated = GetBoolProperty(world, "IsCreated"),
                    flags = GetPropertyValue(world, "Flags")?.ToString(),
                    entityCount,
                    systemCount = systems.Count,
                    systems,
                }
            );
        }

        private static bool TryGetDotsContext(out DotsContext context, out ErrorResponse error)
        {
            context = default;
            error = null;

            Type worldType = Type.GetType("Unity.Entities.World, Unity.Entities");
            Type entityType = Type.GetType("Unity.Entities.Entity, Unity.Entities");
            Type entityManagerType = Type.GetType("Unity.Entities.EntityManager, Unity.Entities");
            Type componentTypeType = Type.GetType("Unity.Entities.ComponentType, Unity.Entities");
            Type allocatorType = Type.GetType("Unity.Collections.Allocator, Unity.Collections");

            if (worldType == null || entityType == null || entityManagerType == null || componentTypeType == null || allocatorType == null)
            {
                error = new ErrorResponse(
                    "DOTS package (com.unity.entities) not installed. Install Entities package to use this tool."
                );
                return false;
            }

            context = new DotsContext(worldType, entityType, entityManagerType, componentTypeType, allocatorType);
            return true;
        }

        private static IEnumerable<object> EnumerateWorlds(DotsContext context)
        {
            PropertyInfo allWorldsProperty = context.WorldType.GetProperty("All", BindingFlags.Public | BindingFlags.Static);
            IEnumerable worlds = allWorldsProperty?.GetValue(null, null) as IEnumerable;
            if (worlds == null)
            {
                yield break;
            }

            foreach (object world in worlds)
            {
                if (world != null)
                {
                    yield return world;
                }
            }
        }

        private static object ResolveWorld(DotsContext context, string worldName)
        {
            IEnumerable<object> worlds = EnumerateWorlds(context);
            if (!string.IsNullOrEmpty(worldName))
            {
                return worlds.FirstOrDefault(w => string.Equals(GetStringProperty(w, "Name"), worldName, StringComparison.Ordinal));
            }

            return worlds.FirstOrDefault();
        }

        private static List<Type> ResolveComponentTypes(JArray componentNames)
        {
            List<Type> result = new List<Type>();
            if (componentNames == null)
            {
                return result;
            }

            foreach (JToken token in componentNames)
            {
                string name = token?.ToString();
                Type resolved = ResolveComponentType(name);
                if (resolved != null && !result.Contains(resolved))
                {
                    result.Add(resolved);
                }
            }

            return result;
        }

        private static Type ResolveComponentType(string typeName)
        {
            if (string.IsNullOrEmpty(typeName))
            {
                return null;
            }

            Type direct = Type.GetType(typeName);
            if (direct != null)
            {
                return direct;
            }

            foreach (Assembly assembly in AppDomain.CurrentDomain.GetAssemblies())
            {
                Type found = assembly.GetType(typeName)
                    ?? assembly.GetTypes().FirstOrDefault(t => t.Name == typeName || t.FullName == typeName);
                if (found != null)
                {
                    return found;
                }
            }

            return null;
        }

        private static object CreateEntityQuery(DotsContext context, object entityManager, List<Type> componentTypes)
        {
            if (componentTypes.Count == 0)
            {
                return GetPropertyValue(entityManager, "UniversalQuery");
            }

            MethodInfo readOnlyMethod = context.ComponentTypeType.GetMethod("ReadOnly", BindingFlags.Public | BindingFlags.Static, null, new[] { typeof(Type) }, null);
            if (readOnlyMethod == null)
            {
                return null;
            }

            Array componentTypeArray = Array.CreateInstance(context.ComponentTypeType, componentTypes.Count);
            for (int i = 0; i < componentTypes.Count; i++)
            {
                object componentType = readOnlyMethod.Invoke(null, new object[] { componentTypes[i] });
                componentTypeArray.SetValue(componentType, i);
            }

            MethodInfo queryMethod = context.EntityManagerType.GetMethods(BindingFlags.Instance | BindingFlags.Public)
                .FirstOrDefault(m =>
                    m.Name == "CreateEntityQuery"
                    && m.GetParameters().Length == 1
                    && m.GetParameters()[0].ParameterType.IsArray
                    && m.GetParameters()[0].ParameterType.GetElementType() == context.ComponentTypeType);
            return queryMethod?.Invoke(entityManager, new object[] { componentTypeArray });
        }

        private static List<object> BuildEntityPreview(DotsContext context, object query, int limit)
        {
            List<object> entities = new List<object>();

            MethodInfo toEntityArrayMethod = query
                .GetType()
                .GetMethods(BindingFlags.Instance | BindingFlags.Public)
                .FirstOrDefault(m =>
                    m.Name == "ToEntityArray"
                    && m.GetParameters().Length == 1
                    && m.GetParameters()[0].ParameterType == context.AllocatorType);
            if (toEntityArrayMethod == null)
            {
                return entities;
            }

            object allocator = Enum.Parse(context.AllocatorType, "Temp");
            object nativeArray = toEntityArrayMethod.Invoke(query, new[] { allocator });
            if (nativeArray == null)
            {
                return entities;
            }

            try
            {
                int length = Convert.ToInt32(GetPropertyValue(nativeArray, "Length") ?? 0);
                MethodInfo getItem = nativeArray.GetType().GetMethod("get_Item", BindingFlags.Instance | BindingFlags.Public);

                int count = Mathf.Min(length, limit);
                for (int i = 0; i < count; i++)
                {
                    object entity = getItem?.Invoke(nativeArray, new object[] { i });
                    entities.Add(SerializeEntity(entity));
                }
            }
            finally
            {
                InvokeDispose(nativeArray);
            }

            return entities;
        }

        private static object CreateEntityStruct(DotsContext context, int index, int version)
        {
            object entity = Activator.CreateInstance(context.EntityType);
            FieldInfo indexField = context.EntityType.GetField("Index");
            FieldInfo versionField = context.EntityType.GetField("Version");

            indexField?.SetValue(entity, index);
            versionField?.SetValue(entity, version);
            return entity;
        }

        private static bool EntityHasComponent(DotsContext context, object entityManager, object entity, Type componentManagedType)
        {
            MethodInfo hasComponentByType = context.EntityManagerType.GetMethods(BindingFlags.Instance | BindingFlags.Public)
                .FirstOrDefault(m =>
                    m.Name == "HasComponent"
                    && m.GetParameters().Length == 2
                    && m.GetParameters()[0].ParameterType == context.EntityType
                    && m.GetParameters()[1].ParameterType == typeof(Type));
            if (hasComponentByType != null)
            {
                object result = hasComponentByType.Invoke(entityManager, new object[] { entity, componentManagedType });
                return result is bool boolResult && boolResult;
            }

            MethodInfo readOnlyMethod = context.ComponentTypeType.GetMethod("ReadOnly", BindingFlags.Public | BindingFlags.Static, null, new[] { typeof(Type) }, null);
            MethodInfo hasComponentByComponentType = context.EntityManagerType.GetMethods(BindingFlags.Instance | BindingFlags.Public)
                .FirstOrDefault(m =>
                    m.Name == "HasComponent"
                    && m.GetParameters().Length == 2
                    && m.GetParameters()[0].ParameterType == context.EntityType
                    && m.GetParameters()[1].ParameterType == context.ComponentTypeType);
            if (readOnlyMethod == null || hasComponentByComponentType == null)
            {
                return false;
            }

            object componentType = readOnlyMethod.Invoke(null, new object[] { componentManagedType });
            object fallbackResult = hasComponentByComponentType.Invoke(entityManager, new[] { entity, componentType });
            return fallbackResult is bool fallbackBool && fallbackBool;
        }

        private static IEnumerable<object> GetSystems(object world)
        {
            object systemsProperty = GetPropertyValue(world, "Systems");
            if (systemsProperty is IEnumerable propertyEnumerable)
            {
                foreach (object system in propertyEnumerable)
                {
                    if (system != null)
                    {
                        yield return system;
                    }
                }

                yield break;
            }

            object existingSystems = InvokeInstanceMethod(world, "GetExistingSystems");
            if (existingSystems is IEnumerable existingEnumerable)
            {
                foreach (object system in existingEnumerable)
                {
                    if (system != null)
                    {
                        yield return system;
                    }
                }

                yield break;
            }

            object handles = InvokeInstanceMethod(world, "GetAllSystems");
            if (!(handles is IEnumerable handleEnumerable))
            {
                yield break;
            }

            MethodInfo getSystemManaged = world
                .GetType()
                .GetMethods(BindingFlags.Instance | BindingFlags.Public)
                .FirstOrDefault(m => m.Name == "GetExistingSystemManaged" && m.GetParameters().Length == 1);
            if (getSystemManaged == null)
            {
                yield break;
            }

            foreach (object handle in handleEnumerable)
            {
                object system = getSystemManaged.Invoke(world, new[] { handle });
                if (system != null)
                {
                    yield return system;
                }
            }
        }

        private static object SerializeEntity(object entity)
        {
            if (entity == null)
            {
                return null;
            }

            Type type = entity.GetType();
            return new
            {
                index = GetFieldValue(type, entity, "Index"),
                version = GetFieldValue(type, entity, "Version"),
            };
        }

        private static object SerializeObject(object value)
        {
            if (value == null)
            {
                return null;
            }

            Type type = value.GetType();
            if (type.IsPrimitive || value is string || value is decimal)
            {
                return value;
            }

            Dictionary<string, object> data = new Dictionary<string, object>();
            foreach (FieldInfo field in type.GetFields(BindingFlags.Instance | BindingFlags.Public))
            {
                data[field.Name] = field.GetValue(value);
            }

            foreach (PropertyInfo property in type.GetProperties(BindingFlags.Instance | BindingFlags.Public))
            {
                if (!property.CanRead || property.GetIndexParameters().Length > 0)
                {
                    continue;
                }

                try
                {
                    data[property.Name] = property.GetValue(value, null);
                }
                catch
                {
                    data[property.Name] = "<unavailable>";
                }
            }

            return data;
        }

        private static object GetFieldValue(Type type, object target, string fieldName)
        {
            return type.GetField(fieldName, BindingFlags.Instance | BindingFlags.Public)?.GetValue(target);
        }

        private static void InvokeDispose(object target)
        {
            target?.GetType().GetMethod("Dispose", BindingFlags.Instance | BindingFlags.Public)?.Invoke(target, null);
        }

        private static object InvokeInstanceMethod(object target, string methodName, params object[] args)
        {
            if (target == null)
            {
                return null;
            }

            MethodInfo method = target
                .GetType()
                .GetMethods(BindingFlags.Instance | BindingFlags.Public)
                .FirstOrDefault(m => m.Name == methodName && m.GetParameters().Length == args.Length);
            return method?.Invoke(target, args);
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

        private readonly struct DotsContext
        {
            public DotsContext(Type worldType, Type entityType, Type entityManagerType, Type componentTypeType, Type allocatorType)
            {
                WorldType = worldType;
                EntityType = entityType;
                EntityManagerType = entityManagerType;
                ComponentTypeType = componentTypeType;
                AllocatorType = allocatorType;
            }

            public Type WorldType { get; }
            public Type EntityType { get; }
            public Type EntityManagerType { get; }
            public Type ComponentTypeType { get; }
            public Type AllocatorType { get; }
        }
    }
}
#endif
