"""object subcommand — GameObject operations."""

from __future__ import annotations

from typing import Any

from uni_cli.transport.mcp_client import McpClient, StdioMcpClient, extract_text, parse_result_json


def run_create(
    client: McpClient | StdioMcpClient,
    instance_id: str,
    name: str,
    preset: str,
    pos: str,
) -> dict[str, Any]:
    """Create a GameObject via manage_gameobject create."""
    position = [float(x) for x in pos.split(",")]
    args: dict[str, Any] = {
        "action": "create",
        "name": name,
        "unity_instance": instance_id,
    }
    if preset != "empty":
        args["primitive_type"] = preset
    if position != [0.0, 0.0, 0.0]:
        args["position"] = position
    result = client.call_tool("manage_gameobject", args)
    parsed = parse_result_json(result)
    if parsed is not None:
        return parsed
    return {"raw_text": extract_text(result)}


def run_get(
    client: McpClient | StdioMcpClient,
    instance_id: str,
    target: str,
) -> dict[str, Any]:
    """Get GameObject info via manage_gameobject get."""
    args: dict[str, Any] = {
        "action": "get",
        "target": target,
        "search_method": "by_name",
        "unity_instance": instance_id,
    }
    result = client.call_tool("manage_gameobject", args)
    parsed = parse_result_json(result)
    if parsed is not None:
        return parsed
    return {"raw_text": extract_text(result)}


def run_modify(
    client: McpClient | StdioMcpClient,
    instance_id: str,
    target: str,
    *,
    pos: str | None = None,
    parent: str | None = None,
    name: str | None = None,
    active: bool | None = None,
) -> dict[str, Any]:
    """Modify a GameObject via manage_gameobject modify."""
    args: dict[str, Any] = {
        "action": "modify",
        "target": target,
        "search_method": "by_name",
        "unity_instance": instance_id,
    }
    if pos is not None:
        args["position"] = [float(x) for x in pos.split(",")]
    if parent is not None:
        args["parent"] = parent
    if name is not None:
        args["name"] = name
    if active is not None:
        args["active"] = active
    result = client.call_tool("manage_gameobject", args)
    parsed = parse_result_json(result)
    if parsed is not None:
        return parsed
    return {"raw_text": extract_text(result)}


def run_delete(
    client: McpClient | StdioMcpClient,
    instance_id: str,
    target: str,
) -> dict[str, Any]:
    """Delete a GameObject via manage_gameobject delete."""
    args: dict[str, Any] = {
        "action": "delete",
        "target": target,
        "search_method": "by_name",
        "unity_instance": instance_id,
    }
    result = client.call_tool("manage_gameobject", args)
    parsed = parse_result_json(result)
    if parsed is not None:
        return parsed
    return {"raw_text": extract_text(result)}
