# uni-cli Token Efficiency Benchmark — Final Report

**Date**: 2026-02-28
**MCP Server**: mcp-for-unity-server v2.14.1 (31 tools, 14 resources)
**Unity**: 2022.3.62f2 (instance: uni-cli@eed8461035005b2a)
**Token Counter**: tiktoken o200k_base

---

## Executive Summary

| Metric | Value | Confidence |
|--------|-------|------------|
| **Per-response output reduction** | **79–98%** (median 92.8%) | High — measured across 3 scene sizes |
| **E2E task total token reduction** | **0–5.5%** (avg 2.4%) | High — 3 tasks × 2 reps |
| **Tool schema overhead (MCP vs CLI)** | **31x** (14,877 vs 480 tokens) | High — live MCP schema extraction |

**Key Finding**: The CLI wrapper achieves massive per-response compression (79–98%), but this advantage is almost entirely negated by the MCP tool schema overhead that dominates short-to-medium conversations. The real win is in the **schema overhead reduction** (31x), which compounds across conversations.

---

## Tier 1 — Per-Response Payload Reduction

Measures output token reduction for identical operations: raw MCP JSON vs compact CLI format.

### Methodology
- **Scenes**: SmallBench (5 obj), MediumBench (50 obj), LargeBench (200 obj)
- **Scenarios**: 5 (hierarchy_query, object_create, reparent, asset_search, batch_ops)
- **Iterations**: 5 per scenario per mode (after 1 warmup)
- **Primary metric**: Output-only reduction (response payload comparison)
- **Compact format**: Includes row-level data (id, name, parent, path) — not just summary

### Results

| Scenario | Small | Medium | Large | Notes |
|----------|-------|--------|-------|-------|
| hierarchy_query | 83.6% | 87.7% | 88.6% | Scales with scene size — larger scenes = more savings |
| object_create | 92.8% | 92.8% | 92.8% | Scene-independent |
| reparent | 97.4% | 97.4% | 97.4% | Scene-independent |
| asset_search | 79.3% | 79.3% | 79.3% | Lowest — row data included (paths, names) |
| batch_ops | 98.4% | 98.4% | 98.4% | Highest — summary-only output |

**Median output reduction: 92.8%** (range 79.3%–98.4%)

### vs Previous (Uncorrected) Claim

