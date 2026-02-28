"""Subsystem commands — ui-toolkit, addressables, dots, shader-graph.

These proxy to the uni-cli UPM package tools (manage_ui_toolkit, etc.)
which are auto-registered via [McpForUnityTool] attribute.
"""

from __future__ import annotations

from typing import Any

from uni_cli.transport.mcp_client import McpClient, extract_text, parse_result_json


# Tool name mapping: CLI command name -> MCP tool name
_TOOL_MAP = {
    "ui-toolkit": "manage_ui_toolkit",
    "addressables": "manage_addressables",
    "dots": "manage_dots",
    "shader-graph": "manage_shader_graph",
}


def run_subsystem(
    client: McpClient,
    instance_id: str,
    command: str,
    action: str,
    extra_args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generic dispatcher for subsystem tool commands.

    Args:
        client: MCP client
        instance_id: Unity instance ID
        command: CLI command name (e.g. "ui-toolkit")
        action: Tool action (e.g. "list_documents")
        extra_args: Additional parameters for the tool
    """
    tool_name = _TOOL_MAP.get(command)
    if not tool_name:
        return {"success": False, "error": f"Unknown subsystem: {command}"}

    args: dict[str, Any] = {
        "action": action,
        "unity_instance": instance_id,
    }
    if extra_args:
        args.update(extra_args)

    result = client.call_tool(tool_name, args)
    parsed = parse_result_json(result)
    if parsed is not None:
        return parsed
    return {"raw_text": extract_text(result)}
