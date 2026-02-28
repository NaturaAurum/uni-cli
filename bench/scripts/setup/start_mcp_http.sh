#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/setup/start_mcp_http.sh [--url http://127.0.0.1:8080] [--from mcpforunityserver==9.4.7]

Starts MCP for Unity HTTP server via uvx.
Keep this shell running while using the MCP client.
EOF
}

url="http://127.0.0.1:8080"
from_pkg="mcpforunityserver==9.4.7"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --url)
      url="${2:-}"
      shift 2
      ;;
    --from)
      from_pkg="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

exec uvx --from "$from_pkg" mcp-for-unity --transport http --http-url "$url" --project-scoped-tools

