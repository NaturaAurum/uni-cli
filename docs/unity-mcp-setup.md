# Unity Project + MCP Setup (for uni-cli PoC)

Last verified: 2026-02-27

## 1) Prerequisites

- Unity Editor: 2021.3 LTS+ (local check found `2022.3.62f2`, `6000.3.9f1`)
- `uv` installed
- Python 3.10+ recommended by `unity-mcp`
  - Local system python observed: `3.9.6` (warning level)

Run local check:

```bash
bash scripts/setup/check_env.sh
```

## 2) Create or Choose Unity Project

Create project from Unity Hub, then open once so `Packages/manifest.json` exists.

Example path:

`~/Desktop/UnityProjects/UniCliPoC`

## 3) Install MCP for Unity Package

### Option A: Git dependency injection (recommended for reproducible setup)

```bash
bash scripts/setup/prepare_project.sh \
  --project-dir ~/Desktop/UnityProjects/UniCliPoC \
  --channel main
```

For beta:

```bash
bash scripts/setup/prepare_project.sh \
  --project-dir ~/Desktop/UnityProjects/UniCliPoC \
  --channel beta
```

### Option B: Unity UI

In Unity:

`Window > Package Manager > + > Add package from git URL...`

Use:

`https://github.com/CoplayDev/unity-mcp.git?path=/MCPForUnity#main`

## 4) Start MCP Server in Unity

In Unity:

1. `Window > MCP for Unity`
2. Click `Start Server`
3. Confirm server URL is up (default): `http://localhost:8080/mcp`

Quick local health check:

```bash
curl -i http://localhost:8080/mcp
```

Expected:

- HTTP response is reachable (status may vary by transport/client expectations)
- Port `8080` is listening

Alternative (CLI launch without clicking Start Server):

```bash
bash scripts/setup/start_mcp_http.sh
```

The process stays attached to the terminal by design.

## 5) Connect MCP Client

Manual config snippet (HTTP):

```json
{
  "mcpServers": {
    "unityMCP": {
      "url": "http://localhost:8080/mcp"
    }
  }
}
```

VS Code style:

```json
{
  "servers": {
    "unityMCP": {
      "type": "http",
      "url": "http://localhost:8080/mcp"
    }
  }
}
```

## 6) Smoke Test Prompts

- "List root hierarchy with id and name only."
- "Create cube named `BenchCube` under root."
- "Reparent `BenchCube` under camera rig."
- "Search textures with `t:Texture` and return only guid/path."

Automated transport smoke test:

```bash
bash scripts/setup/smoke_mcp_http.sh
```

Expected output includes `session_id=...` and at least one Unity instance in `mcpforunity://instances`.

## 7) Integrate with Benchmark

1. Copy template:

```bash
cp bench/scenarios.real.template.json bench/scenarios.real.json
```

2. Replace `REPLACE_WITH_REAL_*_COMMAND` in `bench/scenarios.real.json`
3. Execute:

```bash
python3 scripts/run_benchmark.py \
  --scenario-file bench/scenarios.real.json \
  --out reports/real-latest.json \
  --strict
```

## 8) Common Pitfalls

- Python 3.10+ mismatch:
  - `unity-mcp` recommends 3.10+; if install fails, install newer Python or use `uv` managed runtime.
- Package import stuck:
  - Reopen project and check Unity Console/package logs.
- Client cannot connect:
  - Verify Unity server is started and URL exactly matches `http://localhost:8080/mcp`.
