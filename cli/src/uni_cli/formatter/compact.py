"""Compact output formatter for uni-cli.

Converts MCP JSON responses to token-efficient compact format
per the CLI output contract (docs/cli-output-contract.md).

Format:
  Single item:  ok op=<op> id=<id> [k=v ...]
  Collection:   row <f1>=<v1> <f2>=<v2> ...
                ok op=<op> count=<n> next=<cursor> truncated=<0|1>
  Error:        err code=<code> msg=<message>
"""

from __future__ import annotations

import json
from typing import Any

# --------------------------------------------------------------------------- #
# Value escaping
# --------------------------------------------------------------------------- #


def _esc(val: Any) -> str:
    """Escape a value for compact output. Spaces become underscores."""
    if val is None:
        return "-"
    s = str(val).strip()
    if not s:
        return "-"
    # Replace spaces/newlines to keep single-token fields
    return s.replace("\n", " ").replace("\r", "").replace(" ", "_")


# --------------------------------------------------------------------------- #
# Generic helpers
# --------------------------------------------------------------------------- #


def format_error(code: str, msg: str) -> str:
    """Format an error line."""
    return f"err code={_esc(code)} msg={_esc(msg)}"


def format_ok(op: str, **kv: Any) -> str:
    """Format a success summary line."""
    parts = [f"ok op={op}"]
    for k, v in kv.items():
        parts.append(f"{k}={_esc(v)}")
    return " ".join(parts)


def format_row(fields: dict[str, str], data: dict[str, Any]) -> str:
    """Format a single row with selected fields from data."""
    parts = ["row"]
    for field_name, field_key in fields.items():
        val = data.get(field_key, data.get(field_name, "-"))
        parts.append(f"{field_name}={_esc(val)}")
    return " ".join(parts)


# --------------------------------------------------------------------------- #
# Domain-specific formatters
# --------------------------------------------------------------------------- #


def format_hierarchy(
    data: dict[str, Any],
    fields: list[str],
    limit: int,
    cursor: str,
) -> str:
    """Format hierarchy query result as compact rows + summary.

    Expects data to be the parsed JSON from manage_scene get_hierarchy.
    """
    nodes = (
        data.get("hierarchy") or data.get("nodes") or data.get("items") or data.get("data", {}).get("hierarchy") or []
    )
    if not isinstance(nodes, list):
        nodes = []

    # Field alias map: user-facing name -> possible keys in node data
    field_aliases = {
        "id": ["instanceID", "id", "instance_id"],
        "name": ["name"],
        "parent": ["parentInstanceID", "parent", "parent_id"],
        "active": ["active", "activeSelf"],
        "tag": ["tag"],
        "layer": ["layer"],
        "pos": ["position", "localPosition"],
        "rot": ["rotation", "localRotation"],
        "scale": ["localScale", "scale"],
    }

    lines: list[str] = []
    count = 0
    for node in nodes[:limit]:
        if not isinstance(node, dict):
            continue
        parts = ["row"]
        for f in fields:
            aliases = field_aliases.get(f, [f])
            val = "-"
            for alias in aliases:
                if alias in node:
                    val = node[alias]
                    break
            parts.append(f"{f}={_esc(val)}")
        lines.append(" ".join(parts))
        count += 1

    next_cursor = data.get("next_cursor", data.get("nextCursor"))
    truncated = 1 if len(nodes) > limit else 0
    next_val = next_cursor if next_cursor is not None else "-"
    lines.append(f"ok op=hierarchy.ls count={count} next={next_val} truncated={truncated}")
    return "\n".join(lines)


def format_object_result(op: str, data: dict[str, Any]) -> str:
    """Format a single-object operation result (create, modify, delete)."""
    name = data.get("name") or data.get("gameObjectName") or data.get("target") or "-"
    obj_id = data.get("instanceID") or data.get("id") or "-"
    return format_ok(f"object.{op}", name=name, id=obj_id)


