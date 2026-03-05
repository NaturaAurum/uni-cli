"""batch subcommand — Batch operations."""

from __future__ import annotations

import json
from typing import Any

from uni_cli.transport.mcp_client import McpClient, StdioMcpClient, extract_text, parse_result_json


def run_apply(
    client: McpClient | StdioMcpClient,
    instance_id: str,
    file_path: str,
) -> dict[str, Any]:
    """Execute batch commands from a JSON file via batch_execute."""
    with open(file_path) as f:
        batch_data = json.load(f)

    # Batch file format: {"commands": [{"tool": "...", "params": {...}}, ...]}
    commands = batch_data.get("commands", [])
    if not commands:
        return {"success": False, "error": "No commands in batch file"}

    # Inject unity_instance into each command's params
    for cmd in commands:
        params = cmd.get("params", {})
        if "unity_instance" not in params:
            params["unity_instance"] = instance_id
        cmd["params"] = params

    args: dict[str, Any] = {
        "commands": commands,
        "parallel": batch_data.get("parallel", False),
        "fail_fast": batch_data.get("fail_fast", True),
        "max_parallelism": batch_data.get("max_parallelism", 1),
        "unity_instance": instance_id,
    }
    result = client.call_tool("batch_execute", args)
    parsed = parse_result_json(result)
    if parsed is not None:
        return parsed
    return {"raw_text": extract_text(result)}
