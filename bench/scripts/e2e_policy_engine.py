#!/usr/bin/env python3
# pyright: reportImplicitRelativeImport=false, reportMissingImports=false, reportOptionalMemberAccess=false

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from e2e_task_defs import PolicyStep, TaskDef
from mcp_real_scenario import (
    McpSession,
    compact_asset_search,
    compact_batch,
    compact_create,
    compact_hierarchy,
    extract_text,
    parse_text_json,
)
from run_real_benchmark import TokenCounter


@dataclass
class StepResult:
    step_index: int
    action: str
    tool_name: str
    request_tokens: int
    response_tokens: int
    followup_tokens: int
    latency_ms: float
    success: bool
    facts_extracted: dict[str, Any]
    is_followup: bool


@dataclass
class TaskResult:
    task_id: str
    mode: str
    success: bool
    steps: list[StepResult]
    total_tokens: int
    tool_response_tokens: int
    rounds: int
    followup_calls: int
    unique_tools: set[str]
    wall_clock_ms: float
    system_prompt_tokens: int
    tool_schema_tokens: int
    error: str | None


class PolicyEngine:
    def __init__(self, session: McpSession, token_counter: TokenCounter, mode: str):
        self.session = session
        self.token_counter = token_counter
        self.mode = mode
        self.facts: dict[str, Any] = {}
        self.seed_facts: dict[str, Any] = {}
        self._rounds = 0
        self._followup_calls = 0
        self._unique_tools: set[str] = set()

    def execute_task(self, task: TaskDef) -> TaskResult:
        self.facts = dict(self.seed_facts)
        self._rounds = 0
        self._followup_calls = 0
        self._unique_tools = set()
        steps: list[StepResult] = []
        error: str | None = None
        success = True
        started = time.perf_counter()
        system_prompt_tokens = self.token_counter.count(self._system_prompt(task))
        tool_schema_tokens = self._tool_schema_tokens()

        for index, step in enumerate(
            task.setup_steps + task.verify_steps + task.cleanup_steps
        ):
            result = self._execute_step(index, step)
            steps.append(result)
            if not result.success:
                success = False
                error = result.facts_extracted.get("error", "step_failed")
                break

        total_tokens = sum(
            s.request_tokens + s.response_tokens + s.followup_tokens for s in steps
        )
        tool_response_tokens = sum(s.response_tokens for s in steps)
        wall_clock_ms = (time.perf_counter() - started) * 1000.0
        return TaskResult(
            task_id=task.id,
            mode=self.mode,
            success=success,
            steps=steps,
            total_tokens=total_tokens + system_prompt_tokens + tool_schema_tokens,
            tool_response_tokens=tool_response_tokens,
            rounds=self._rounds,
            followup_calls=self._followup_calls,
            unique_tools=set(self._unique_tools),
            wall_clock_ms=wall_clock_ms,
            system_prompt_tokens=system_prompt_tokens,
            tool_schema_tokens=tool_schema_tokens,
            error=error,
        )

    def _execute_step(self, step_index: int, step: PolicyStep) -> StepResult:
        request_tokens = 0
        response_tokens = 0
        followup_tokens = 0
        latency_ms = 0.0
        aggregated_facts: dict[str, Any] = {}
        success = True
        expanded_args = self._expand_args(step.arguments)

        try:
            for call_args in expanded_args:
                req_text = self._request_text(step.tool_name, call_args)
                request_tokens += self.token_counter.count(req_text)
                response_text, parsed, call_ms = self._invoke(step.tool_name, call_args)
                latency_ms += call_ms
                response_tokens += self.token_counter.count(response_text)
                step_facts = self._extract_facts(
                    step.extract, response_text, parsed, call_args
                )
                aggregated_facts = self._merge_facts(aggregated_facts, step_facts)
                self.facts = self._merge_facts(self.facts, step_facts)

                if self.mode == "wrapper" and step.wrapper_needs_followup:
                    followup_tokens += self._run_followups(step, call_args, parsed)

            if step.action == "followup" and step.tool_name == "manage_material":
                if self.facts.get("bench_glow_found"):
                    success = True

        except Exception as exc:
            success = False
            aggregated_facts["error"] = str(exc)

        return StepResult(
            step_index=step_index,
            action=step.action,
            tool_name=step.tool_name,
            request_tokens=request_tokens,
            response_tokens=response_tokens,
            followup_tokens=followup_tokens,
            latency_ms=latency_ms,
            success=success,
            facts_extracted=aggregated_facts,
            is_followup=False,
        )

    def _expand_args(self, arguments: dict[str, Any]) -> list[dict[str, Any]]:
        loop_fact = arguments.get("__for_each_fact")
        if not isinstance(loop_fact, str):
            return [self._resolve_placeholders(arguments, None)]
        items = self.facts.get(loop_fact, [])
        if not isinstance(items, list):
            return [self._resolve_placeholders(arguments, None)]
        expanded: list[dict[str, Any]] = []
        for item in items:
            expanded.append(self._resolve_placeholders(arguments, item))
        return expanded or [self._resolve_placeholders(arguments, None)]

    def _resolve_placeholders(self, value: Any, item: Any) -> Any:
        if isinstance(value, dict):
            out: dict[str, Any] = {}
            for key, inner in value.items():
                if key == "__for_each_fact":
                    continue
                out[key] = self._resolve_placeholders(inner, item)
            return out
        if isinstance(value, list):
            return [self._resolve_placeholders(x, item) for x in value]
        if isinstance(value, str):
            if value == "{item}":
                return item
            resolved = value
            if "{item}" in resolved:
                resolved = resolved.replace("{item}", str(item))
            for fact_key, fact_value in self.facts.items():
                token = "{" + fact_key + "}"
                if token in resolved:
                    resolved = resolved.replace(token, str(fact_value))
            return resolved
        return value

    def _request_text(self, tool_name: str, arguments: dict[str, Any]) -> str:
        return (
            f"{tool_name}:{json.dumps(arguments, sort_keys=True, ensure_ascii=False)}"
        )

    def _invoke(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> tuple[str, Any, float]:
        start = time.perf_counter()
        if tool_name == "read_resource":
            uri = str(arguments.get("uri") or arguments.get("uri_template") or "")
            if not uri:
                raise RuntimeError("missing_resource_uri")
            result = self.session.read_resource(uri)
            text = self._resource_text(result)
            latency_ms = (time.perf_counter() - start) * 1000.0
            self._rounds += 1
            self._unique_tools.add("read_resource")
            return text, parse_text_json(text), latency_ms

        call_args = dict(arguments)
        if "unity_instance" not in call_args and self.facts.get("unity_instance"):
            call_args["unity_instance"] = self.facts["unity_instance"]

        result = self.session.call_tool(tool_name, call_args)
        raw_text = extract_text(result)
        text = self._format_response(tool_name, call_args, raw_text, result)
        latency_ms = (time.perf_counter() - start) * 1000.0
        self._rounds += 1
        self._unique_tools.add(tool_name)
        return text, parse_text_json(raw_text) or parse_text_json(text), latency_ms

    def _format_response(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        raw_text: str,
        result: dict[str, Any],
    ) -> str:
        if self.mode == "baseline":
            return raw_text or json.dumps(result, ensure_ascii=False)
        action = str(arguments.get("action", ""))
        if tool_name == "manage_scene" and action == "get_hierarchy":
            return compact_hierarchy(raw_text)
        if tool_name == "manage_gameobject" and action == "create":
            return compact_create(raw_text)
        if tool_name == "manage_asset" and action == "search":
            return compact_asset_search(raw_text)
        if tool_name == "batch_execute":
            return compact_batch(raw_text)
        return raw_text or json.dumps(result, ensure_ascii=False)

    def _run_followups(
        self,
        step: PolicyStep,
        base_args: dict[str, Any],
        parsed: Any,
    ) -> int:
        if not step.followup_tool or not isinstance(step.followup_args, dict):
            return 0
        next_cursor = self._next_cursor_from_parsed(parsed)
        truncated = self._truncated_from_parsed(parsed)
        if not truncated and (next_cursor in (None, "-", "", 0, "0")):
            return 0

        total = 0
        guard = 0
        cursor = next_cursor
        while guard < 10 and (cursor not in (None, "-", "") or truncated):
            guard += 1
            followup_args = self._resolve_placeholders(
                step.followup_args, base_args.get("parent_id")
            )
            if cursor not in (None, "-", ""):
                if "cursor" in followup_args:
                    followup_args["cursor"] = cursor
                if "page_number" in followup_args and isinstance(cursor, (int, str)):
                    try:
                        followup_args["page_number"] = int(cursor)
                    except Exception:
                        pass
            req_text = self._request_text(step.followup_tool, followup_args)
            req_tokens = self.token_counter.count(req_text)
            response_text, followup_parsed, _ = self._invoke(
                step.followup_tool, followup_args
            )
            resp_tokens = self.token_counter.count(response_text)
            total += req_tokens + resp_tokens
            self._followup_calls += 1
            cursor = self._next_cursor_from_parsed(followup_parsed)
            truncated = self._truncated_from_parsed(followup_parsed)
            if not truncated and cursor in (None, "-", ""):
                break
        return total

    def _extract_facts(
        self,
        wanted: list[str],
        response_text: str,
        parsed: Any,
        call_args: dict[str, Any],
    ) -> dict[str, Any]:
        facts: dict[str, Any] = {}
        compact_info = self._parse_compact_text(response_text)

        if "truncated" in wanted:
            facts["truncated"] = bool(
                compact_info.get("truncated", False)
                or self._truncated_from_parsed(parsed)
            )
        if "next_cursor" in wanted:
            facts["next_cursor"] = compact_info.get(
                "next"
            ) or self._next_cursor_from_parsed(parsed)

        if "bench_cube_exists" in wanted or "bench_cube_ids" in wanted:
            ids = self._extract_ids(parsed, compact_info)
            if "bench_cube_ids" in wanted:
                facts["bench_cube_ids"] = ids
            if "bench_cube_exists" in wanted:
                facts["bench_cube_exists"] = len(ids) > 0
            if ids:
                facts["first_bench_cube_id"] = ids[0]

        if "has_rigidbody" in wanted or "rigidbody_mass" in wanted:
            has_rigidbody, mass = self._extract_rigidbody(parsed)
            if "has_rigidbody" in wanted:
                facts["has_rigidbody"] = has_rigidbody
            if "rigidbody_mass" in wanted:
                facts["rigidbody_mass"] = mass

        if "hierarchy_rows" in wanted or "root_ids" in wanted or "root_count" in wanted:
            rows = self._extract_hierarchy_rows(parsed, compact_info)
            if "hierarchy_rows" in wanted:
                facts["hierarchy_rows"] = rows
            root_ids = [
                str(r.get("id"))
                for r in rows
                if str(r.get("parent", "-")) in ("-", "", "None", "null")
            ]
            if "root_ids" in wanted:
                facts["root_ids"] = root_ids
            if "root_count" in wanted:
                facts["root_count"] = len(root_ids)

        if "descendant_counts" in wanted:
            parent_id = str(call_args.get("parent_id", ""))
            child_ids = self._extract_ids(parsed, compact_info)
            current = dict(self.facts.get("descendant_counts", {}))
            current[parent_id] = len(child_ids)
            facts["descendant_counts"] = current

        if "verify_root_count" in wanted or "verify_descendant_total" in wanted:
            rows = self._extract_hierarchy_rows(parsed, compact_info)
            verify_root_count = len(
                [
                    r
                    for r in rows
                    if str(r.get("parent", "-")) in ("-", "", "None", "null")
                ]
            )
            if "verify_root_count" in wanted:
                facts["verify_root_count"] = verify_root_count
            if "verify_descendant_total" in wanted:
                facts["verify_descendant_total"] = max(0, len(rows) - verify_root_count)
            if "counts_match" in wanted:
                prior = int(self.facts.get("root_count", -1))
                facts["counts_match"] = prior == verify_root_count

        if "bench_glow_found" in wanted or "bench_glow_path" in wanted:
            asset_paths = self._extract_asset_paths(parsed, compact_info)
            found = any("Bench_Glow" in p for p in asset_paths)
            if "bench_glow_found" in wanted:
                facts["bench_glow_found"] = found
            if "bench_glow_path" in wanted:
                if found:
                    facts["bench_glow_path"] = next(
                        p for p in asset_paths if "Bench_Glow" in p
                    )
                else:
                    facts["bench_glow_path"] = "Assets/Bench/Bench_Glow.mat"

        if (
            "target_ids" in wanted
            or "target_names" in wanted
            or "target_count" in wanted
        ):
            ids = self._extract_ids(parsed, compact_info)
            names = self._extract_names(parsed, compact_info)
            if "target_ids" in wanted:
                facts["target_ids"] = ids
            if "target_names" in wanted:
                facts["target_names"] = names
            if "target_count" in wanted:
                facts["target_count"] = len(ids)

        if "material_assignments" in wanted:
            assignments = dict(self.facts.get("material_assignments", {}))
            target = str(call_args.get("target", ""))
            assignments[target] = str(call_args.get("value", ""))
            facts["material_assignments"] = assignments

        if "material_verified_count" in wanted or "material_mismatch_ids" in wanted:
            target = str(call_args.get("uri_template", ""))
            components_text = (
                json.dumps(parsed, ensure_ascii=False)
                if isinstance(parsed, dict)
                else response_text
            )
            ok = "Bench_Glow" in components_text
            mismatch = list(self.facts.get("material_mismatch_ids", []))
            verified = int(self.facts.get("material_verified_count", 0))
            if ok:
                verified += 1
            else:
                mismatch.append(target)
            if "material_verified_count" in wanted:
                facts["material_verified_count"] = verified
            if "material_mismatch_ids" in wanted:
                facts["material_mismatch_ids"] = mismatch

        for key in wanted:
            if key not in facts and key in self.facts:
                facts[key] = self.facts[key]
        return facts

    def _parse_compact_text(self, text: str) -> dict[str, Any]:
        rows: list[dict[str, str]] = []
        summary: dict[str, Any] = {}
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("row "):
                row: dict[str, str] = {}
                for part in s[4:].split():
                    if "=" in part:
                        k, v = part.split("=", 1)
                        row[k] = v
                rows.append(row)
            elif s.startswith("ok "):
                for part in s[3:].split():
                    if "=" in part:
                        k, v = part.split("=", 1)
                        summary[k] = v
        summary["rows"] = rows
        return summary

    def _extract_ids(self, parsed: Any, compact_info: dict[str, Any]) -> list[str]:
        ids: list[str] = []
        for row in compact_info.get("rows", []):
            rid = row.get("id")
            if rid:
                ids.append(str(rid))
        if ids:
            return ids

        if isinstance(parsed, dict):
            data = (
                parsed.get("data") if isinstance(parsed.get("data"), dict) else parsed
            )
            for key in (
                "results",
                "items",
                "gameObjects",
                "objects",
                "hierarchy",
                "nodes",
            ):
                values = data.get(key)
                if isinstance(values, list):
                    for item in values:
                        if isinstance(item, dict):
                            item_id = item.get("instanceID") or item.get("id")
                            if item_id is not None:
                                ids.append(str(item_id))
                    if ids:
                        return ids
            direct = data.get("instanceID") or data.get("id")
            if direct is not None:
                ids.append(str(direct))
        return ids

    def _extract_names(self, parsed: Any, compact_info: dict[str, Any]) -> list[str]:
        names: list[str] = []
        for row in compact_info.get("rows", []):
            val = row.get("name")
            if val:
                names.append(str(val))
        if names:
            return names
        if isinstance(parsed, dict):
            data = (
                parsed.get("data") if isinstance(parsed.get("data"), dict) else parsed
            )
            for key in (
                "results",
                "items",
                "gameObjects",
                "objects",
                "hierarchy",
                "nodes",
            ):
                values = data.get(key)
                if isinstance(values, list):
                    for item in values:
                        if isinstance(item, dict) and item.get("name") is not None:
                            names.append(str(item.get("name")))
        return names

    def _extract_hierarchy_rows(
        self, parsed: Any, compact_info: dict[str, Any]
    ) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        compact_rows = compact_info.get("rows", [])
        for row in compact_rows:
            rows.append(
                {
                    "id": str(row.get("id", "")),
                    "name": str(row.get("name", "")),
                    "parent": str(row.get("parent", "-")),
                }
            )
        if rows:
            return rows

        if isinstance(parsed, dict):
            data = (
                parsed.get("data") if isinstance(parsed.get("data"), dict) else parsed
            )
            values = (
                data.get("hierarchy") or data.get("nodes") or data.get("items") or []
            )
            if isinstance(values, list):
                for node in values:
                    if isinstance(node, dict):
                        rows.append(
                            {
                                "id": str(
                                    node.get("instanceID") or node.get("id") or ""
                                ),
                                "name": str(node.get("name") or ""),
                                "parent": str(
                                    node.get("parentInstanceID")
                                    or node.get("parent")
                                    or "-"
                                ),
                            }
                        )
        return rows

    def _extract_asset_paths(
        self, parsed: Any, compact_info: dict[str, Any]
    ) -> list[str]:
        paths: list[str] = []
        for row in compact_info.get("rows", []):
            p = row.get("path")
            if p:
                paths.append(str(p))
        if paths:
            return paths
        if isinstance(parsed, dict):
            data = (
                parsed.get("data") if isinstance(parsed.get("data"), dict) else parsed
            )
            results = (
                data.get("results") or data.get("assets") or data.get("items") or []
            )
            if isinstance(results, list):
                for item in results:
                    if isinstance(item, dict):
                        p = item.get("path") or item.get("assetPath")
                        if p:
                            paths.append(str(p))
        return paths

    def _extract_rigidbody(self, parsed: Any) -> tuple[bool, float | None]:
        if not isinstance(parsed, dict):
            return False, None
        text = json.dumps(parsed, ensure_ascii=False)
        if "Rigidbody" not in text:
            return False, None
        mass = None
        data = parsed.get("data") if isinstance(parsed.get("data"), dict) else parsed
        components = data.get("components") or data.get("items") or []
        if isinstance(components, list):
            for comp in components:
                if not isinstance(comp, dict):
                    continue
                ctype = str(comp.get("type") or comp.get("name") or "")
                if "Rigidbody" in ctype:
                    props = (
                        comp.get("properties")
                        if isinstance(comp.get("properties"), dict)
                        else comp
                    )
                    raw_mass = props.get("mass") if isinstance(props, dict) else None
                    if isinstance(raw_mass, (int, float)):
                        mass = float(raw_mass)
                    break
        return True, mass

    def _resource_text(self, result: dict[str, Any]) -> str:
        contents = result.get("contents")
        if not isinstance(contents, list):
            return json.dumps(result, ensure_ascii=False)
        texts: list[str] = []
        for item in contents:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                texts.append(item["text"])
        joined = "\n".join(texts).strip()
        if joined:
            return joined
        return json.dumps(result, ensure_ascii=False)

    def _next_cursor_from_parsed(self, parsed: Any) -> Any:
        if isinstance(parsed, dict):
            data = (
                parsed.get("data") if isinstance(parsed.get("data"), dict) else parsed
            )
            if not isinstance(data, dict):
                return None
            for key in ("next_cursor", "next", "cursor", "page_number"):
                if key in data:
                    return data.get(key)
        return None

    def _truncated_from_parsed(self, parsed: Any) -> bool:
        if isinstance(parsed, dict):
            data = (
                parsed.get("data") if isinstance(parsed.get("data"), dict) else parsed
            )
            value = data.get("truncated")
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.strip() in ("1", "true", "True")
            if isinstance(value, (int, float)):
                return int(value) == 1
        return False

    def _merge_facts(
        self, base: dict[str, Any], update: dict[str, Any]
    ) -> dict[str, Any]:
        merged = dict(base)
        for key, value in update.items():
            if (
                key in merged
                and isinstance(merged[key], list)
                and isinstance(value, list)
            ):
                merged[key] = merged[key] + value
            elif (
                key in merged
                and isinstance(merged[key], dict)
                and isinstance(value, dict)
            ):
                temp = dict(merged[key])
                temp.update(value)
                merged[key] = temp
            else:
                merged[key] = value
        return merged

    def _system_prompt(self, task: TaskDef) -> str:
        return (
            "You are a deterministic Unity task policy agent. "
            f"Execute task={task.id} name={task.name}. "
            "Never improvise tools outside policy steps. "
            "Collect only required facts and verify completion."
        )

    def _tool_schema_tokens(self) -> int:
        try:
            from mcp_real_scenario import _post_sse_json

            msg = {
                "jsonrpc": "2.0",
                "id": self.session.seq,
                "method": "tools/list",
                "params": {},
            }
            self.session.seq += 1
            event, raw, _ = _post_sse_json(
                self.session.url,
                msg,
                self.session.session_id,
                self.session.timeout_sec,
            )
            if not event or "result" not in event:
                return self.token_counter.count(raw)
            return self.token_counter.count(
                json.dumps(event["result"], ensure_ascii=False, sort_keys=True)
            )
        except Exception:
            estimated = "29 tools with average 200 tokens each"
            return self.token_counter.count(estimated)
