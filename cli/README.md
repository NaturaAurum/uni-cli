# uni-cli

Token-efficient CLI for LLM agents to control Unity Editor via [MCP](https://modelcontextprotocol.io). Reduces token overhead by ~31x compared to raw MCP tool schemas.

Part of the [uni-cli](https://github.com/NaturaAurum/uni-cli) project — extends [unity-mcp](https://github.com/CoplayDev/unity-mcp) with additional Unity subsystem tools.

## Why

LLM agents talking to Unity through MCP pay a heavy token tax — large tool schemas and verbose JSON responses eat context window budget. uni-cli solves this with a compact CLI layer:

| Metric | Value |
|--------|-------|
| Per-response output reduction | **79–98%** (median 92.8%) |
| Tool schema overhead | **MCP 14,877 → CLI 480 tokens** (31x reduction) |

## Install

```bash
pip install unity-mcp-cli
```

**Prerequisites:**
- Python 3.10+
- [unity-mcp](https://github.com/CoplayDev/unity-mcp) running in your Unity project

## Usage

```bash
# List scene hierarchy (compact output)
uni-cli hierarchy ls --instance MyProject --fields id,name,parent --limit 50

# Create a GameObject
uni-cli object create --instance MyProject --name "Player" --preset Cube --pos 0,1,0

# Search assets
uni-cli asset search --instance MyProject --query "*.prefab" --limit 20

# Get full JSON output
uni-cli hierarchy ls --format json --limit 10

# List available MCP tools
uni-cli tools
```

### Output Format

Compact row-based format designed for minimal token usage:

```
row id=12345 name="Main Camera" active=1 parent=-1
row id=12346 name="Directional Light" active=1 parent=-1
ok op=hierarchy.ls count=2 next="" truncated=0
```

### Commands

| Command | Description |
|---------|-------------|
| `hierarchy ls` | List scene hierarchy |
| `object create/get/modify/delete` | GameObject operations |
| `asset search/info/create/delete` | Asset operations |
| `batch apply` | Execute batch commands from file |
| `ui-toolkit <action>` | UI Toolkit (UXML, USS, VisualElement) |
| `addressables <action>` | Addressable Asset System |
| `dots <action>` | DOTS / ECS |
| `shader-graph <action>` | Shader Graph |
| `tools` | List available MCP tools |

### Global Options

| Option | Default | Description |
|--------|---------|-------------|
| `--url` | `http://127.0.0.1:8080/mcp` | MCP server URL |
| `--instance` | auto-detect | Unity instance selector |
| `--format` | `compact` | Output format (`compact` or `json`) |
| `--timeout` | `30` | Request timeout in seconds |

## Zero Dependencies

uni-cli uses only Python standard library — no external packages required.

## License

[MIT](https://github.com/NaturaAurum/uni-cli/blob/main/LICENSE)
