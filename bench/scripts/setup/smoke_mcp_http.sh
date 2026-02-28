#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/setup/smoke_mcp_http.sh [--url http://127.0.0.1:8080/mcp]

Runs a minimal MCP handshake against Unity MCP HTTP endpoint:
  1) initialize
  2) resources/read mcpforunity://instances
EOF
}

url="http://127.0.0.1:8080/mcp"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --url)
      url="${2:-}"
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

tmp_dir="$(mktemp -d)"
hdr_file="$tmp_dir/headers.txt"
trap 'rm -rf "$tmp_dir"' EXIT

curl -sS -D "$hdr_file" -o /dev/null -m 8 -N \
  -H 'Accept: application/json, text/event-stream' \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"uni-cli-smoke","version":"0.1"}}}' \
  "$url"

session_id="$(awk 'BEGIN{IGNORECASE=1} /^mcp-session-id:/{print $2}' "$hdr_file" | tr -d '\r')"
if [ -z "$session_id" ]; then
  echo "Failed to obtain mcp-session-id from initialize response." >&2
  exit 1
fi

echo "session_id=$session_id"

curl -sS -m 8 -N \
  -H 'Accept: application/json, text/event-stream' \
  -H 'Content-Type: application/json' \
  -H "mcp-session-id: $session_id" \
  -d '{"jsonrpc":"2.0","id":2,"method":"resources/read","params":{"uri":"mcpforunity://instances"}}' \
  "$url"

