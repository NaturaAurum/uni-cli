"""Shared test helpers — importable by test modules."""

from __future__ import annotations

import json
from typing import Any


def make_tool_result(data: dict[str, Any] | str, *, is_error: bool = False) -> dict[str, Any]:
    """Build an MCP tool result envelope (content + isError)."""
    text = data if isinstance(data, str) else json.dumps(data)
    return {
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
    }


def make_instances_resource(*instances: dict[str, Any]) -> dict[str, Any]:
    """Build an MCP instances resource response."""
    payload = json.dumps({"instances": list(instances)})
    return {
        "contents": [
            {"uri": "mcpforunity://instances", "text": payload},
        ],
    }
