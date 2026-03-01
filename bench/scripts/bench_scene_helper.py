#!/usr/bin/env python3
# pyright: reportImplicitRelativeImport=false
"""Helpers for switching deterministic benchmark scenes in Unity."""

from __future__ import annotations

import argparse
import subprocess
import sys
from typing import Any, Callable

from mcp_real_scenario import (
    McpSession,
    ensure_success_text,
    extract_text,
    parse_text_json,
    resolve_instance_id,
)

SceneRunner = Callable[[str, dict[str, str]], dict[str, Any]]


SCENE_PROFILE_CONFIG: dict[str, dict[str, str]] = {
    "small": {
        "scene_name": "SmallBench",
        "scene_path": "Assets/BenchScenes/SmallBench.unity",
    },
    "medium": {
        "scene_name": "MediumBench",
        "scene_path": "Assets/BenchScenes/MediumBench.unity",
    },
    "large": {
        "scene_name": "LargeBench",
        "scene_path": "Assets/BenchScenes/LargeBench.unity",
    },
}


def resolve_scene_profiles(scene_profile: str | None) -> list[str]:
    if scene_profile is None:
        return []
    if scene_profile == "all":
        return ["small", "medium", "large"]
    if scene_profile in SCENE_PROFILE_CONFIG:
        return [scene_profile]
    raise ValueError(f"unknown scene profile: {scene_profile}")


def switch_to_scene_profile(
    session: McpSession,
    resolved_instance: str,
    scene_profile: str,
) -> dict[str, str]:
    if scene_profile not in SCENE_PROFILE_CONFIG:
        raise ValueError(f"unknown scene profile: {scene_profile}")

    cfg = SCENE_PROFILE_CONFIG[scene_profile]
    scene_name = cfg["scene_name"]
    scene_path = cfg["scene_path"]

    # Save current scene before switching to avoid unsaved-changes error
    try:
        session.call_tool(
            "manage_scene",
            {"action": "save", "unity_instance": resolved_instance},
        )
    except Exception:
        pass  # If save fails (e.g., untitled scene), proceed anyway

    load_res = session.call_tool(
        "manage_scene",
        {
            "action": "load",
            "name": scene_name,
            "path": "BenchScenes",
            "unity_instance": resolved_instance,
        },
    )
    load_text = extract_text(load_res)
    ensure_success_text(load_text, f"scene_load_{scene_profile}")

    active_res = session.call_tool(
        "manage_scene",
        {
            "action": "get_active",
            "unity_instance": resolved_instance,
        },
    )
    active_text = extract_text(active_res)
    ensure_success_text(active_text, f"scene_verify_{scene_profile}")
    payload = parse_text_json(active_text)
    if isinstance(payload, dict):
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        active_path = str(data.get("path", "")) if isinstance(data, dict) else ""
        if active_path and not active_path.endswith(scene_path):
            raise RuntimeError(
                f"scene_switch_mismatch:{scene_profile}:expected={scene_path}:actual={active_path}"
            )

    return {
        "profile": scene_profile,
        "scene_name": scene_name,
        "scene_path": scene_path,
    }


def run_with_scene_profiles(
    session: McpSession,
    resolved_instance: str,
    scene_profiles: list[str],
    runner: SceneRunner,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for profile in scene_profiles:
        scene_meta = switch_to_scene_profile(session, resolved_instance, profile)
        result = runner(profile, scene_meta)
        results.append(result)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8080/mcp")
    parser.add_argument("--unity-instance", default="uni-cli")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--scene-profile",
        choices=["small", "medium", "large", "all"],
        required=True,
    )
    parser.add_argument(
        "--benchmark-cmd",
        default="",
        help="Optional shell command to run after each scene switch",
    )
    args = parser.parse_args()

    session = McpSession(url=args.url, timeout_sec=args.timeout)
    session.initialize()
    resolved = resolve_instance_id(session, args.unity_instance)
    profiles = resolve_scene_profiles(args.scene_profile)
    for profile in profiles:
        scene_meta = switch_to_scene_profile(session, resolved, profile)
        print(f"switched scene_profile={profile} scene_path={scene_meta['scene_path']}")
        if args.benchmark_cmd:
            proc = subprocess.run(args.benchmark_cmd, shell=True)
            if proc.returncode != 0:
                return proc.returncode

    return 0


if __name__ == "__main__":
    sys.exit(main())
