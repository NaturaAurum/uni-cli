"""Subsystem commands — ui-toolkit, addressables, dots, shader-graph.

These proxy to the uni-cli UPM package tools (manage_ui_toolkit, etc.)
which are auto-registered via [McpForUnityTool] attribute.

Custom tools must be invoked via the execute_custom_tool MCP tool,
not called directly by name. Built-in tools (manage_scene, etc.) are
hardcoded in the Python MCP server (AutoRegister=false), while custom
tools are project-scoped and routed through execute_custom_tool.
"""

from __future__ import annotations

from typing import Any

from uni_cli.transport.mcp_client import McpClient, StdioMcpClient, extract_text, parse_result_json

# Tool name mapping: CLI command name -> unity-mcp custom tool name
_TOOL_MAP = {
    "ui-toolkit": "manage_ui_toolkit",
    "addressables": "manage_addressables",
    "dots": "manage_dots",
    "shader-graph": "manage_shader_graph",
}


def run_subsystem(
    client: McpClient | StdioMcpClient,
    instance_id: str,
    command: str,
    action: str,
    extra_args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generic dispatcher for subsystem tool commands.

    Invokes custom tools via execute_custom_tool, which is the
    unity-mcp gateway for project-scoped tool execution.

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

    params: dict[str, Any] = {"action": action}
    if extra_args:
        params.update(extra_args)

    args: dict[str, Any] = {
        "tool_name": tool_name,
        "parameters": params,
        "unity_instance": instance_id,
    }

    result = client.call_tool("execute_custom_tool", args)
    parsed = parse_result_json(result)
    if parsed is not None:
        return parsed
    return {"raw_text": extract_text(result)}
