#!/usr/bin/env python3
"""Benchmark baseline (direct MCP) vs wrapper CLI on tokens/success/latency."""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class TokenCounter:
    def __init__(self, encoding_name: str | None) -> None:
        self.encoding_name = encoding_name
        self.mode = "heuristic_char4"
        self._encoder = None
        if encoding_name:
            try:
                import tiktoken  # type: ignore

                self._encoder = tiktoken.get_encoding(encoding_name)
                self.mode = f"tiktoken:{encoding_name}"
            except Exception:
                self.mode = "heuristic_char4"

    def count(self, text: str) -> int:
        if not text:
            return 0
        if self._encoder:
            return len(self._encoder.encode(text))
        return int(math.ceil(len(text) / 4.0))


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    ordered = sorted(values)
    idx = (len(ordered) - 1) * p
    low = int(math.floor(idx))
    high = int(math.ceil(idx))
    if low == high:
        return float(ordered[low])
    low_v = ordered[low]
    high_v = ordered[high]
    return float(low_v + (high_v - low_v) * (idx - low))


def format_template(value: str | None, context: dict[str, Any]) -> str | None:
    if value is None:
        return None
    rendered = value
    for key, val in context.items():
        rendered = rendered.replace(f"{{{key}}}", str(val))
    return rendered


def run_command(command: str, stdin_text: str | None, timeout_sec: float) -> dict[str, Any]:
    start = time.perf_counter()
    timed_out = False
    try:
        proc = subprocess.run(
            command,
            shell=True,
            text=True,
            input=stdin_text,
            capture_output=True,
            timeout=timeout_sec,
        )
        returncode = proc.returncode
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        returncode = 124
        stdout = exc.stdout or ""
        stderr = (exc.stderr or "") + f"\nTIMEOUT after {timeout_sec}s"
    end = time.perf_counter()
    return {
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
        "timed_out": timed_out,
        "latency_ms": (end - start) * 1000.0,
    }


