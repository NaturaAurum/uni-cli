"""Auto-lifecycle management for the MCP for Unity server.

Detects running Unity instances via ~/.unity-mcp/ status files,
and auto-starts/stops an mcpforunityserver subprocess in stdio mode.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

_STATUS_DIR_ENV = "UNITY_MCP_STATUS_DIR"
_DEFAULT_STATUS_DIR = Path.home() / ".unity-mcp"
_HEARTBEAT_STALE_SEC = 300.0
_DEFAULT_MCP_PKG = "mcpforunityserver"
_SHUTDOWN_GRACE_SEC = 5.0


@dataclass
class UnityStatus:
    project_name: str
    project_path: str
    unity_port: int
    unity_version: str
    last_heartbeat: str
    file_path: Path


@dataclass
class ServerHandle:
    process: subprocess.Popen[bytes]


def is_server_running(url: str, timeout_sec: float = 3.0) -> bool:
    base_url = url.rsplit("/mcp", 1)[0] if url.endswith("/mcp") else url
    health_url = f"{base_url}/health"

    try:
        req = urllib.request.Request(health_url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            if getattr(resp, "status", 200) < 400:
                return True
    except Exception:
        pass

    try:
        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 0,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "uni-cli-probe", "version": "0.0.1"},
                },
            }
        ).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            return getattr(resp, "status", 200) < 400
    except Exception:
        return False


def _status_dir() -> Path:
    env = os.environ.get(_STATUS_DIR_ENV)
    if env:
        return Path(env)
    return _DEFAULT_STATUS_DIR


def find_unity_instances() -> list[UnityStatus]:
    results = _find_instances_from_status_files()
    if results:
        return results
    return _find_instances_from_processes()


def _find_instances_from_status_files() -> list[UnityStatus]:
    sdir = _status_dir()
    if not sdir.is_dir():
        return []

    results: list[UnityStatus] = []
    now = time.time()

    for fp in sorted(sdir.glob("unity-mcp-status-*.json")):
        try:
            mtime = fp.stat().st_mtime
        except OSError:
            continue
        if (now - mtime) > _HEARTBEAT_STALE_SEC:
            continue

        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        results.append(
            UnityStatus(
                project_name=data.get("project_name", ""),
                project_path=data.get("project_path", ""),
                unity_port=int(data.get("unity_port", 0)),
                unity_version=data.get("unity_version", ""),
                last_heartbeat=data.get("last_heartbeat", ""),
                file_path=fp,
            )
        )

    return results


def _find_instances_from_processes() -> list[UnityStatus]:
    try:
        raw = subprocess.check_output(
            ["ps", "-eo", "args"],
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).decode("utf-8", errors="replace")
    except (subprocess.SubprocessError, OSError):
        return []

    seen_paths: set[str] = set()
    results: list[UnityStatus] = []
    for line in raw.splitlines():
        if "Unity" not in line or "-projectpath" not in line.lower():
            continue
        if "-batchMode" in line:
            continue
        parts = line.split()
        project_path = ""
        for i, part in enumerate(parts):
            if part.lower() == "-projectpath" and i + 1 < len(parts):
                project_path = parts[i + 1]
                break
        if not project_path or project_path in seen_paths:
            continue
        seen_paths.add(project_path)
        results.append(
            UnityStatus(
                project_name=Path(project_path).name,
                project_path=project_path,
                unity_port=0,
                unity_version="",
                last_heartbeat="",
                file_path=Path(),
            )
        )

    return results


def _find_uvx() -> str | None:
    return shutil.which("uvx")


def start_server(
    mcp_pkg: str = _DEFAULT_MCP_PKG,
) -> ServerHandle:
    uvx = _find_uvx()
    if not uvx:
        raise RuntimeError(
            "Cannot auto-start MCP server: 'uvx' not found.\n"
            "Install uv (https://docs.astral.sh/uv/) or start the server manually:\n"
            f"  uvx --from {mcp_pkg} mcp-for-unity"
        )

    cmd = [uvx, "--from", mcp_pkg, "mcp-for-unity"]

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )

    return ServerHandle(process=proc)


def stop_server(handle: ServerHandle) -> None:
    proc = handle.process
    if proc.poll() is not None:
        return

    try:
        if proc.stdin and not proc.stdin.closed:
            proc.stdin.close()
    except Exception:
        pass

    try:
        proc.wait(timeout=_SHUTDOWN_GRACE_SEC)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass


def ensure_server(verbose: bool = False) -> ServerHandle:
    instances = find_unity_instances()
    if not instances:
        raise RuntimeError("No Unity instances detected.\nPlease open a Unity project with unity-mcp installed.")

    if verbose:
        names = ", ".join(i.project_name or i.project_path for i in instances)
        _eprint(f"[uni-cli] Unity detected: {names}")
        _eprint("[uni-cli] Starting MCP server (stdio) ...")

    handle = start_server()

    if verbose:
        _eprint("[uni-cli] MCP server started.")

    return handle


def _eprint(msg: str) -> None:
    print(msg, file=sys.stderr)
