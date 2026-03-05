"""MCP Streamable HTTP transport client.

Handles JSON-RPC 2.0 over HTTP with SSE fallback, session management,
and instance resolution for unity-mcp servers.
"""

from __future__ import annotations

import json
import os
import select
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any


class McpError(Exception):
    """Raised when an MCP call fails."""

    def __init__(self, code: str, message: str, data: Any = None) -> None:
        self.code = code
        self.message = message
        self.data = data
        super().__init__(f"{code}: {message}")


def _read_sse_events(
    resp: Any,
    request_id: Any,
    timeout_sec: float,
) -> tuple[dict[str, Any] | None, str]:
    """Read SSE events from an HTTP response stream until matching id found."""
    raw_lines: list[str] = []
    events: list[dict[str, Any]] = []
    started = time.monotonic()

    while True:
        if (time.monotonic() - started) > timeout_sec:
            raise McpError("TIMEOUT", "SSE response timeout")
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


def _post_json(
    url: str,
    payload: dict[str, Any],
    session_id: str | None,
    timeout_sec: float,
) -> tuple[dict[str, Any] | None, str, str | None]:
    """Send a JSON-RPC request via HTTP POST, handling JSON and SSE responses."""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
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

            # 202 Accepted — result delivered via GET stream
            if status == 202:
                post_raw = resp.read().decode("utf-8", errors="replace")
                if req_id is None:
                    return None, post_raw, sid
                get_req = urllib.request.Request(url, method="GET")
                get_req.add_header("Accept", "text/event-stream")
                if sid or session_id:
                    get_req.add_header("mcp-session-id", sid or session_id)
                with urllib.request.urlopen(get_req, timeout=timeout_sec) as get_resp:
                    got_sid = get_resp.headers.get("mcp-session-id") or sid
                    event, raw = _read_sse_events(get_resp, req_id, timeout_sec)
                    return event, post_raw + "\n" + raw, got_sid

            # SSE stream response
            if "text/event-stream" in ctype:
                event, raw = _read_sse_events(resp, req_id, timeout_sec)
                return event, raw, sid

            # Plain JSON response
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        sid = exc.headers.get("mcp-session-id") if exc.headers else None
        return None, raw, sid
    except McpError:
        raise
    except Exception as exc:
        return None, f"request_error: {exc}", None

    # Try to parse as JSON
    stripped = raw.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            obj = json.loads(stripped)
            if isinstance(obj, dict):
                return obj, raw, sid
        except json.JSONDecodeError:
            pass

    # Try to extract from SSE-formatted text
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
class McpClient:
    """MCP JSON-RPC client over Streamable HTTP transport."""

    url: str
    timeout_sec: float = 30.0
    session_id: str | None = None
    _seq: int = field(default=1, init=False, repr=False)

    def initialize(self) -> dict[str, Any]:
        """Perform MCP handshake: initialize + notifications/initialized."""
        msg = {
            "jsonrpc": "2.0",
            "id": self._seq,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "uni-cli", "version": "0.1.0"},
            },
        }
        self._seq += 1
        event, raw, sid = _post_json(self.url, msg, None, self.timeout_sec)
        if sid:
            self.session_id = sid
        if not event or "result" not in event:
            raise McpError("INIT_FAILED", f"initialize failed: {raw[:500]}")

        # Send initialized notification (no response expected)
        notify = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }
        _post_json(self.url, notify, self.session_id, self.timeout_sec)
        return event["result"]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call an MCP tool and return the result dict.

        Returns the 'result' field from the JSON-RPC response which contains:
        - content: list of content items (type: "text", text: "...")
        - isError: bool
        """
        msg = {
            "jsonrpc": "2.0",
            "id": self._seq,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        self._seq += 1
        event, raw, _ = _post_json(self.url, msg, self.session_id, self.timeout_sec)
        if not event:
            raise McpError("NO_RESPONSE", f"tools/call {name}: no event: {raw[:500]}")
        if "error" in event:
            err = event["error"]
            raise McpError(
                str(err.get("code", "RPC_ERROR")),
                err.get("message", str(err)),
                err.get("data"),
            )
        result = event.get("result", {})
        if result.get("isError"):
            raise McpError("TOOL_ERROR", f"tool {name} returned error", result)
        return result

    def read_resource(self, uri: str) -> dict[str, Any]:
        """Read an MCP resource by URI."""
        msg = {
            "jsonrpc": "2.0",
            "id": self._seq,
            "method": "resources/read",
            "params": {"uri": uri},
        }
        self._seq += 1
        event, raw, _ = _post_json(self.url, msg, self.session_id, self.timeout_sec)
        if not event:
            raise McpError("NO_RESPONSE", f"resources/read {uri}: no event: {raw[:500]}")
        if "error" in event:
            err = event["error"]
            raise McpError(
                str(err.get("code", "RPC_ERROR")),
                err.get("message", str(err)),
                err.get("data"),
            )
        return event.get("result", {})

    def list_tools(self) -> list[dict[str, Any]]:
        """List all available MCP tools."""
        msg = {
            "jsonrpc": "2.0",
            "id": self._seq,
            "method": "tools/list",
            "params": {},
        }
        self._seq += 1
        event, raw, _ = _post_json(self.url, msg, self.session_id, self.timeout_sec)
        if not event:
            raise McpError("NO_RESPONSE", f"tools/list: no event: {raw[:500]}")
        if "error" in event:
            err = event["error"]
            raise McpError(
                str(err.get("code", "RPC_ERROR")),
                err.get("message", str(err)),
                err.get("data"),
            )
        result = event.get("result", {})
        return result.get("tools", [])

    def close(self) -> None:
        """Gracefully close the MCP session via HTTP DELETE."""
        if not self.session_id:
            return
        try:
            req = urllib.request.Request(self.url, method="DELETE")
            req.add_header("mcp-session-id", self.session_id)
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass


def extract_text(result: dict[str, Any]) -> str:
    """Extract text content from an MCP tool result."""
    parts: list[str] = []
    for item in result.get("content", []):
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(str(item.get("text", "")))
    return "\n".join(parts).strip()


def parse_result_json(result: dict[str, Any]) -> Any:
    """Extract and parse JSON from an MCP tool result's text content."""
    text = extract_text(result)
    if not text:
        return None
    stripped = text.strip()
    if not stripped or stripped[0] not in "{[":
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return None


