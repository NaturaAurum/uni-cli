#!/usr/bin/env python3
# pyright: reportImplicitRelativeImport=false, reportMissingImports=false

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from e2e_policy_engine import PolicyEngine, TaskResult
from e2e_task_defs import ALL_TASKS
from mcp_real_scenario import McpSession, resolve_instance_id
from run_real_benchmark import TokenCounter, calc_reduction


def parse_modes(mode_arg: str) -> list[str]:
    if mode_arg == "both":
        return ["baseline", "wrapper"]
    if mode_arg in ("baseline", "wrapper"):
        return [mode_arg]
    raise SystemExit(f"invalid --mode: {mode_arg}")


def select_tasks(tasks_arg: str) -> list[Any]:
    by_id = {task.id: task for task in ALL_TASKS}
    if tasks_arg == "all":
        return list(ALL_TASKS)
    selected: list[Any] = []
    for task_id in [x.strip() for x in tasks_arg.split(",") if x.strip()]:
        if task_id not in by_id:
            raise SystemExit(f"unknown task id: {task_id}")
        selected.append(by_id[task_id])
    if not selected:
        raise SystemExit("no tasks selected")
    return selected


def run_repetition(
    *,
    url: str,
    unity_instance_selector: str,
    timeout: float,
    mode: str,
    tasks: list[Any],
    token_counter: TokenCounter,
) -> tuple[str, list[TaskResult]]:
    session = McpSession(url=url, timeout_sec=timeout)
    session.initialize()
    resolved_instance = resolve_instance_id(session, unity_instance_selector)
    engine = PolicyEngine(session=session, token_counter=token_counter, mode=mode)
    engine.seed_facts = {"unity_instance": resolved_instance}

    results: list[TaskResult] = []
    for task in tasks:
        results.append(engine.execute_task(task))
    return resolved_instance, results


def aggregate_mode_results(results: list[TaskResult]) -> dict[str, Any]:
    runs = len(results)
    if runs == 0:
        return {
            "runs": 0,
            "success_count": 0,
            "success_rate": 0.0,
            "total_tokens": 0,
            "tool_response_tokens": 0,
            "rounds": 0,
            "followup_calls": 0,
            "followup_overhead_tokens": 0,
            "wall_clock_ms": 0.0,
            "system_prompt_tokens": 0,
            "tool_schema_tokens": 0,
            "unique_tools": [],
            "errors": [],
        }

    success_count = sum(1 for r in results if r.success)
    total_tokens = sum(r.total_tokens for r in results)
    tool_response_tokens = sum(r.tool_response_tokens for r in results)
    rounds = sum(r.rounds for r in results)
    followup_calls = sum(r.followup_calls for r in results)
    wall_clock_ms = sum(r.wall_clock_ms for r in results)
    system_prompt_tokens = sum(r.system_prompt_tokens for r in results)
    tool_schema_tokens = sum(r.tool_schema_tokens for r in results)
    followup_overhead_tokens = sum(
        sum(step.followup_tokens for step in r.steps) for r in results
    )
    unique_tools = sorted({tool for r in results for tool in r.unique_tools})
    errors = [r.error for r in results if r.error]
    return {
        "runs": runs,
        "success_count": success_count,
        "success_rate": success_count / runs,
        "total_tokens": int(round(total_tokens / runs)),
        "tool_response_tokens": int(round(tool_response_tokens / runs)),
        "rounds": int(round(rounds / runs)),
        "followup_calls": int(round(followup_calls / runs)),
        "followup_overhead_tokens": int(round(followup_overhead_tokens / runs)),
        "wall_clock_ms": wall_clock_ms / runs,
        "system_prompt_tokens": int(round(system_prompt_tokens / runs)),
        "tool_schema_tokens": int(round(tool_schema_tokens / runs)),
        "unique_tools": unique_tools,
        "errors": errors,
    }


def build_task_report(
    task: Any,
    baseline_results: list[TaskResult],
    wrapper_results: list[TaskResult],
) -> dict[str, Any]:
    baseline = aggregate_mode_results(baseline_results)
    wrapper = aggregate_mode_results(wrapper_results)
    token_reduction_pct = calc_reduction(
        float(baseline["total_tokens"]),
        float(wrapper["total_tokens"]),
    )
    return {
        "id": task.id,
        "name": task.name,
        "category": task.category,
        "baseline": baseline,
        "wrapper": wrapper,
        "comparison": {
            "token_reduction_pct": token_reduction_pct,
            "round_increase": wrapper["rounds"] - baseline["rounds"],
            "followup_overhead_tokens": wrapper["followup_overhead_tokens"],
        },
    }


