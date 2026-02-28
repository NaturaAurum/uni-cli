#!/usr/bin/env python3
"""Run real Unity MCP scenarios for benchmark (baseline vs compact wrapper view)."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


def _post_sse_json(
    url: str,
    payload: dict[str, Any],
    session_id: str | None,
    timeout_sec: float,
) -> tuple[dict[str, Any] | None, str, str | None]:
    def read_sse_events(
        resp: Any, request_id: Any, timeout_seconds: float
    ) -> tuple[dict[str, Any] | None, str]:
        raw_lines: list[str] = []
        events: list[dict[str, Any]] = []
        started = time.monotonic()

        while True:
            if (time.monotonic() - started) > timeout_seconds:
                raise TimeoutError("sse_response_timeout")
            line_b = resp.readline()
            if not line_b:
                break
            line = line_b.decode("utf-8", errors="replace").rstrip("\n")
            raw_lines.append(line)
            if not line.startswith("data: "):
                continue
            chunk = line[6:].strip()
            if not chunk:
                continue
            try:
                event = json.loads(chunk)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            events.append(event)
            if request_id is None:
                return event, "\n".join(raw_lines)
            if str(event.get("id")) == str(request_id):
                return event, "\n".join(raw_lines)

        if events:
            return events[-1], "\n".join(raw_lines)
        return None, "\n".join(raw_lines)

    def poll_stream_event(
        target_url: str,
        sid: str | None,
        request_id: Any,
        timeout: float,
    ) -> tuple[dict[str, Any] | None, str, str | None]:
        get_req = urllib.request.Request(target_url, method="GET")
        get_req.add_header("Accept", "text/event-stream")
        if sid:
            get_req.add_header("mcp-session-id", sid)
        with urllib.request.urlopen(get_req, timeout=timeout) as get_resp:
            got_sid = get_resp.headers.get("mcp-session-id") or sid
            event, raw_text = read_sse_events(get_resp, request_id, timeout)
            return event, raw_text, got_sid

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    # Keep SSE support for compatibility but prefer JSON responses first.
    req.add_header("Accept", "application/json;q=1.0, text/event-stream;q=0.5")
    req.add_header("Content-Type", "application/json")
    if session_id:
        req.add_header("mcp-session-id", session_id)

    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            sid = resp.headers.get("mcp-session-id")
            status = getattr(resp, "status", 200)
            ctype = (resp.headers.get("content-type") or "").lower()
            req_id = payload.get("id")

            # Streamable HTTP may acknowledge POST with 202 and deliver result via GET stream.
            if status == 202:
                post_raw = resp.read().decode("utf-8", errors="replace")
                if req_id is None:
                    # Notification-style call: no response expected.
                    return None, post_raw, sid
                event, get_raw, got_sid = poll_stream_event(
                    url, sid or session_id, req_id, timeout_sec
                )
                raw = post_raw + ("\n" if post_raw and get_raw else "") + get_raw
                return event, raw, got_sid

            if "text/event-stream" in ctype:
                event, raw_text = read_sse_events(resp, req_id, timeout_sec)
                return event, raw_text, sid

            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        sid = exc.headers.get("mcp-session-id") if exc.headers else None
        return None, raw, sid
    except Exception as exc:
        return None, f"request_error: {exc}", None

    stripped = raw.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            obj = json.loads(stripped)
            if isinstance(obj, dict):
                return obj, raw, sid
        except json.JSONDecodeError:
            pass

    events: list[dict[str, Any]] = []
    for line in raw.splitlines():
        if line.startswith("data: "):
            chunk = line[6:].strip()
            if not chunk:
                continue
            try:
                events.append(json.loads(chunk))
            except json.JSONDecodeError:
                continue

    request_id = payload.get("id")
    if request_id is not None:
        for event in events:
            if event.get("id") == request_id:
                return event, raw, sid
    if events:
        return events[-1], raw, sid
    return None, raw, sid


@dataclass
class McpSession:
    url: str
    timeout_sec: float
    session_id: str | None = None
    seq: int = 1

    def initialize(self) -> None:
        msg = {
            "jsonrpc": "2.0",
            "id": self.seq,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "uni-cli-real-bench", "version": "0.1"},
            },
        }
        self.seq += 1
        event, raw, sid = _post_sse_json(self.url, msg, None, self.timeout_sec)
        if sid:
            self.session_id = sid
        if not event or "result" not in event:
            raise RuntimeError(f"initialize_failed: {raw[:500]}")

        # Optional init notification; ignore response shape.
        notify = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }
        _post_sse_json(self.url, notify, self.session_id, self.timeout_sec)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        msg = {
            "jsonrpc": "2.0",
            "id": self.seq,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        self.seq += 1
        event, raw, _ = _post_sse_json(self.url, msg, self.session_id, self.timeout_sec)
        if not event:
            raise RuntimeError(f"tools_call_failed:{name}: no event: {raw[:500]}")
        if "error" in event:
            raise RuntimeError(f"tools_call_failed:{name}: {json.dumps(event['error'])}")
        result = event.get("result", {})
        if result.get("isError"):
            raise RuntimeError(f"tools_call_isError:{name}: {json.dumps(result)[:500]}")
        return result

    def read_resource(self, uri: str) -> dict[str, Any]:
        msg = {
            "jsonrpc": "2.0",
            "id": self.seq,
            "method": "resources/read",
            "params": {"uri": uri},
        }
        self.seq += 1
        event, raw, _ = _post_sse_json(self.url, msg, self.session_id, self.timeout_sec)
        if not event:
            raise RuntimeError(f"resource_read_failed:{uri}: no event: {raw[:500]}")
        if "error" in event:
            raise RuntimeError(f"resource_read_failed:{uri}: {json.dumps(event['error'])}")
        return event.get("result", {})


def extract_text(result: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in result.get("content", []):
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(str(item.get("text", "")))
    return "\n".join(parts).strip()


def parse_text_json(text: str) -> Any:
    if not text:
        return None
    stripped = text.strip()
    if not stripped or stripped[0] not in "{[":
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return None


def ensure_success_text(text: str, context: str) -> None:
    obj = parse_text_json(text)
    if isinstance(obj, dict) and obj.get("success") is False:
        msg = obj.get("error") or obj.get("message") or obj.get("code") or "unknown_error"
        raise RuntimeError(f"{context}_failed:{msg}")


def resolve_instance_id(session: McpSession, selector: str) -> str:
    result = session.read_resource("mcpforunity://instances")
    contents = result.get("contents", [])
    if not contents:
        raise RuntimeError("no_instances_available")
    raw_text = ""
    for item in contents:
        if isinstance(item, dict) and item.get("uri") == "mcpforunity://instances":
            raw_text = str(item.get("text", ""))
            break
    payload = parse_text_json(raw_text)
    if not isinstance(payload, dict):
        raise RuntimeError(f"invalid_instances_payload:{raw_text[:300]}")
    instances = payload.get("instances", [])
    if not isinstance(instances, list) or not instances:
        raise RuntimeError("instance_list_empty")

    # 1) exact id match
    for inst in instances:
        if isinstance(inst, dict) and str(inst.get("id")) == selector:
            return str(inst["id"])

    # 2) full Name@hash prefix
    for inst in instances:
        if isinstance(inst, dict):
            iid = str(inst.get("id", ""))
            if iid.startswith(selector):
                return iid

    # 3) name exact
    by_name = [
        str(inst.get("id"))
        for inst in instances
        if isinstance(inst, dict) and str(inst.get("name")) == selector and inst.get("id")
    ]
    if len(by_name) == 1:
        return by_name[0]
    if len(by_name) > 1:
        raise RuntimeError(f"instance_selector_ambiguous:{selector}")

    available = ", ".join(
        str(inst.get("id"))
        for inst in instances
        if isinstance(inst, dict) and inst.get("id")
    )
    raise RuntimeError(f"instance_not_found:{selector}; available={available}")


def compact_hierarchy(text: str) -> str:
    """Contract-compliant compact output for hierarchy queries.
    Emits row lines with --fields id,name,parent, then summary."""
    obj = parse_text_json(text)
    if not isinstance(obj, dict):
        return f"ok op=hierarchy.query text_len={len(text)}"
    raw_data = obj.get("data")
    data = raw_data if isinstance(raw_data, dict) else obj
    nodes = data.get("hierarchy") or data.get("nodes") or data.get("items") or []
    if not isinstance(nodes, list):
        nodes = []
    count = len(nodes)
    next_cursor = data.get("next_cursor")
    lines: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        nid = node.get("instanceID") or node.get("id") or "-"
        name = node.get("name") or "-"
        parent = node.get("parentInstanceID") or node.get("parent") or "-"
        lines.append(f"row id={nid} name={name} parent={parent}")
    next_val = next_cursor if next_cursor is not None else "-"
    lines.append(f"ok op=hierarchy.query count={count} next={next_val} truncated=0")
    return "\n".join(lines)

def compact_create(text: str) -> str:
    obj = parse_text_json(text)
    if not isinstance(obj, dict):
        return f"ok op=object.create text_len={len(text)}"
    raw_data = obj.get("data")
    data = raw_data if isinstance(raw_data, dict) else obj
    name = data.get("name") or obj.get("name") or data.get("gameObjectName") or obj.get("target") or "-"
    go_id = data.get("instanceID") or data.get("id") or obj.get("instanceID") or obj.get("id") or "-"
    return f"ok op=object.create name={name} id={go_id}"


def compact_reparent(parent_name: str, child_name: str, text: str) -> str:
    obj = parse_text_json(text)
    if isinstance(obj, dict):
        target = obj.get("name") or obj.get("target") or child_name
        return f"ok op=object.reparent child={target} parent={parent_name}"
    return f"ok op=object.reparent child={child_name} parent={parent_name}"


def compact_asset_search(text: str) -> str:
    """Contract-compliant compact output for asset search.
    Emits row lines with --fields path,name, then summary."""
    obj = parse_text_json(text)
    if not isinstance(obj, dict):
        return f"ok op=asset.search text_len={len(text)}"
    raw_data = obj.get("data")
    data = raw_data if isinstance(raw_data, dict) else obj
    results = data.get("results") or data.get("assets") or data.get("items") or []
    if not isinstance(results, list):
        results = []
    count = len(results)
    raw_page = data.get("page")
    page = raw_page if raw_page is not None else data.get("page_number", 1)
    lines: list[str] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        path = item.get("path") or item.get("assetPath") or "-"
        name = item.get("name") or item.get("fileName") or "-"
        lines.append(f"row path={path} name={name}")
    next_val = page + 1 if count > 0 else "-"
    lines.append(f"ok op=asset.search count={count} next={next_val} truncated=0")
    return "\n".join(lines)

def compact_batch(text: str) -> str:
    """Contract-compliant compact output for batch operations.
    Summary only by default; includes up to 3 fail IDs per contract section 6."""
    obj = parse_text_json(text)
    if not isinstance(obj, dict):
        return f"ok op=batch.apply text_len={len(text)}"
    raw_data = obj.get("data")
    data = raw_data if isinstance(raw_data, dict) else obj
    results = data.get("results", [])
    if not isinstance(results, list):
        results = []
    total = len(results)
    fail_items = [x for x in results if isinstance(x, dict) and x.get("error")]
    fail = len(fail_items)
    ok_count = total - fail
    # Include up to 3 fail IDs per contract
    fail_ids = ",".join(
        str(x.get("id") or x.get("name") or f"item_{i}")
        for i, x in enumerate(fail_items[:3])
    )
    line = f"ok op=batch.apply total={total} ok_count={ok_count} fail_count={fail}"
    if fail_ids:
        line += f" fail_ids={fail_ids}"
    return line

def run_hierarchy(session: McpSession, unity_instance: str, mode: str, iteration: int) -> str:
    args = {
        "action": "get_hierarchy",
        "page_size": 120,
        "cursor": 0,
        "include_transform": True,
        "max_depth": 4,
        "unity_instance": unity_instance,
    }
    res = session.call_tool("manage_scene", args)
    text = extract_text(res)
    ensure_success_text(text, "hierarchy_query")
    if mode == "baseline":
        return text or json.dumps(res, ensure_ascii=False)
    return compact_hierarchy(text)


def run_create(session: McpSession, unity_instance: str, mode: str, iteration: int) -> str:
    obj_name = f"BenchObj_{int(time.time())}_{iteration}"
    args = {
        "action": "create",
        "name": obj_name,
        "primitive_type": "Cube",
        "position": [float(iteration % 5), 1.0, 0.0],
        "unity_instance": unity_instance,
    }
    res = session.call_tool("manage_gameobject", args)
    text = extract_text(res)
    ensure_success_text(text, "object_create")
    # Keep scene state stable across iterations/runs.
    try:
        session.call_tool(
            "manage_gameobject",
            {
                "action": "delete",
                "target": obj_name,
                "search_method": "by_name",
                "unity_instance": unity_instance,
            },
        )
    except Exception:
        pass
    if mode == "baseline":
        return text or json.dumps(res, ensure_ascii=False)
    return compact_create(text)


def run_reparent(session: McpSession, unity_instance: str, mode: str, iteration: int) -> str:
    suffix = f"{int(time.time())}_{iteration}"
    parent_name = f"BenchParent_{suffix}"
    child_name = f"BenchChild_{suffix}"

    create_parent = {
        "action": "create",
        "name": parent_name,
        "primitive_type": "Cube",
        "position": [0.0, 0.0, 0.0],
        "unity_instance": unity_instance,
    }
    create_child = {
        "action": "create",
        "name": child_name,
        "primitive_type": "Sphere",
        "position": [2.0, 0.0, 0.0],
        "unity_instance": unity_instance,
    }
    reparent = {
        "action": "modify",
        "target": child_name,
        "search_method": "by_name",
        "parent": parent_name,
        "unity_instance": unity_instance,
    }

    r1 = session.call_tool("manage_gameobject", create_parent)
    r2 = session.call_tool("manage_gameobject", create_child)
    r3 = session.call_tool("manage_gameobject", reparent)
    t1, t2, t3 = extract_text(r1), extract_text(r2), extract_text(r3)
    ensure_success_text(t1, "reparent_create_parent")
    ensure_success_text(t2, "reparent_create_child")
    ensure_success_text(t3, "reparent_modify")
    # Delete parent to remove the whole temporary subtree.
    try:
        session.call_tool(
            "manage_gameobject",
            {
                "action": "delete",
                "target": parent_name,
                "search_method": "by_name",
                "unity_instance": unity_instance,
            },
        )
    except Exception:
        pass

    if mode == "baseline":
        return json.dumps(
            {
                "create_parent": parse_text_json(t1) or t1,
                "create_child": parse_text_json(t2) or t2,
                "reparent": parse_text_json(t3) or t3,
            },
            ensure_ascii=False,
        )
    return compact_reparent(parent_name, child_name, t3)


def run_asset_search(session: McpSession, unity_instance: str, mode: str, iteration: int) -> str:
    args = {
        "action": "search",
        "path": "Assets",
        "filter_type": "Script",
        "page_size": 80,
        "page_number": 1,
        "generate_preview": False,
        "unity_instance": unity_instance,
    }
    res = session.call_tool("manage_asset", args)
    text = extract_text(res)
    ensure_success_text(text, "asset_search")
    if mode == "baseline":
        return text or json.dumps(res, ensure_ascii=False)
    return compact_asset_search(text)


def run_batch(session: McpSession, unity_instance: str, mode: str, iteration: int) -> str:
    suffix = f"{int(time.time())}_{iteration}"
    commands = [
        {
            "tool": "manage_gameobject",
            "params": {
                "action": "create",
                "name": f"BatchA_{suffix}",
                "primitive_type": "Cube",
                "position": [0.0, 0.0, 0.0]
            },
        },
        {
            "tool": "manage_gameobject",
            "params": {
                "action": "create",
                "name": f"BatchB_{suffix}",
                "primitive_type": "Sphere",
                "position": [1.0, 0.0, 0.0]
            },
        },
        {
            "tool": "manage_gameobject",
            "params": {
                "action": "modify",
                "target": f"BatchA_{suffix}",
                "search_method": "by_name",
                "position": [0.5, 1.0, 0.0]
            },
        },
    ]
    args = {
        "commands": commands,
        "parallel": False,
        "fail_fast": True,
        "max_parallelism": 1,
        "unity_instance": unity_instance
    }
    res = session.call_tool("batch_execute", args)
    text = extract_text(res)
    ensure_success_text(text, "batch_ops")
    # Best-effort cleanup to avoid benchmark drift.
    for name in (f"BatchA_{suffix}", f"BatchB_{suffix}"):
        try:
            session.call_tool(
                "manage_gameobject",
                {
                    "action": "delete",
                    "target": name,
                    "search_method": "by_name",
                    "unity_instance": unity_instance,
                },
            )
        except Exception:
            pass
    if mode == "baseline":
        return text or json.dumps(res, ensure_ascii=False)
    return compact_batch(text)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        required=True,
        choices=["hierarchy_query", "object_create", "reparent", "asset_search", "batch_ops"],
    )
    parser.add_argument("--mode", required=True, choices=["baseline", "wrapper"])
    parser.add_argument("--iteration", type=int, default=0)
    parser.add_argument("--url", default="http://127.0.0.1:8080/mcp")
    parser.add_argument("--unity-instance", default="uni-cli")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    session = McpSession(url=args.url, timeout_sec=args.timeout)
    session.initialize()
    resolved_instance = resolve_instance_id(session, args.unity_instance)

    if args.scenario == "hierarchy_query":
        out = run_hierarchy(session, resolved_instance, args.mode, args.iteration)
    elif args.scenario == "object_create":
        out = run_create(session, resolved_instance, args.mode, args.iteration)
    elif args.scenario == "reparent":
        out = run_reparent(session, resolved_instance, args.mode, args.iteration)
    elif args.scenario == "asset_search":
        out = run_asset_search(session, resolved_instance, args.mode, args.iteration)
    elif args.scenario == "batch_ops":
        out = run_batch(session, resolved_instance, args.mode, args.iteration)
    else:
        raise ValueError(f"unknown scenario: {args.scenario}")

    print(out)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"err code=SCENARIO_FAILED msg={exc}", file=sys.stderr)
        sys.exit(1)
