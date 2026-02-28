# Tier 2 End-to-End Agent Task Benchmark Design

## 1. Overview
- **Purpose**: Measure the total token consumption and efficiency of an LLM agent completing complex, multi-step Unity tasks.
- **Comparison Modes**: Compares raw MCP (direct tool calls) vs CLI wrapper mode (structured, compressed CLI outputs).
- **Positioning**: Complements Tier 1 benchmarks (per-response payload compression) by providing high-level task-completion metrics.

## 2. Task Suite (8 tasks)

### Task 1: Create Tagged Cube
- **Category**: Write-heavy
- **Description**: Create a Cube at origin, name it `Bench_Cube`, add Rigidbody, set mass=2, tag it `BenchTag` (create tag if needed), ensure active.
- **Success Criteria**:
  - GameObject named `Bench_Cube` exists in active scene
  - Has Rigidbody with mass=2
  - Tag equals `BenchTag`
  - Transform position (0,0,0)
- **Baseline (raw MCP) sequence** (5-7 rounds):
  1. `manage_scene` (open/create BenchmarkScene)
  2. `manage_gameobject` (create primitive Cube, name, transform)
  3. `manage_components` (add Rigidbody, set mass)
  4. `manage_editor` (ensure tag exists) + `manage_gameobject` (set tag)
  5. `find_gameobjects` + `gameobject_components` (verify)
- **Wrapper (CLI) sequence** (6-9 rounds):
  - Same core calls
  - If `find_gameobjects` returns only count without ids, needs follow-up detail fetch
- **Key insight**: Compact output mostly neutral for write-heavy single-object tasks.

### Task 2: Batch Grid Spawner
- **Category**: Write-heavy
- **Description**: Create a parent object `Spawner_Parent` and spawn 25 spheres in a 5x5 grid (spacing=2.0) as its children.
- **Success Criteria**:
  - `Spawner_Parent` exists
  - 25 spheres exist as direct children
  - Positions follow 5x5 grid logic
- **Baseline (raw MCP) sequence** (6-10 rounds):
  1. `manage_gameobject` (create parent)
  2. `batch_execute` (array of 25 `manage_gameobject` calls for spheres)
  3. `find_gameobjects` (verify count)
- **Wrapper (CLI) sequence** (6-12 rounds):
  - Uses `uni batch` style abstraction if available in policy, or multiple CLI calls.
- **Key insight**: Tests how much `batch_execute` overhead is reduced or hidden by CLI wrapper.

### Task 3: Hierarchy Audit
- **Category**: Read-heavy
- **Description**: List all root objects, count total descendants for each, and identify any object with missing scripts (Null components).
- **Success Criteria**:
  - Accurate count of roots
  - Correct descendant totals
  - Accurate list of "Broken" objects
- **Baseline (raw MCP) sequence** (10-25 rounds):
  1. `find_gameobjects` (get roots)
  2. Recursive `find_gameobjects` or `gameobject_details` for hierarchy depth
  3. `gameobject_components` for every object to find "null"
- **Wrapper (CLI) sequence** (10-35 rounds):
  - **Explicitly tests**: "Compact hurts if you must re-fetch details". If CLI output is too summarized, agent must perform more rounds to get IDs.
- **Key insight**: Measuring the "Round Trip Tax" of compression.

### Task 4: Material Swap on Targets
- **Category**: Mixed
- **Description**: Find all objects with prefix `Bench_Target_`, ensure material `Bench_Glow` exists in `Assets/Bench/`, and assign it to their MeshRenderers.
- **Success Criteria**:
  - `Bench_Glow` exists as asset
  - All matching objects have `Bench_Glow` assigned
- **Baseline (raw MCP) sequence** (8-18 rounds):
  1. `find_gameobjects` (prefix search)
  2. `manage_asset` (check/create material)
  3. `manage_material` (set properties)
  4. `manage_components` (assign to renderers)
- **Wrapper (CLI) sequence** (9-22 rounds):
  - Similar flow, testing if "Find" results provide enough data to skip `gameobject_details`.

### Task 5: Prefab Roundtrip
- **Category**: Mixed
- **Description**: Create a hierarchy (Parent -> Child), save it as `Assets/Bench/Roundtrip.prefab`, delete from scene, then instantiate two copies at different positions.
- **Success Criteria**:
  - Prefab asset exists
  - Two instances exist in scene with correct prefab link
- **Baseline (raw MCP) sequence** (9-16 rounds):
  1. `manage_gameobject` (hierarchy setup)
  2. `manage_prefabs` (save as prefab)
  3. `manage_gameobject` (delete)
  4. `manage_prefabs` (instantiate x2)
- **Wrapper (CLI) sequence** (9-20 rounds):
  - Tests prefab path handling and ID stability in CLI output.

### Task 6: Basic UI Setup
- **Category**: Write-heavy
- **Description**: Create a UI Canvas, an EventSystem, and a Button named `Start_Button`. Set button anchors to Bottom-Right.
- **Success Criteria**:
  - Canvas + EventSystem exist
  - Button is child of Canvas
  - Button `RectTransform` anchors are (1,0,1,0)
- **Baseline (raw MCP) sequence** (7-14 rounds):
  1. `manage_ui` (create canvas)
  2. `manage_ui` (create event system)
  3. `manage_ui` (create button)
  4. `manage_components` (set RectTransform)
