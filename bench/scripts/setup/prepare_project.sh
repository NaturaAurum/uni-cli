#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/setup/prepare_project.sh --project-dir <path> [--channel main|beta]

What it does:
  - Ensures Packages/manifest.json exists
  - Injects/updates com.coplaydev.unity-mcp dependency as git URL

Example:
  scripts/setup/prepare_project.sh --project-dir ~/Desktop/UnityProjects/UniCliPoC --channel main
EOF
}

project_dir=""
channel="main"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --project-dir)
      project_dir="${2:-}"
      shift 2
      ;;
    --channel)
      channel="${2:-}"
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

if [ -z "$project_dir" ]; then
  echo "--project-dir is required." >&2
  usage
  exit 2
fi

if [ "$channel" != "main" ] && [ "$channel" != "beta" ]; then
  echo "--channel must be one of: main, beta" >&2
  exit 2
fi

project_dir="${project_dir/#\~/$HOME}"
manifest_path="$project_dir/Packages/manifest.json"

if [ ! -f "$manifest_path" ]; then
  echo "manifest.json not found: $manifest_path" >&2
  echo "Create/open a Unity project first." >&2
  exit 1
fi

dependency_url="https://github.com/CoplayDev/unity-mcp.git?path=/MCPForUnity#$channel"

python3 - "$manifest_path" "$dependency_url" <<'PY'
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
dependency_url = sys.argv[2]
pkg_name = "com.coplaydev.unity-mcp"

data = json.loads(manifest_path.read_text(encoding="utf-8"))
deps = data.setdefault("dependencies", {})
before = deps.get(pkg_name)
deps[pkg_name] = dependency_url

manifest_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

if before == dependency_url:
    print(f"unchanged: {pkg_name} -> {dependency_url}")
elif before is None:
    print(f"added: {pkg_name} -> {dependency_url}")
else:
    print(f"updated: {pkg_name}: {before} -> {dependency_url}")
PY

echo "Done. Reopen Unity project and wait for package import to finish."