def resolve_instance(client: McpClient | StdioMcpClient, selector: str | None) -> str:
    """Resolve a Unity instance selector to a full instance ID.

    Matching priority: exact id > id prefix > name exact > first available.
    """
    result = client.read_resource("mcpforunity://instances")
    contents = result.get("contents", [])
    if not contents:
        raise McpError("NO_INSTANCES", "No Unity instances available")

    raw_text = ""
    for item in contents:
        if isinstance(item, dict) and item.get("uri") == "mcpforunity://instances":
            raw_text = str(item.get("text", ""))
            break

    try:
        payload = json.loads(raw_text) if raw_text else {}
    except json.JSONDecodeError:
        raise McpError("INVALID_RESPONSE", f"Bad instances payload: {raw_text[:200]}")

    instances = payload.get("instances", [])
    if not isinstance(instances, list) or not instances:
        raise McpError("NO_INSTANCES", "Instance list empty")

    # No selector — return first available
    if not selector:
        first = instances[0]
        if isinstance(first, dict) and first.get("id"):
            return str(first["id"])
        raise McpError("NO_INSTANCES", "No valid instance found")

    # 1) Exact id match
    for inst in instances:
        if isinstance(inst, dict) and str(inst.get("id")) == selector:
            return str(inst["id"])

    # 2) Id prefix match
    for inst in instances:
        if isinstance(inst, dict):
            iid = str(inst.get("id", ""))
            if iid.startswith(selector):
                return iid

    # 3) Name exact match
    by_name = [
        str(inst.get("id"))
        for inst in instances
        if isinstance(inst, dict) and str(inst.get("name")) == selector and inst.get("id")
    ]
    if len(by_name) == 1:
        return by_name[0]
    if len(by_name) > 1:
        raise McpError("AMBIGUOUS_INSTANCE", f"Multiple instances match '{selector}'")

    available = ", ".join(str(inst.get("id")) for inst in instances if isinstance(inst, dict) and inst.get("id"))
    raise McpError(
        "INSTANCE_NOT_FOUND",
        f"Instance '{selector}' not found; available: {available}",
    )