def summarize_to_console(task_reports: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    lines.append(
        "Task                           Category      BaseTok  WrapTok  Red%   BaseRnd  WrapRnd  Followups"
    )
    lines.append("-" * 98)
    for row in task_reports:
        baseline = row["baseline"]
        wrapper = row["wrapper"]
        red = row["comparison"]["token_reduction_pct"]
        red_txt = f"{red:6.2f}" if isinstance(red, (int, float)) else "  n/a "
        lines.append(
            f"{row['id'][:30]:<30} {row['category'][:12]:<12} "
            f"{baseline['total_tokens']:>8} {wrapper['total_tokens']:>8} {red_txt:>6} "
            f"{baseline['rounds']:>8} {wrapper['rounds']:>8} {wrapper['followup_calls']:>10}"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8080/mcp")
    parser.add_argument("--unity-instance", default="uni-cli")
    parser.add_argument("--tasks", default="all")
    parser.add_argument(
        "--mode", default="both", choices=["baseline", "wrapper", "both"]
    )
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--encoding", default="o200k_base")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--out", default="reports/e2e-benchmark-latest.json")
    args = parser.parse_args()

    if args.repetitions <= 0:
        raise SystemExit("--repetitions must be > 0")

    tasks = select_tasks(args.tasks)
    modes = parse_modes(args.mode)
    token_counter = TokenCounter(args.encoding)

    run_matrix: dict[str, dict[str, list[TaskResult]]] = {
        task.id: {"baseline": [], "wrapper": []} for task in tasks
    }
    resolved_instances: list[str] = []

    for mode in modes:
        for _ in range(args.repetitions):
            resolved_instance, task_results = run_repetition(
                url=args.url,
                unity_instance_selector=args.unity_instance,
                timeout=args.timeout,
                mode=mode,
                tasks=tasks,
                token_counter=token_counter,
            )
            resolved_instances.append(resolved_instance)
            for result in task_results:
                run_matrix[result.task_id][mode].append(result)

    task_reports: list[dict[str, Any]] = []
    for task in tasks:
        baseline_results = run_matrix[task.id]["baseline"]
        wrapper_results = run_matrix[task.id]["wrapper"]
        if not baseline_results and "baseline" not in modes:
            baseline_results = []
        if not wrapper_results and "wrapper" not in modes:
            wrapper_results = []
        task_reports.append(build_task_report(task, baseline_results, wrapper_results))

    comparable = [
        t
        for t in task_reports
        if isinstance(t["comparison"]["token_reduction_pct"], (int, float))
    ]
    macro_avg = (
        sum(float(t["comparison"]["token_reduction_pct"]) for t in comparable)
        / len(comparable)
        if comparable
        else None
    )
    hurts = [
        t["id"]
        for t in comparable
        if float(t["comparison"]["token_reduction_pct"]) < 0.0
    ]
    total_baseline_tokens = sum(t["baseline"]["total_tokens"] for t in task_reports)
    total_wrapper_tokens = sum(t["wrapper"]["total_tokens"] for t in task_reports)

    report = {
        "name": "tier2-e2e-agent-benchmark",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "url": args.url,
        "unity_instance_selector": args.unity_instance,
        "resolved_instances": sorted(set(resolved_instances)),
        "token_counter_mode": token_counter.mode,
        "mode": args.mode,
        "repetitions": args.repetitions,
        "tasks": task_reports,
        "summary": {
            "macro_avg_token_reduction_pct": macro_avg,
            "tasks_where_wrapper_hurts": hurts,
            "total_baseline_tokens": total_baseline_tokens,
            "total_wrapper_tokens": total_wrapper_tokens,
        },
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fp:
        json.dump(report, fp, ensure_ascii=False, indent=2)

    print(summarize_to_console(task_reports))
    print("-" * 98)
    macro_txt = (
        f"{macro_avg:.2f}%"
        if isinstance(macro_avg, (int, float))
        else "n/a (requires both baseline and wrapper)"
    )
    print(
        f"macro_avg_token_reduction_pct={macro_txt} "
        f"total_baseline_tokens={total_baseline_tokens} "
        f"total_wrapper_tokens={total_wrapper_tokens}"
    )
    print(f"tasks_where_wrapper_hurts={','.join(hurts) if hurts else '-'}")
    print(f"report: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