| | Previous | Corrected |
|---|---|---|
| Headline | ~98.3% | 92.8% median |
| asset_search | 99.7% | 79.3% |
| Data integrity | Summary only (agent can't use results) | Row data preserved |
| Methodology | Single scene, weighted average | 3 scenes, per-scenario reporting |

### Degenerate CI Note
All iterations within each scenario produced identical token counts (deterministic MCP responses), so bootstrap confidence intervals are not meaningful for within-scenario analysis. Cross-scene variance provides the actual spread (e.g., hierarchy_query: 83.6%–88.6%).

---

## Tier 2 — End-to-End Agent Task Token Budget

Measures total tokens consumed to complete a multi-step Unity task, including:
- System prompt tokens
- Tool schema tokens (MCP tool definitions loaded into context)
- Request tokens (what the agent sends)
- Response tokens (what MCP returns)
- Followup call tokens (wrapper pagination if compact output is truncated)

### Tasks

| Task | Category | Steps | Description |
|------|----------|-------|-------------|
| create_tagged_cube | write-heavy | 4 setup + 2 verify + 1 cleanup | Create cube, add Rigidbody, set tag |
| hierarchy_audit | read-heavy | 2 setup + 1 verify | Read hierarchy, count roots, verify |
| material_swap | mixed | 4 setup + 1 verify | Find/create material, assign to targets |

### Results

| Task | Baseline Tokens | Wrapper Tokens | Reduction | Rounds |
|------|----------------|----------------|-----------|--------|
| create_tagged_cube | 14,236 | 13,987 | 1.75% | 2 / 2 |
| hierarchy_audit | 14,932 | 14,118 | 5.45% | 1 / 1 |
| material_swap | 13,886 | 13,886 | 0.00% | 0 / 0 |

**Macro average reduction: 2.4%**

### Why E2E Reduction Is So Low

Token budget breakdown (hierarchy_audit example):

| Component | Estimated Tokens | % of Total |
|-----------|-----------------|------------|
| Tool schema (MCP defs) | ~13,000 | ~87% |
| System prompt | ~50 | <1% |
| Request tokens | ~200 | ~1% |
| Response tokens | ~700–1,700 | ~5–12% |

The tool schema dominates — **87% of every conversation is spent loading MCP tool definitions** before a single operation runs. The wrapper reduces the response payload (5–12% of total) but cannot eliminate the schema overhead because the policy engine still makes MCP calls underneath.

> **Implication**: If the CLI wrapper replaced MCP entirely (schema overhead drops from 14,877 to 480 tokens), E2E savings would be dramatically different. See Tier 3.

---

## Tier 3 — Tool Schema Overhead Analysis

Measures the fixed per-conversation cost of tool/command definitions.

### Results (Live MCP)

| | Tokens | Items |
|---|---|---|
| MCP tool schemas | 13,783 | 31 tools |
| MCP resource schemas | 1,094 | 14 resources |
| **MCP total** | **14,877** | |
| **CLI help text** | **480** | 25 commands |

**Overhead ratio: 31.0x** (MCP / CLI)

### Amortized Cost Per Operation

| Conversation Length | MCP per-op | CLI per-op | Delta per-op |
|--------------------|-----------|-----------|-------------|
| 1 operation | 14,877 | 480 | +14,397 |
| 5 operations | 2,975 | 96 | +2,879 |
| 10 operations | 1,488 | 48 | +1,440 |
| 25 operations | 595 | 19 | +576 |
| 50 operations | 298 | 10 | +288 |

Even at 50 operations, MCP carries ~30x more overhead per operation.

---

## Synthesis — Where Each Tier Matters

### For Short Conversations (1–5 tool calls)
- **Schema overhead dominates**: MCP loads 14,877 tokens upfront
- **Tier 1 savings irrelevant**: Response reduction doesn't offset schema cost
- **CLI wrapper wins massively** if it replaces MCP schema entirely

### For Medium Conversations (10–25 tool calls)
- **Schema overhead amortizes but remains significant**: ~600–1,500 extra tokens/op
- **Tier 1 savings start to matter**: 80–98% response reduction compounds across calls
- **Net effect**: CLI clearly better, magnitude depends on response sizes

### For Long Conversations (50+ tool calls)
- **Schema overhead amortized to ~300 tokens/op**
- **Tier 1 savings compound significantly**: Large hierarchy queries save thousands of tokens
- **Net effect**: CLI substantially better

### True Token Budget Comparison (Projected)

For a 10-operation session reading a large hierarchy:

| Component | MCP | CLI (projected) |
|-----------|-----|-----------------|
| Schema overhead | 14,877 | 480 |
| 10× hierarchy_query requests | ~1,700 | ~1,050 |
| 10× hierarchy_query responses | ~13,470 | ~1,540 |
| **Total** | **~30,047** | **~3,070** |
| **Projected E2E reduction** | | **~89.8%** |

---

## Conclusions

1. **Per-response compression is real and significant** (median 92.8%, corrected from inflated 98.3%)
2. **MCP tool schema is the dominant cost** in any LLM conversation (14,877 tokens fixed overhead)
3. **The real win is replacing MCP's schema**, not just compressing its responses
4. **Current E2E measurements (2.4% avg) understate the benefit** because the benchmark still loads MCP schemas — it measures "compact responses via MCP" not "CLI replacing MCP"
5. **Credible projected E2E savings: 60–90%** when CLI fully replaces MCP (schema + response savings)

### Recommendation

The data strongly supports building a **standalone CLI** that eliminates MCP protocol entirely for LLM-agent use cases:
- Replace 14,877-token tool schemas with 480-token CLI help
- Replace verbose JSON responses with compact row-based format
- Net projected savings: 60–90% depending on conversation length

---

## Artifacts

| File | Description |
|------|-------------|
| `reports/tier1-corrected.json` | Tier 1 raw data (3 scenes × 5 scenarios) |
| `reports/tier2-e2e.json` | Tier 2 raw data (3 tasks × 2 modes × 2 reps) |
| `reports/tier3-schema-overhead.json` | Tier 3 schema analysis |
| `scripts/run_real_benchmark.py` | Tier 1 runner |
| `scripts/run_e2e_benchmark.py` | Tier 2 runner |
| `scripts/analyze_schema_overhead.py` | Tier 3 analyzer |
