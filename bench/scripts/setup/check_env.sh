#!/usr/bin/env bash
set -euo pipefail

echo "== uni-cli / Unity MCP environment check =="
echo "cwd: $(pwd)"
echo

warn_count=0
err_count=0

pass() {
  echo "[PASS] $1"
}

warn() {
  echo "[WARN] $1"
  warn_count=$((warn_count + 1))
}

fail() {
  echo "[FAIL] $1"
  err_count=$((err_count + 1))
}

if command -v uv >/dev/null 2>&1; then
  pass "uv installed: $(uv --version)"
else
  fail "uv is not installed. Install from https://docs.astral.sh/uv/getting-started/installation/"
fi

if command -v python3 >/dev/null 2>&1; then
  py_ver="$(python3 --version | awk '{print $2}')"
  py_major="$(echo "$py_ver" | cut -d. -f1)"
  py_minor="$(echo "$py_ver" | cut -d. -f2)"
  pass "python3 detected: $py_ver"
  if [ "$py_major" -lt 3 ] || { [ "$py_major" -eq 3 ] && [ "$py_minor" -lt 10 ]; }; then
    warn "python3 is below 3.10 (current: $py_ver). unity-mcp recommends Python 3.10+."
  else
    pass "python3 satisfies unity-mcp requirement (>=3.10)."
  fi
else
  fail "python3 is not installed."
fi

editor_root="/Applications/Unity/Hub/Editor"
if [ -d "$editor_root" ]; then
  editors_raw="$(ls -1 "$editor_root" 2>/dev/null || true)"
  if [ -n "$editors_raw" ]; then
    pass "Unity editors found under $editor_root:"
    while IFS= read -r v; do
      echo "  - $v"
    done <<< "$editors_raw"
  else
    fail "No Unity editor versions found in $editor_root."
  fi
else
  fail "Unity Hub editor directory not found: $editor_root"
fi

if lsof -nP -iTCP:8080 -sTCP:LISTEN >/dev/null 2>&1; then
  warn "Port 8080 is currently in use (could be existing unity-mcp server)."
  lsof -nP -iTCP:8080 -sTCP:LISTEN | sed 's/^/  /'
else
  pass "Port 8080 is free."
fi

echo
if [ "$err_count" -gt 0 ]; then
  echo "Result: FAIL ($err_count errors, $warn_count warnings)"
  exit 1
fi
echo "Result: PASS ($warn_count warnings)"