def clip(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def validate_config(config: dict[str, Any]) -> None:
    if "scenarios" not in config or not isinstance(config["scenarios"], list):
        raise ValueError("Config must include a list field: scenarios")
    for idx, scenario in enumerate(config["scenarios"], start=1):
        if "id" not in scenario:
            raise ValueError(f"Scenario #{idx} missing id")
        for mode in ("baseline", "wrapper"):
            if mode not in scenario:
                raise ValueError(f"Scenario {scenario['id']} missing {mode}")
            if "command" not in scenario[mode]:
                raise ValueError(f"Scenario {scenario['id']} mode {mode} missing command")


def aggregate_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(runs)
    success_count = sum(1 for run in runs if run["success"])
    latencies = [float(run["latency_ms"]) for run in runs]
    input_tokens = sum(int(run["input_tokens"]) for run in runs)
    output_tokens = sum(int(run["output_tokens"]) for run in runs)
    return {
        "runs": total,
        "success_count": success_count,
        "success_rate": (success_count / total) if total else 0.0,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "latency_ms": {
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "max": max(latencies) if latencies else 0.0,
        },
        "failures": [run for run in runs if not run["success"]],
    }


def calc_reduction(baseline_value: float, wrapper_value: float) -> float | None:
    if baseline_value <= 0:
        return None
    return ((baseline_value - wrapper_value) / baseline_value) * 100.0


def render_summary(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(
        "Scenario                          BaseTok   WrapTok  Reduct%   "
        "BaseSucc   WrapSucc   BaseP95   WrapP95"
    )
    lines.append("-" * 94)
    total_base_tokens = 0
    total_wrap_tokens = 0
    total_base_runs = 0
    total_wrap_runs = 0
    total_base_success = 0
    total_wrap_success = 0
    total_base_p95: list[float] = []
    total_wrap_p95: list[float] = []
    for scenario in report["scenarios"]:
        sid = scenario["id"][:30]
        base = scenario["baseline"]
        wrap = scenario["wrapper"]
        red = scenario["comparison"]["token_reduction_pct"]
        red_txt = f"{red:7.2f}" if red is not None else "   n/a "
        lines.append(
            f"{sid:<30} {base['total_tokens']:>8} {wrap['total_tokens']:>9} {red_txt:>8} "
            f"{base['success_rate'] * 100:>9.2f} {wrap['success_rate'] * 100:>10.2f} "
            f"{base['latency_ms']['p95']:>9.1f} {wrap['latency_ms']['p95']:>9.1f}"
        )
        total_base_tokens += base["total_tokens"]
        total_wrap_tokens += wrap["total_tokens"]
        total_base_runs += base["runs"]
        total_wrap_runs += wrap["runs"]
        total_base_success += base["success_count"]
        total_wrap_success += wrap["success_count"]
        total_base_p95.append(base["latency_ms"]["p95"])
        total_wrap_p95.append(wrap["latency_ms"]["p95"])

    total_reduction = calc_reduction(total_base_tokens, total_wrap_tokens)
    total_reduction_txt = f"{total_reduction:7.2f}" if total_reduction is not None else "   n/a "
    base_success = (total_base_success / total_base_runs * 100.0) if total_base_runs else 0.0
    wrap_success = (total_wrap_success / total_wrap_runs * 100.0) if total_wrap_runs else 0.0
    base_p95 = sum(total_base_p95) / len(total_base_p95) if total_base_p95 else 0.0
    wrap_p95 = sum(total_wrap_p95) / len(total_wrap_p95) if total_wrap_p95 else 0.0
    lines.append("-" * 94)
    lines.append(
        f"{'TOTAL':<30} {total_base_tokens:>8} {total_wrap_tokens:>9} {total_reduction_txt:>8} "
        f"{base_success:>9.2f} {wrap_success:>10.2f} {base_p95:>9.1f} {wrap_p95:>9.1f}"
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario-file", required=True, help="JSON scenario file path")
    parser.add_argument("--out", default="", help="Report output path (JSON)")
    parser.add_argument("--timeout", type=float, default=20.0, help="Timeout seconds per run")
    parser.add_argument(
        "--encoding",
        default="o200k_base",
        help="tiktoken encoding name (fallback to heuristic if unavailable)",
    )
    parser.add_argument(
        "--repeat-factor",
        type=int,
        default=1,
        help="Multiply iterations for each scenario",
    )
    parser.add_argument(
        "--max-preview",
        type=int,
        default=220,
        help="Max chars stored for stdout/stderr previews",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print rendered commands without executing",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when any run fails",
    )
    args = parser.parse_args()

    scenario_path = Path(args.scenario_file)
    if not scenario_path.exists():
        raise SystemExit(f"Scenario file not found: {scenario_path}")

    with scenario_path.open("r", encoding="utf-8") as fp:
        config = json.load(fp)
    validate_config(config)

    token_counter = TokenCounter(args.encoding)
    defaults = config.get("defaults", {})
    generated_at = datetime.now(timezone.utc).isoformat()

    report: dict[str, Any] = {
        "name": config.get("name", scenario_path.stem),
        "description": config.get("description", ""),
        "generated_at_utc": generated_at,
        "scenario_file": str(scenario_path),
        "token_counter_mode": token_counter.mode,
        "defaults": defaults,
        "scenarios": [],
    }

    any_failure = False

    for scenario in config["scenarios"]:
        sid = scenario["id"]
        iterations = int(scenario.get("iterations", defaults.get("iterations", 10)))
        warmup = int(scenario.get("warmup", defaults.get("warmup", 2)))
        if iterations <= 0:
            raise ValueError(f"Scenario {sid}: iterations must be > 0")
        if warmup < 0:
            raise ValueError(f"Scenario {sid}: warmup must be >= 0")
        runs_by_mode: dict[str, list[dict[str, Any]]] = {"baseline": [], "wrapper": []}

        for mode in ("baseline", "wrapper"):
            op = scenario[mode]
            success_regex = op.get("success_regex")
            expected_exit = int(op.get("expected_exit", 0))

            for run_idx in range(warmup + (iterations * args.repeat_factor)):
                context = {
                    "scenario_id": sid,
                    "iteration": run_idx,
                    "mode": mode,
                }
                command = format_template(op["command"], context)
                stdin_text = format_template(op.get("stdin"), context)
                request_text = format_template(op.get("request_text"), context)
                if request_text is None:
                    if stdin_text:
                        request_text = f"{command}\n{stdin_text}"
                    else:
                        request_text = command

                if args.dry_run:
                    print(f"[dry-run] {sid}:{mode}:{run_idx} -> {command}")
                    continue

                result = run_command(command, stdin_text, args.timeout)
                combined_output = (result["stdout"] or "") + (result["stderr"] or "")

                success = result["returncode"] == expected_exit
                if success and success_regex:
                    success = re.search(success_regex, combined_output, flags=re.MULTILINE) is not None

                record = {
                    "scenario_id": sid,
                    "mode": mode,
                    "iteration": run_idx,
                    "returncode": result["returncode"],
                    "timed_out": result["timed_out"],
                    "latency_ms": result["latency_ms"],
                    "success": success,
                    "input_tokens": token_counter.count(request_text),
                    "output_tokens": token_counter.count(combined_output),
                    "total_tokens": token_counter.count(request_text)
                    + token_counter.count(combined_output),
                    "stdout_preview": clip(result["stdout"], args.max_preview),
                    "stderr_preview": clip(result["stderr"], args.max_preview),
                }

                if run_idx >= warmup:
                    runs_by_mode[mode].append(record)
                    if not success:
                        any_failure = True

        if args.dry_run:
            continue

        baseline_agg = aggregate_runs(runs_by_mode["baseline"])
        wrapper_agg = aggregate_runs(runs_by_mode["wrapper"])

        scenario_result = {
            "id": sid,
            "description": scenario.get("description", ""),
            "iterations": iterations * args.repeat_factor,
            "baseline": baseline_agg,
            "wrapper": wrapper_agg,
            "comparison": {
                "token_reduction_pct": calc_reduction(
                    baseline_agg["total_tokens"], wrapper_agg["total_tokens"]
                ),
                "success_rate_delta_pct_point": (wrapper_agg["success_rate"] - baseline_agg["success_rate"])
                * 100.0,
                "latency_p95_delta_pct": calc_reduction(
                    baseline_agg["latency_ms"]["p95"], wrapper_agg["latency_ms"]["p95"]
                ),
            },
            "runs": runs_by_mode,
        }
        report["scenarios"].append(scenario_result)

    if args.dry_run:
        return 0

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if args.out:
        output_path = Path(args.out)
    else:
        output_path = Path("reports") / f"benchmark-{timestamp}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fp:
        json.dump(report, fp, indent=2, ensure_ascii=False)

    print(render_summary(report))
    print(f"\nreport: {output_path}")
    print(f"token_counter: {token_counter.mode}")

    if args.strict and any_failure:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
