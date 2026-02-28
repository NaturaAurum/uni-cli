"""Entry point for uni-cli — token-efficient CLI for Unity Editor via MCP."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from uni_cli.formatter.compact import format_error, format_json, format_result
from uni_cli.transport.mcp_client import McpClient, McpError, resolve_instance


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="uni-cli",
        description="Token-efficient CLI for LLM agents to control Unity Editor.",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8080/mcp",
        help="MCP server URL (default: http://127.0.0.1:8080/mcp)",
    )
    parser.add_argument(
        "--instance",
        default=None,
        help="Unity instance selector (e.g. 'MyProject' or 'MyProject@hash')",
    )
    parser.add_argument(
        "--format",
        choices=["compact", "json"],
        default="compact",
        dest="output_format",
        help="Output format (default: compact)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="MCP request timeout in seconds (default: 30)",
    )

    sub = parser.add_subparsers(dest="command", help="Available commands")

    # ---- hierarchy ----
    hier = sub.add_parser("hierarchy", help="Scene hierarchy operations")
    hier_sub = hier.add_subparsers(dest="action")
    hier_ls = hier_sub.add_parser("ls", help="List scene hierarchy")
    hier_ls.add_argument("--fields", default="id,name,parent")
    hier_ls.add_argument("--limit", type=int, default=120)
    hier_ls.add_argument("--cursor", default="0")

    # ---- object ----
    obj = sub.add_parser("object", help="GameObject operations")
    obj_sub = obj.add_subparsers(dest="action")

    obj_create = obj_sub.add_parser("create", help="Create GameObject")
    obj_create.add_argument("--name", required=True)
    obj_create.add_argument(
        "--preset", default="empty", help="Primitive type: empty, Cube, Sphere, etc."
    )
    obj_create.add_argument("--pos", default="0,0,0", help="Position x,y,z")

    obj_get = obj_sub.add_parser("get", help="Get GameObject info")
    obj_get.add_argument("--target", required=True)

    obj_modify = obj_sub.add_parser("modify", help="Modify GameObject")
    obj_modify.add_argument("--target", required=True)
    obj_modify.add_argument("--pos", default=None, help="New position x,y,z")
    obj_modify.add_argument("--parent", default=None, help="New parent name")
    obj_modify.add_argument("--name", default=None, dest="new_name", help="Rename")
    obj_modify.add_argument(
        "--active", default=None, type=_parse_bool, help="Set active state (true/false)"
    )

    obj_delete = obj_sub.add_parser("delete", help="Delete GameObject")
    obj_delete.add_argument("--target", required=True)

    # ---- asset ----
    asset = sub.add_parser("asset", help="Asset operations")
    asset_sub = asset.add_subparsers(dest="action")

    asset_search = asset_sub.add_parser("search", help="Search assets")
    asset_search.add_argument("--query", default="")
    asset_search.add_argument("--filter-type", default=None)
    asset_search.add_argument("--fields", default="path,name")
    asset_search.add_argument("--limit", type=int, default=80)

    asset_info = asset_sub.add_parser("info", help="Get asset info")
    asset_info.add_argument("--path", required=True)

    asset_create = asset_sub.add_parser("create", help="Create asset")
    asset_create.add_argument("--path", required=True)
    asset_create.add_argument("--type", required=True, dest="asset_type")

    asset_delete = asset_sub.add_parser("delete", help="Delete asset")
    asset_delete.add_argument("--path", required=True)

    # ---- batch ----
    batch = sub.add_parser("batch", help="Batch operations")
    batch_sub = batch.add_subparsers(dest="action")
    batch_apply = batch_sub.add_parser("apply", help="Execute batch commands from file")
    batch_apply.add_argument("--file", required=True, dest="batch_file")

    # ---- subsystem commands ----
    for cmd_name, tool_desc in [
        ("ui-toolkit", "UI Toolkit operations (UXML, USS, VisualElements)"),
        ("addressables", "Addressables operations (groups, entries, labels)"),
        ("dots", "DOTS/ECS operations (worlds, entities, systems)"),
        ("shader-graph", "Shader Graph operations (graphs, shaders, variants)"),
    ]:
        ss = sub.add_parser(cmd_name, help=tool_desc)
        ss.add_argument("action", help="Tool action (e.g. list_documents, create)")
        ss.add_argument(
            "--args",
            default="{}",
            dest="extra_args",
            help="Extra arguments as JSON string",
        )

    # ---- tools ----
    sub.add_parser("tools", help="List available MCP tools")

    return parser


def _parse_bool(val: str) -> bool:
    if val.lower() in ("true", "1", "yes"):
        return True
    if val.lower() in ("false", "0", "no"):
        return False
    raise argparse.ArgumentTypeError(f"Expected bool, got '{val}'")


def _dispatch(
    client: McpClient, instance_id: str, args: argparse.Namespace
) -> tuple[str, str, dict[str, Any]]:
    """Dispatch command and return (command, action, result_data)."""
    cmd = args.command
    action = getattr(args, "action", None) or ""

    if cmd == "hierarchy":
        if action == "ls":
            from uni_cli.commands.hierarchy import run_ls

            data = run_ls(client, instance_id, args.fields, args.limit, args.cursor)
            return cmd, action, data
    elif cmd == "object":
        if action == "create":
            from uni_cli.commands.object import run_create

            data = run_create(client, instance_id, args.name, args.preset, args.pos)
            return cmd, action, data
        elif action == "get":
            from uni_cli.commands.object import run_get

            data = run_get(client, instance_id, args.target)
            return cmd, action, data
        elif action == "modify":
            from uni_cli.commands.object import run_modify

            data = run_modify(
                client,
                instance_id,
                args.target,
                pos=args.pos,
                parent=args.parent,
                name=args.new_name,
                active=args.active,
            )
            return cmd, action, data
        elif action == "delete":
            from uni_cli.commands.object import run_delete

            data = run_delete(client, instance_id, args.target)
            return cmd, action, data
    elif cmd == "asset":
        if action == "search":
            from uni_cli.commands.asset import run_search

            data = run_search(
                client,
                instance_id,
                args.query,
                args.filter_type,
                args.fields,
                args.limit,
            )
            return cmd, action, data
        elif action == "info":
            from uni_cli.commands.asset import run_info

            data = run_info(client, instance_id, args.path)
            return cmd, action, data
        elif action == "create":
            from uni_cli.commands.asset import run_create

            data = run_create(client, instance_id, args.path, args.asset_type)
            return cmd, action, data
        elif action == "delete":
            from uni_cli.commands.asset import run_delete

            data = run_delete(client, instance_id, args.path)
            return cmd, action, data
    elif cmd == "batch":
        if action == "apply":
            from uni_cli.commands.batch import run_apply

            data = run_apply(client, instance_id, args.batch_file)
            return cmd, action, data
    elif cmd in ("ui-toolkit", "addressables", "dots", "shader-graph"):
        from uni_cli.commands.subsystem import run_subsystem

        extra = json.loads(args.extra_args) if args.extra_args != "{}" else None
        data = run_subsystem(client, instance_id, cmd, action, extra)
        return cmd, action, data
    elif cmd == "tools":
        tools = client.list_tools()
        return (
            cmd,
            "list",
            {
                "tools": [
                    {
                        "name": t.get("name", "?"),
                        "description": (t.get("description") or "")[:80],
                    }
                    for t in tools
                ]
            },
        )

    return cmd, action, {"success": False, "error": f"Unknown command: {cmd} {action}"}


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    # Connect to MCP server
    try:
        client = McpClient(url=args.url, timeout_sec=args.timeout)
        client.initialize()
    except McpError as exc:
        print(format_error(exc.code, exc.message))
        return 1
    except Exception as exc:
        print(format_error("CONNECTION_ERROR", str(exc)))
        return 1

    # Resolve Unity instance
    try:
        instance_id = resolve_instance(client, args.instance)
    except McpError as exc:
        print(format_error(exc.code, exc.message))
        return 1

    # Dispatch command
    try:
        cmd, action, data = _dispatch(client, instance_id, args)
    except McpError as exc:
        print(format_error(exc.code, exc.message))
        return 1
    except Exception as exc:
        print(format_error("INTERNAL_ERROR", str(exc)))
        return 1
    finally:
        client.close()

    # Check for error in result
    if isinstance(data, dict) and data.get("success") is False:
        err_msg = data.get("error") or data.get("message") or "unknown_error"
        print(format_error("TOOL_ERROR", str(err_msg)))
        return 1

    # Format output
    if args.output_format == "json":
        print(format_json(data))
    else:
        fields = None
        limit = 120
        cursor = "0"
        if hasattr(args, "fields") and args.fields:
            fields = [f.strip() for f in args.fields.split(",")]
        if hasattr(args, "limit"):
            limit = args.limit
        if hasattr(args, "cursor"):
            cursor = args.cursor
        print(
            format_result(cmd, action, data, fields=fields, limit=limit, cursor=cursor)
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
