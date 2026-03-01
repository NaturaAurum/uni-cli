#!/usr/bin/env python3
# pyright: reportImplicitRelativeImport=false
"""Unity load test — verify 4 UPM package tools are registered and callable.

Implements Task 2 (docs/tasks/02-unity-load-test.md):
  2-1. MCP tools/list shows the 4 new tools
  2-2. Each tool responds to a basic action call
  2-3. Connectivity + session health check
       (If MCP initializes and tools respond, Unity compiled without errors.
        Direct Unity Console access is not available via MCP.)

Usage:
  python3 bench/scripts/verify_tools_load_test.py [--url http://127.0.0.1:8080/mcp]
  python3 bench/scripts/verify_tools_load_test.py --out bench/reports/load-test.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp_real_scenario import McpSession, parse_text_json, resolve_instance_id

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXPECTED_TOOLS = [
    "manage_ui_toolkit",
    "manage_addressables",
    "manage_dots",
    "manage_shader_graph",
]

# Basic action per tool: (tool_name, action, expect_error_substring_or_None)
# For optional packages (addressables, dots), "not installed" is an expected
# error when the package isn't present in the Unity project.
BASIC_CALLS: list[tuple[str, str, str | None]] = [
    ("manage_ui_toolkit", "list_documents", None),
    ("manage_shader_graph", "list_graphs", None),
    ("manage_addressables", "list_groups", "not installed"),
    ("manage_dots", "list_worlds", "not installed"),
]


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""
    elapsed_ms: float = 0.0


@dataclass
class LoadTestReport:
    timestamp: str = ""
    url: str = ""
    instance_id: str = ""
    checks: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Test phases
# ---------------------------------------------------------------------------


def _list_tools(session: McpSession) -> list[dict[str, Any]]:
    """Call MCP tools/list and return the tool list."""
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
    if not event:
        raise RuntimeError(f"tools/list failed: {raw[:500]}")
    if "error" in event:
        raise RuntimeError(f"tools/list error: {json.dumps(event['error'])}")
    result = event.get("result", {})
    return result.get("tools", [])


def check_tools_registered(session: McpSession) -> list[CheckResult]:
    """2-1: Verify all 4 tools appear in MCP tools/list."""
    t0 = time.monotonic()
    tools = _list_tools(session)
    elapsed = (time.monotonic() - t0) * 1000
    tool_names = {t.get("name", "") for t in tools}

    results: list[CheckResult] = []
    for expected in EXPECTED_TOOLS:
        ok = expected in tool_names
        results.append(
            CheckResult(
                name=f"registered:{expected}",
                passed=ok,
                detail=f"found in {len(tools)} tools"
                if ok
                else f"MISSING — {len(tools)} tools listed",
                elapsed_ms=round(elapsed, 1),
            )
        )
    return results


def _extract_text(result: dict[str, Any]) -> str:
    """Extract text content from an MCP tool result."""
    parts: list[str] = []
    for item in result.get("content", []):
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(str(item.get("text", "")))
    return "\n".join(parts).strip()


def check_basic_calls(session: McpSession, instance_id: str) -> list[CheckResult]:
    """2-2: Call each tool with a basic action and verify response."""
    results: list[CheckResult] = []
    for tool_name, action, expected_err in BASIC_CALLS:
        t0 = time.monotonic()
        try:
            result = session.call_tool(
                tool_name,
                {
                    "action": action,
                    "unity_instance": instance_id,
                },
            )
            elapsed = (time.monotonic() - t0) * 1000
            text = _extract_text(result)
            # Check for payload-level failure (success=false in text JSON)
            parsed = parse_text_json(text)
            if isinstance(parsed, dict) and parsed.get("success") is False:
                err_msg = str(
                    parsed.get("error")
                    or parsed.get("message")
                    or "unknown_error"
                )
                if expected_err and expected_err.lower() in err_msg.lower():
                    results.append(
                        CheckResult(
                            name=f"call:{tool_name}/{action}",
                            passed=True,
                            detail=f"expected error — {expected_err}",
                            elapsed_ms=round(elapsed, 1),
                        )
                    )
                else:
                    results.append(
                        CheckResult(
                            name=f"call:{tool_name}/{action}",
                            passed=False,
                            detail=f"payload error: {err_msg[:200]}",
                            elapsed_ms=round(elapsed, 1),
                        )
                    )
            else:
                # Genuine success
                results.append(
                    CheckResult(
                        name=f"call:{tool_name}/{action}",
                        passed=True,
                        detail=f"ok — {len(text)} chars",
                        elapsed_ms=round(elapsed, 1),
                    )
                )
        except RuntimeError as exc:
            elapsed = (time.monotonic() - t0) * 1000
            err_str = str(exc)
            if expected_err and expected_err.lower() in err_str.lower():
                # Expected error (e.g. optional package not installed)
                results.append(
                    CheckResult(
                        name=f"call:{tool_name}/{action}",
                        passed=True,
                        detail=f"expected error — {expected_err}",
                        elapsed_ms=round(elapsed, 1),
                    )
                )
            else:
                results.append(
                    CheckResult(
                        name=f"call:{tool_name}/{action}",
                        passed=False,
                        detail=f"ERROR: {err_str[:200]}",
                        elapsed_ms=round(elapsed, 1),
                    )
                )
    return results


def check_connectivity(url: str, timeout: float) -> CheckResult:
    """2-3: Verify MCP server is reachable and session initializes."""
    t0 = time.monotonic()
    try:
        session = McpSession(url=url, timeout_sec=timeout)
        session.initialize()
        elapsed = (time.monotonic() - t0) * 1000
        return CheckResult(
            name="connectivity",
            passed=True,
            detail=f"session={session.session_id or 'none'}",
            elapsed_ms=round(elapsed, 1),
        )
    except Exception as exc:
        elapsed = (time.monotonic() - t0) * 1000
        return CheckResult(
            name="connectivity",
            passed=False,
            detail=str(exc)[:200],
            elapsed_ms=round(elapsed, 1),
        )


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def build_report(
    url: str, instance_id: str, checks: list[CheckResult]
) -> LoadTestReport:
    report = LoadTestReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        url=url,
        instance_id=instance_id,
    )
    passed = 0
    failed = 0
    for c in checks:
        report.checks.append(
            {
                "name": c.name,
                "passed": c.passed,
                "detail": c.detail,
                "elapsed_ms": c.elapsed_ms,
            }
        )
        if c.passed:
            passed += 1
        else:
            failed += 1
    report.summary = {
        "total": passed + failed,
        "passed": passed,
        "failed": failed,
        "all_passed": failed == 0,
    }
    return report


def print_report(report: LoadTestReport) -> None:
    """Human-readable report to stderr."""
    w = sys.stderr.write
    w("\n")
    w("=" * 60 + "\n")
    w("  Unity Load Test — Tool Registration Verification\n")
    w("=" * 60 + "\n")
    w(f"  URL:      {report.url}\n")
    w(f"  Instance: {report.instance_id}\n")
    w(f"  Time:     {report.timestamp}\n")
    w("-" * 60 + "\n")
    for c in report.checks:
        mark = "PASS" if c["passed"] else "FAIL"
        w(f"  [{mark}] {c['name']:<40} {c['elapsed_ms']:>7.1f}ms\n")
        if c["detail"]:
            w(f"         {c['detail']}\n")
    w("-" * 60 + "\n")
    s = report.summary
    status = "ALL PASSED" if s["all_passed"] else f"{s['failed']} FAILED"
    w(f"  Result: {s['passed']}/{s['total']} passed — {status}\n")
    w("=" * 60 + "\n\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify uni-cli UPM tools are registered and callable via MCP."
    )
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8080/mcp",
        help="MCP server URL (default: http://127.0.0.1:8080/mcp)",
    )
    parser.add_argument(
        "--instance",
        default=None,
        help="Unity instance selector (default: first available)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="Per-request timeout in seconds (default: 15)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Write JSON report to file (default: stdout)",
    )
    args = parser.parse_args()

    all_checks: list[CheckResult] = []

    # Phase 0: Connectivity
    conn = check_connectivity(args.url, args.timeout)
    all_checks.append(conn)
    if not conn.passed:
        report = build_report(args.url, "", all_checks)
        print_report(report)
        _write_output(report, args.out)
        return 1

    # Set up session for remaining checks
    session = McpSession(url=args.url, timeout_sec=args.timeout)
    session.initialize()

    # Resolve instance
    try:
        instance_id = resolve_instance_id(session, args.instance or "")
    except Exception as exc:
        all_checks.append(
            CheckResult(
                name="instance_resolve",
                passed=False,
                detail=str(exc)[:200],
            )
        )
        report = build_report(args.url, "", all_checks)
        print_report(report)
        _write_output(report, args.out)
        return 1

    # Phase 1: tools/list (2-1)
    try:
        reg_checks = check_tools_registered(session)
        all_checks.extend(reg_checks)
    except Exception as exc:
        all_checks.append(
            CheckResult(
                name="tools_list",
                passed=False,
                detail=str(exc)[:200],
            )
        )

    # Phase 2: basic calls (2-2)
    call_checks = check_basic_calls(session, instance_id)
    all_checks.extend(call_checks)

    # Build and output report
    report = build_report(args.url, instance_id, all_checks)
    print_report(report)
    _write_output(report, args.out)

    return 0 if report.summary.get("all_passed") else 1


def _write_output(report: LoadTestReport, out_path: str | None) -> None:
    """Write JSON report to file or stdout."""
    data = {
        "timestamp": report.timestamp,
        "url": report.url,
        "instance_id": report.instance_id,
        "checks": report.checks,
        "summary": report.summary,
    }
    text = json.dumps(data, indent=2) + "\n"
    if out_path:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_text(text)
        sys.stderr.write(f"Report written to {out_path}\n")
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    sys.exit(main())
