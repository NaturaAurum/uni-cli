"""asset subcommand — Asset operations."""

from __future__ import annotations

from typing import Any

from uni_cli.transport.mcp_client import McpClient, StdioMcpClient, extract_text, parse_result_json


def run_search(
    client: McpClient | StdioMcpClient,
    instance_id: str,
    query: str,
    filter_type: str | None,
    fields: str,
    limit: int,
) -> dict[str, Any]:
    """Search assets via manage_asset search."""
    args: dict[str, Any] = {
        "action": "search",
        "path": "Assets",
        "page_size": limit,
        "page_number": 1,
        "generate_preview": False,
        "unity_instance": instance_id,
    }
    if query:
        args["search_pattern"] = query
    if filter_type:
        args["filter_type"] = filter_type
    result = client.call_tool("manage_asset", args)
    parsed = parse_result_json(result)
    if parsed is not None:
        return parsed
    return {"raw_text": extract_text(result)}


def run_info(
    client: McpClient | StdioMcpClient,
    instance_id: str,
    path: str,
) -> dict[str, Any]:
    """Get asset info via manage_asset get_info."""
    args: dict[str, Any] = {
        "action": "get_info",
        "path": path,
        "unity_instance": instance_id,
    }
    result = client.call_tool("manage_asset", args)
    parsed = parse_result_json(result)
    if parsed is not None:
        return parsed
    return {"raw_text": extract_text(result)}


def run_create(
    client: McpClient | StdioMcpClient,
    instance_id: str,
    path: str,
    asset_type: str,
    **properties: Any,
) -> dict[str, Any]:
    """Create an asset via manage_asset create."""
    args: dict[str, Any] = {
        "action": "create",
        "path": path,
        "asset_type": asset_type,
        "unity_instance": instance_id,
    }
    if properties:
        args["properties"] = properties
    result = client.call_tool("manage_asset", args)
    parsed = parse_result_json(result)
    if parsed is not None:
        return parsed
    return {"raw_text": extract_text(result)}


def run_delete(
    client: McpClient | StdioMcpClient,
    instance_id: str,
    path: str,
) -> dict[str, Any]:
    """Delete an asset via manage_asset delete."""
    args: dict[str, Any] = {
        "action": "delete",
        "path": path,
        "unity_instance": instance_id,
    }
    result = client.call_tool("manage_asset", args)
    parsed = parse_result_json(result)
    if parsed is not None:
        return parsed
    return {"raw_text": extract_text(result)}