- **Wrapper (CLI) sequence** (8-18 rounds):
  - Tests UI-specific component management and nested property updates.

### Task 7: Large Asset Inventory Filter
- **Category**: Read-heavy
- **Description**: Scan `Assets/` for all Textures larger than 1024px. Report their names and current `TextureImporter` compression settings.
- **Success Criteria**:
  - Complete list of matching textures
  - Correct metadata (size, format) reported
- **Baseline (raw MCP) sequence** (10-50 rounds):
  1. `manage_asset` (list assets)
  2. `manage_asset` (get metadata for each)
- **Wrapper (CLI) sequence** (10-70 rounds):
  - **Key Performance Metric**: More calls but significantly fewer tokens per listing due to field filtering.

### Task 8: Console-Driven Fix Loop
- **Category**: Mixed
- **Description**: Trigger a build or test run, read `read_console` for errors in `Bench_Broken_*.cs`, fix the syntax errors using `manage_asset` (write), `refresh_unity`, and verify clean run.
- **Success Criteria**:
  - Zero errors in console
  - `run_tests` returns success
- **Baseline (raw MCP) sequence** (8-20 rounds):
  1. `run_tests`
  2. `read_console`
  3. `manage_asset` (read/write file)
  4. `refresh_unity`
- **Wrapper (CLI) sequence** (10-30 rounds):
  - **Explicitly tests**: "Compact can hide key breadcrumbs". Does the CLI log truncation prevent the agent from seeing the line number?


## 3. Agent Simulation Design

### Track A: Deterministic Policy Agent (Scripted FSM)
- **Concept**: A scripted "agent" that follows strict decision rules to remove LLM variance.
- **Information Requirements**: At each step, the policy checks for necessary state facts.
- **Decision Rules**:
  1. Perform success check (is task done?).
  2. If not, fetch missing facts (e.g., find object ID).
  3. If results are large, handle pagination.
  4. Execute required writes.
- **Goal**: Fully deterministic execution given identical Unity state, providing a stable floor for token comparison.

### Track B: Real LLM Agent (Validation)
- **Concept**: Use an actual LLM (e.g., GPT-4o, Claude 3.5 Sonnet) to validate policy assumptions.
- **Configuration**: Temperature = 0, constrained prompting.
- **Iteration**: N=10 runs per task to observe variance.
- **Goal**: Verify that the CLI wrapper actually aids reasoning and reduces cognitive load in non-scripted scenarios.

## 4. Token Accounting

- **Scope**: `total_tokens = system_prompt + tool_schemas + user_message + assistant_reasoning + tool_calls + tool_responses + follow_ups + completion_message`
- **Measurement**: 
  - Use official API usage totals (e.g., `usage` field in OpenAI/Anthropic responses) where available.
  - Fallback to `tiktoken` with `o200k_base` encoding for local estimation.
- **Reporting**: Report `total_tokens_observed` (raw string count) and `total_tokens_billed` (including cache hits/misses if applicable) separately.

## 5. Metrics

Per task, per mode:
- **Success Rate**: Percentage of runs that met success criteria.
- **Total Tokens**: Sum of all tokens consumed until completion.
- **Rounds**: Number of request-response cycles.
- **Tool Calls**: Total number of individual tool executions.
- **Unique Tools Used**: Count of distinct tools called.
- **Follow-up Calls**: Number of additional calls required for clarification or error handling.

**Derived Metrics**:
- `token_reduction_pct`: Percentage of tokens saved by wrapper mode.
- `round_increase`: Increase/decrease in cycles compared to baseline.
- `efficiency`: Number of task completions possible per 1 million tokens.

## 6. Reporting Format

- **Per-Task Table**: Compare raw MCP vs CLI wrapper with absolute and percentage deltas.
- **Suite Summary**: Provide macro-average (unweighted average across tasks) and micro-average (total tokens over total tasks).
- **"Where Wrapper Hurts" Callouts**: Identify scenarios where the wrapper introduces overhead or reduces flexibility.
- **Edge Case Documentation**: Note behavior during partial failures or ambiguous state.

## 7. Fixture Requirements

To ensure repeatability, the benchmark requires a stabilized environment:
- **BenchmarkScene**: A dedicated Unity scene with a known initial hierarchy.
- **Assets/Bench/**: A directory containing deterministic textures, materials, and prefabs for testing.
- **Bench_Target_* Objects**: Specific objects tagged or named for the material swap task.
- **Bench_Broken_* Objects**: Scripts or objects with intentional errors for the console fix task.

## 8. Implementation Plan

1. **Benchmark Spec**: Define the JSON/YAML format for task definitions and success criteria.
2. **Runner**: Develop a execution engine supporting `mode=raw` and `mode=wrapper`.
3. **Deterministic Policy Engine**: Implement the FSM-based agent simulation.
4. **Verifier Library**: Create scripts to check Unity state post-task (e.g., object existence, property values).
5. **Token Accounting**: Integrate token counting logic into the runner.
6. **Reporting**: Generate JSONL traces for every run and an aggregated Markdown table.
7. **Fixture Stabilization**: Automate the setup and reset of the Unity benchmark environment.