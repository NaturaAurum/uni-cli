#!/usr/bin/env python3
"""Tier 3: Analyze tool-schema token overhead for MCP vs CLI approaches.

Measures the per-conversation fixed cost of tool definitions that get injected
into the LLM's system prompt or tool-use framework. This overhead is amortized
across all operations in a conversation.

Usage:
    python3 scripts/analyze_schema_overhead.py --url http://127.0.0.1:8080/mcp
    python3 scripts/analyze_schema_overhead.py --mock  # offline estimate
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from typing import Any

from mcp_real_scenario import McpSession


class TokenCounter:
    def __init__(self, encoding_name: str | None) -> None:
        self.mode = "heuristic_char4"
        self._encoder = None
        if encoding_name:
            try:
                import tiktoken  # type: ignore

                self._encoder = tiktoken.get_encoding(encoding_name)
                self.mode = f"tiktoken:{encoding_name}"
            except Exception:
                pass

    def count(self, text: str) -> int:
        if not text:
            return 0
        if self._encoder:
            return len(self._encoder.encode(text))
        return int(math.ceil(len(text) / 4.0))


# --- MCP tool schema extraction ---


def fetch_mcp_tools(session: McpSession) -> list[dict[str, Any]]:
    """Fetch tool list via MCP tools/list."""
    msg = {
        "jsonrpc": "2.0",
        "id": session.seq,
        "method": "tools/list",
        "params": {},
    }
    session.seq += 1
    from mcp_real_scenario import _post_sse_json

    event, raw, _ = _post_sse_json(
        session.url, msg, session.session_id, session.timeout_sec
    )
    if not event or "result" not in event:
        print(f"warn: tools/list failed: {raw[:300]}", file=sys.stderr)
        return []
    result = event["result"]
    return result.get("tools", [])


def fetch_mcp_resources(session: McpSession) -> list[dict[str, Any]]:
    """Fetch resource list via MCP resources/list."""
    msg = {
        "jsonrpc": "2.0",
        "id": session.seq,
        "method": "resources/list",
        "params": {},
    }
    session.seq += 1
    from mcp_real_scenario import _post_sse_json

    event, raw, _ = _post_sse_json(
        session.url, msg, session.session_id, session.timeout_sec
    )
    if not event or "result" not in event:
        print(f"warn: resources/list failed: {raw[:300]}", file=sys.stderr)
        return []
    result = event["result"]
    return result.get("resources", [])


# --- CLI help text estimation ---


def estimate_cli_help_tokens(tool_count: int) -> dict[str, Any]:
    """Estimate CLI wrapper's tool schema overhead.

    In a CLI wrapper approach, the LLM receives:
    - A system prompt section describing available CLI commands
    - Each command: name, description, flags, examples

    We estimate based on typical CLI help output patterns.
    """
    # Average CLI command help text size (based on typical --help output)
    avg_help_per_command = (
        "uni-cli <command> <action> [flags]\n"
        "  --instance <id>    Target Unity instance\n"
        "  --fields <list>    Comma-separated field whitelist\n"
        "  --limit <n>        Page size (max 200)\n"
        "  --cursor <n>       Page cursor\n"
        "  --format compact   Output format (compact|json)\n"
    )
    # CLI commands map roughly 1:1 to MCP tools but with subcommands
    cli_commands = [
        (
            "uni-cli hierarchy ls",
            "List scene hierarchy (fields: id, name, parent, pos, rot, scale)",
        ),
        (
            "uni-cli hierarchy find",
            "Search GameObjects (by name, tag, layer, component, path, id)",
        ),
        ("uni-cli object create", "Create GameObject (--preset cube|sphere|empty|...)"),
        ("uni-cli object modify", "Modify GameObject transform, name, parent, tag"),
        ("uni-cli object delete", "Delete GameObject by name or id"),
        ("uni-cli object duplicate", "Duplicate GameObject"),
        ("uni-cli component add", "Add component to GameObject"),
        ("uni-cli component remove", "Remove component from GameObject"),
        ("uni-cli component set", "Set component property value"),
        ("uni-cli asset search", "Search project assets (--query, --filter-type)"),
        ("uni-cli asset info", "Get asset metadata"),
        ("uni-cli asset create", "Create new asset"),
        ("uni-cli material create", "Create material with shader"),
        ("uni-cli material set", "Set material shader property"),
        ("uni-cli script create", "Create C# script file"),
        ("uni-cli script validate", "Validate script syntax"),
        ("uni-cli prefab save", "Save hierarchy as prefab"),
        ("uni-cli prefab instantiate", "Instantiate prefab in scene"),
        ("uni-cli scene open", "Open/create scene"),
        ("uni-cli scene save", "Save current scene"),
        ("uni-cli scene screenshot", "Capture scene view"),
        ("uni-cli editor play|pause|stop", "Control editor playback"),
        ("uni-cli console read", "Read editor console logs"),
        ("uni-cli batch apply", "Execute multiple commands"),
        ("uni-cli test run", "Run Unity tests"),
    ]

    help_text_parts = [
        "# uni-cli — Unity Editor CLI for LLM agents\n\nAvailable commands:\n"
    ]
    for cmd, desc in cli_commands:
        help_text_parts.append(f"  {cmd:<35} {desc}\n")
    help_text_parts.append("\nCommon flags:\n")
    help_text_parts.append(avg_help_per_command)
    help_text_parts.append(
        "\nOutput format (compact):\n"
        "  Single:    ok op=<op> id=<id> [k=v ...]\n"
        "  Collection: row field1=val1 field2=val2 ...\\n"
        "             ok op=<op> count=<n> next=<cursor> truncated=<0|1>\n"
        "  Error:     err code=<code> msg=<short>\n"
    )

    return {
        "command_count": len(cli_commands),
        "help_text": "".join(help_text_parts),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8080/mcp")
    parser.add_argument("--encoding", default="o200k_base")
    parser.add_argument("--mock", action="store_true", help="Offline estimation only")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--out", default="reports/schema-overhead.json")
    args = parser.parse_args()

    tc = TokenCounter(args.encoding)

    # --- MCP side ---
    mcp_tools: list[dict[str, Any]] = []
    mcp_resources: list[dict[str, Any]] = []
    mcp_schema_text = ""

    if not args.mock:
        try:
            session = McpSession(url=args.url, timeout_sec=args.timeout)
            session.initialize()
            mcp_tools = fetch_mcp_tools(session)
            mcp_resources = fetch_mcp_resources(session)
        except Exception as exc:
            print(
                f"warn: MCP connection failed ({exc}), using mock estimates",
                file=sys.stderr,
            )
            args.mock = True

    if args.mock:
        # Rough estimate: 29 tools × ~200 tokens each (name + description + inputSchema)
        mcp_schema_text = (
            "mock: estimated 29 tools × 200 tokens + 20 resources × 80 tokens"
        )
        mcp_tool_tokens = 29 * 200
        mcp_resource_tokens = 20 * 80
    else:
        # Serialize each tool definition as it would appear in the LLM's context
        tool_schemas = []
        for tool in mcp_tools:
            tool_schemas.append(json.dumps(tool, ensure_ascii=False))
        mcp_schema_text = "\n".join(tool_schemas)

        resource_schemas = []
        for res in mcp_resources:
            resource_schemas.append(json.dumps(res, ensure_ascii=False))
        mcp_resource_text = "\n".join(resource_schemas)

        mcp_tool_tokens = tc.count(mcp_schema_text)
        mcp_resource_tokens = tc.count(mcp_resource_text)

    mcp_total = mcp_tool_tokens + mcp_resource_tokens

    # --- CLI side ---
    cli_info = estimate_cli_help_tokens(len(mcp_tools) or 29)
    cli_total = tc.count(cli_info["help_text"])

    # --- Amortized analysis ---
    report = {
        "token_counter": tc.mode,
        "mcp": {
            "tool_count": len(mcp_tools) or 29,
            "resource_count": len(mcp_resources) or 20,
            "tool_schema_tokens": mcp_tool_tokens,
            "resource_schema_tokens": mcp_resource_tokens,
            "total_schema_tokens": mcp_total,
            "is_mock": args.mock,
        },
        "cli": {
            "command_count": cli_info["command_count"],
            "help_text_tokens": cli_total,
        },
        "comparison": {
            "schema_overhead_delta": mcp_total - cli_total,
            "schema_overhead_ratio": mcp_total / cli_total if cli_total > 0 else None,
        },
        "amortized": {},
    }

    # Show amortized cost for different conversation lengths
    for n_ops in [1, 5, 10, 25, 50, 100]:
        report["amortized"][f"per_{n_ops}_ops"] = {
            "mcp_per_op": mcp_total / n_ops,
            "cli_per_op": cli_total / n_ops,
            "delta_per_op": (mcp_total - cli_total) / n_ops,
        }

    # --- Output ---
    print("=== Tool Schema Overhead Analysis ===")
    print(f"Token counter: {tc.mode}")
    print()
    print(
        f"MCP tool schemas:     {mcp_tool_tokens:>6} tokens ({len(mcp_tools) or 29} tools)"
    )
    print(
        f"MCP resource schemas: {mcp_resource_tokens:>6} tokens ({len(mcp_resources) or 20} resources)"
    )
    print(f"MCP total:            {mcp_total:>6} tokens")
    print()
    print(
        f"CLI help text:        {cli_total:>6} tokens ({cli_info['command_count']} commands)"
    )
    print()
    delta = mcp_total - cli_total
    print(f"Delta (MCP - CLI):    {delta:>+6} tokens")
    if cli_total > 0:
        print(f"Ratio (MCP / CLI):    {mcp_total / cli_total:>6.2f}x")
    print()
    print("Amortized per-operation overhead:")
    for n_ops in [1, 5, 10, 25, 50]:
        mcp_amort = mcp_total / n_ops
        cli_amort = cli_total / n_ops
        delta_amort = delta / n_ops
        print(
            f"  {n_ops:>3} ops: MCP={mcp_amort:>7.1f}"
            f"  CLI={cli_amort:>7.1f}  delta={delta_amort:>+7.1f}"
        )

    # Save JSON
    from pathlib import Path

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fp:
        json.dump(report, fp, ensure_ascii=False, indent=2)
    print(f"\nReport: {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