class _LineReader:
    """Buffered line reader with select()-based timeout. Returns None on timeout, b'' on EOF."""

    __slots__ = ("_fd", "_buf")

    def __init__(self, fd: int) -> None:
        self._fd = fd
        self._buf = b""

    def readline(self, timeout: float) -> bytes | None:
        deadline = time.monotonic() + timeout
        while True:
            nl = self._buf.find(b"\n")
            if nl >= 0:
                line = self._buf[: nl + 1]
                self._buf = self._buf[nl + 1 :]
                return line

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None

            ready, _, _ = select.select([self._fd], [], [], min(remaining, 1.0))
            if not ready:
                continue

            chunk = os.read(self._fd, 8192)
            if not chunk:
                if self._buf:
                    data = self._buf
                    self._buf = b""
                    return data
                return b""

            self._buf += chunk


class StdioMcpClient:
    """MCP JSON-RPC client over subprocess stdio pipe. Same interface as McpClient."""

    def __init__(self, proc: subprocess.Popen[bytes], timeout_sec: float = 30.0) -> None:
        self._proc = proc
        self.timeout_sec = timeout_sec
        self._seq: int = 1
        assert proc.stdout is not None
        self._reader = _LineReader(proc.stdout.fileno())

    def _send(self, msg: dict[str, Any]) -> None:
        assert self._proc.stdin is not None
        data = json.dumps(msg, separators=(",", ":")) + "\n"
        self._proc.stdin.write(data.encode("utf-8"))
        self._proc.stdin.flush()

    def _recv(self, request_id: int) -> dict[str, Any]:
        deadline = time.monotonic() + self.timeout_sec
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                raise McpError("SERVER_DIED", "MCP server process exited unexpectedly")

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break

            raw = self._reader.readline(min(remaining, 2.0))
            if raw is None:
                continue
            if raw == b"":
                raise McpError("SERVER_DIED", "MCP server closed stdout")

            raw = raw.strip()
            if not raw:
                continue

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if not isinstance(msg, dict):
                continue

            if "id" not in msg:
                continue

            if msg.get("id") == request_id:
                return msg

        raise McpError("TIMEOUT", f"Timeout waiting for response (id={request_id})")

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        req_id = self._seq
        self._seq += 1
        self._send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        return self._recv(req_id)

    def initialize(self) -> dict[str, Any]:
        resp = self._request(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "uni-cli", "version": "0.1.0"},
            },
        )
        if "error" in resp:
            err = resp["error"]
            raise McpError("INIT_FAILED", f"initialize failed: {err}")

        self._send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        return resp.get("result", {})

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        resp = self._request("tools/call", {"name": name, "arguments": arguments})
        if "error" in resp:
            err = resp["error"]
            raise McpError(
                str(err.get("code", "RPC_ERROR")),
                err.get("message", str(err)),
                err.get("data"),
            )
        result = resp.get("result", {})
        if result.get("isError"):
            raise McpError("TOOL_ERROR", f"tool {name} returned error", result)
        return result

    def read_resource(self, uri: str) -> dict[str, Any]:
        resp = self._request("resources/read", {"uri": uri})
        if "error" in resp:
            err = resp["error"]
            raise McpError(
                str(err.get("code", "RPC_ERROR")),
                err.get("message", str(err)),
                err.get("data"),
            )
        return resp.get("result", {})

    def list_tools(self) -> list[dict[str, Any]]:
        resp = self._request("tools/list", {})
        if "error" in resp:
            err = resp["error"]
            raise McpError(
                str(err.get("code", "RPC_ERROR")),
                err.get("message", str(err)),
                err.get("data"),
            )
        return resp.get("result", {}).get("tools", [])

    def close(self) -> None:
        pass
