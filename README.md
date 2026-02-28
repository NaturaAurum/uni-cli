# uni-cli

Token-efficient CLI and Unity Editor tools for LLM agents. Extends [unity-mcp](https://github.com/CoplayDev/unity-mcp) with additional subsystem support and a compact CLI interface that reduces token overhead by ~31x.

## What This Does

| Component | Description |
|-----------|-------------|
| **UPM Package** (`package/`) | New Unity tools — UI Toolkit, Addressables, DOTS, Shader Graph — auto-registered as MCP tools |
| **CLI Tool** (`cli/`) | Compact command interface for LLM agents. Translates to MCP calls with minimal token overhead |

### How It Works

```
# Without uni-cli (MCP only):
LLM → MCP server (14,877 token schema) → Unity
       verbose JSON responses

# With uni-cli package installed:
LLM → MCP server (14,877 + new tools) → Unity + uni-cli tools
       MCP clients (Cursor, Claude) see additional tools automatically

# With uni-cli CLI:
LLM → uni-cli (480 token schema) → MCP server → Unity
       compact responses (79-98% smaller)
```

## Install

### 1. UPM Package (Unity Editor tools)

Requires [unity-mcp](https://github.com/CoplayDev/unity-mcp) installed first.

Add to your `Packages/manifest.json`:

```json
{
  "dependencies": {
    "com.coplaydev.unity-mcp": "https://github.com/CoplayDev/unity-mcp.git?path=/MCPForUnity#main",
    "com.uni-cli.tools": "https://github.com/ArtisanCodesmith/uni-cli.git?path=/package"
  }
}
```

New tools appear automatically in MCP-compatible clients (Cursor, Claude Code, VS Code, etc.).

### 2. CLI Tool (optional, for token efficiency)

```bash
pip install uni-cli
```

```bash
# Example: list scene hierarchy in compact format
uni-cli hierarchy ls --instance MyProject --fields id,name,parent --limit 50
```

## Token Efficiency

Measured against live Unity (2022.3, unity-mcp v2.14.1):

| Metric | Value |
|--------|-------|
| Per-response output reduction | **79–98%** (median 92.8%) |
| Tool schema overhead | **MCP 14,877 vs CLI 480 tokens** (31x) |
| Projected E2E savings | **60–90%** (schema + response) |

Full benchmark report: [`bench/reports/final-benchmark-report.md`](bench/reports/final-benchmark-report.md)

## New Tools (via UPM Package)

| Tool | Status | Subsystem |
|------|--------|-----------|
| `manage_ui_toolkit` | Planned | UI Toolkit (UXML, USS, VisualElement) |
| `manage_addressables` | Planned | Addressable Asset System |
| `manage_dots` | Planned | DOTS / ECS |
| `manage_shader_graph` | Planned | Shader Graph |

These tools use the same `[McpForUnityTool]` attribute as unity-mcp, so they're auto-discovered by the MCP server when installed.

## Repository Structure

```
uni-cli/
├── package/              ← UPM package (install via Unity Package Manager)
│   ├── Editor/Tools/     ← New subsystem tool implementations
│   └── package.json
├── cli/                  ← CLI tool (install via pip)
│   ├── src/uni_cli/
│   └── pyproject.toml
├── unity-project/        ← Development Unity project
├── bench/                ← Benchmarks and validation data
│   ├── scripts/
│   ├── data/
│   └── reports/
├── docs/
└── LICENSE               ← MIT
```

## Development

```bash
# Open Unity project (has local package reference)
# unity-project/Packages/manifest.json references "file:../../package"

# Run benchmarks
python3 bench/scripts/run_real_benchmark.py \
  --url http://127.0.0.1:8080/mcp \
  --unity-instance uni-cli \
  --iterations 10 --warmup 2 --repetitions 2 \
  --scene-profile all \
  --out bench/reports/tier1-corrected.json
```

## License

MIT
