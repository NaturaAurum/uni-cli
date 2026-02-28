"""hierarchy subcommand — Scene hierarchy operations."""

from __future__ import annotations

from typing import Any

from uni_cli.transport.mcp_client import McpClient, extract_text, parse_result_json


def run_ls(
    client: McpClient,
    instance_id: str,
    fields: str,
    limit: int,
    cursor: str,
) -> dict[str, Any]:
    """List scene hierarchy via manage_scene get_hierarchy."""
    args: dict[str, Any] = {
        "action": "get_hierarchy",
        "page_size": limit,
        "cursor": int(cursor) if cursor.isdigit() else 0,
        "include_transform": True,
        "max_depth": 4,
        "unity_instance": instance_id,
    }
    result = client.call_tool("manage_scene", args)
    text = extract_text(result)
    parsed = parse_result_json(result)
    if parsed is not None:
        return parsed
    return {"raw_text": text}
