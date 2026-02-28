# CLI — TOKEN-EFFICIENT MCP WRAPPER

Python CLI wrapping MCP Streamable HTTP. Zero deps (stdlib only). 79–98% output token reduction.

## STRUCTURE & DEPS

```
pyproject.toml                    # entry: uni-cli → uni_cli.main:main
src/uni_cli/
  main.py                         # argparse + dispatch + format (203L)
  transport/mcp_client.py          # JSON-RPC 2.0 / HTTP / SSE / session (262L)
  formatter/compact.py             # row-based compact output (210L)
  commands/                        # each independent, returns dict
    hierarchy.py  object.py  asset.py  batch.py  subsystem.py

Deps: main → transport + formatter + commands/*
      commands/* → transport (call_tool)
      transport ≠ formatter (independent)
```

## WHERE TO LOOK

| Task | File | Notes |
|------|------|-------|
| New command | `commands/` | `run_<action>(client, instance_id, **kwargs) → dict` |
| Register command | `main.py` | `_build_parser()` + `_dispatch()` |
| Output format | `formatter/compact.py` | `row field1=val1 field2=val2` |
| MCP connection | `transport/mcp_client.py` | HTTP POST + SSE, `mcp-session-id` |

## CONVENTIONS

- `from __future__ import annotations` every file
- Commands return `dict` — formatter handles display
- `parse_result_json(result)` for MCP response parsing
- Instance resolution: exact ID → prefix → name → first available
- `McpError` for RPC failures (JSON-RPC error codes)

## ANTI-PATTERNS

- **NEVER** add external deps — no requests, httpx, click
- **NEVER** import between commands — each independent
- **NEVER** format in commands — return raw dict, let formatter handle

## OUTPUT CONTRACT

```
row id=12345 name="Main Camera" active=1 parent=-1      # collection item
ok op=hierarchy.ls count=2 next="" truncated=0            # collection end
ok op=object.create id=12347 name="Cube"                  # single item
err op=object.delete message="Object not found"            # error
```

Full spec: `docs/cli-output-contract.md`