def format_asset_search(
    data: dict[str, Any],
    fields: list[str],
    limit: int,
) -> str:
    """Format asset search result as compact rows + summary."""
    results = data.get("assets") or data.get("results") or data.get("items") or data.get("data", {}).get("assets") or []
    if not isinstance(results, list):
        results = []

    field_aliases = {
        "path": ["path", "assetPath"],
        "name": ["name", "fileName"],
        "type": ["assetType", "type"],
        "guid": ["guid"],
        "size": ["size", "fileSize"],
    }

    lines: list[str] = []
    count = 0
    for item in results[:limit]:
        if not isinstance(item, dict):
            continue
        parts = ["row"]
        for f in fields:
            aliases = field_aliases.get(f, [f])
            val = "-"
            for alias in aliases:
                if alias in item:
                    val = item[alias]
                    break
            parts.append(f"{f}={_esc(val)}")
        lines.append(" ".join(parts))
        count += 1

    page = data.get("pageNumber", data.get("page_number", 1))
    next_val = page + 1 if count >= limit else "-"
    truncated = 1 if count >= limit else 0
    lines.append(f"ok op=asset.search count={count} next={next_val} truncated={truncated}")
    return "\n".join(lines)


def format_batch(data: dict[str, Any]) -> str:
    """Format batch operation result as summary per contract section 6."""
    results = data.get("results", [])
    if not isinstance(results, list):
        results = []
    total = len(results)
    fail_items = [x for x in results if isinstance(x, dict) and x.get("error")]
    fail = len(fail_items)
    ok_count = total - fail
    # Up to 3 fail IDs per contract
    fail_ids = ",".join(str(x.get("id") or x.get("name") or f"item_{i}") for i, x in enumerate(fail_items[:3]))
    line = f"ok op=batch.apply total={total} ok_count={ok_count} fail_count={fail}"
    if fail_ids:
        line += f" fail_ids={fail_ids}"
    return line


def format_subsystem_result(tool: str, action: str, data: dict[str, Any]) -> str:
    """Format a subsystem tool result (ui_toolkit, addressables, dots, shader_graph).

    For list-type actions: rows + summary.
    For single-item actions: ok summary.
    """
    # Detect if this is a list/collection result
    list_keys = [
        "items",
        "documents",
        "stylesheets",
        "groups",
        "entries",
        "worlds",
        "entities",
        "systems",
        "graphs",
        "variants",
        "results",
        "assets",
    ]
    items = None
    for key in list_keys:
        if key in data and isinstance(data[key], list):
            items = data[key]
            break

    if items is not None:
        lines: list[str] = []
        for item in items:
            if isinstance(item, dict):
                parts = ["row"]
                for k, v in item.items():
                    if not k.startswith("_"):
                        parts.append(f"{k}={_esc(v)}")
                lines.append(" ".join(parts))
            else:
                lines.append(f"row value={_esc(item)}")
        lines.append(format_ok(f"{tool}.{action}", count=len(items)))
        return "\n".join(lines)

    # Single-item result
    kv = {}
    for k, v in data.items():
        if k in ("success", "message", "data") or k.startswith("_"):
            continue
        kv[k] = v
    return format_ok(f"{tool}.{action}", **kv)


# --------------------------------------------------------------------------- #
# Top-level dispatcher
# --------------------------------------------------------------------------- #


def format_result(
    command: str,
    action: str,
    raw_result: dict[str, Any],
    *,
    fields: list[str] | None = None,
    limit: int = 120,
    cursor: str = "0",
) -> str:
    """Format an MCP tool result into compact output.

    Args:
        command: The CLI command (hierarchy, object, asset, batch, etc.)
        action: The sub-action (ls, create, search, apply, etc.)
        raw_result: Parsed JSON result from MCP tool response
        fields: Field whitelist for collection commands
        limit: Page size for collection commands
        cursor: Current cursor position
    """
    # Unwrap nested data envelope
    data = raw_result
    if isinstance(data.get("data"), dict):
        data = data["data"]

    if command == "hierarchy":
        return format_hierarchy(data, fields or ["id", "name", "parent"], limit, cursor)
    elif command == "object":
        return format_object_result(action, data)
    elif command == "asset" and action == "search":
        return format_asset_search(data, fields or ["path", "name"], limit)
    elif command == "batch":
        return format_batch(data)
    elif command in ("ui-toolkit", "addressables", "dots", "shader-graph"):
        tool_name = command.replace("-", "_")
        return format_subsystem_result(tool_name, action, data)
    else:
        # Fallback: key=value pairs from top-level data
        return format_ok(
            f"{command}.{action}",
            **{k: v for k, v in data.items() if k not in ("success", "message") and not k.startswith("_")},
        )


def format_json(result: dict[str, Any]) -> str:
    """Format result as indented JSON (--format json mode)."""
    return json.dumps(result, indent=2, ensure_ascii=False)
