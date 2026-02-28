#!/usr/bin/env python3
"""Mock Unity responses for benchmark PoC."""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from typing import Any


SCENARIOS = [
    "hierarchy_query",
    "object_create",
    "reparent",
    "asset_search",
    "batch_ops",
]

BASE_LATENCY_MS = {
    "hierarchy_query": 165,
    "object_create": 118,
    "reparent": 96,
    "asset_search": 184,
    "batch_ops": 248,
}

WRAP_LATENCY_MS = {
    "hierarchy_query": 109,
    "object_create": 84,
    "reparent": 73,
    "asset_search": 131,
    "batch_ops": 161,
}


def stable_rng(mode: str, scenario: str, iteration: int) -> random.Random:
    seed = f"{mode}:{scenario}:{iteration}"
    return random.Random(seed)


def maybe_fail(mode: str, scenario: str, iteration: int) -> bool:
    if scenario != "batch_ops" or iteration <= 0:
        return False
    if mode == "baseline":
        return iteration % 7 == 0
    return iteration % 19 == 0


def sleep_latency(mode: str, scenario: str, rng: random.Random) -> None:
    base = BASE_LATENCY_MS[scenario] if mode == "baseline" else WRAP_LATENCY_MS[scenario]
    jitter = rng.uniform(-14.0, 22.0)
    latency = max(5.0, base + jitter)
    time.sleep(latency / 1000.0)


def hierarchy_payload(mode: str, iteration: int, rng: random.Random) -> str:
    if mode == "baseline":
        nodes: list[dict[str, Any]] = []
        for idx in range(26):
            nodes.append(
                {
                    "id": f"go_{idx:04d}",
                    "name": f"Node_{idx}",
                    "path": f"/Root/Section_{idx // 5}/Node_{idx}",
                    "parentId": f"go_{max(0, idx - 1):04d}",
                    "activeSelf": idx % 4 != 0,
                    "tag": "Untagged",
                    "layer": 0,
                    "components": [
                        {"type": "Transform", "enabled": True},
                        {"type": "MeshRenderer", "enabled": idx % 3 != 0},
                        {"type": "MonoBehaviour", "enabled": True},
                    ],
                    "localPosition": {
                        "x": round(rng.uniform(-20, 20), 3),
                        "y": round(rng.uniform(-5, 30), 3),
                        "z": round(rng.uniform(-20, 20), 3),
                    },
                }
            )
        return json.dumps(
            {
                "ok": True,
                "op": "hierarchy.list",
                "requestId": f"req_h_{iteration}",
                "data": {"nodes": nodes, "depth": 3, "includeComponents": True},
                "meta": {"resultCount": len(nodes), "nextCursor": None},
            }
        )
    rows = []
    for idx in range(12):
        rows.append(f"go_{idx:04d}:Node_{idx}:go_{max(0, idx - 1):04d}")
    return (
        "ok op=hierarchy.list count=12 next=12 fields=id,name,parentId rows="
        + ",".join(rows)
    )


def object_create_payload(mode: str, iteration: int, rng: random.Random) -> str:
    obj_id = f"go_new_{iteration:04d}"
    if mode == "baseline":
        payload = {
            "ok": True,
            "op": "object.create",
            "requestId": f"req_c_{iteration}",
            "data": {
                "object": {
                    "id": obj_id,
                    "name": f"NewObject_{iteration}",
                    "parentId": "go_0000",
                    "components": [
                        {"type": "Transform", "enabled": True},
                        {"type": "MeshFilter", "enabled": True},
                        {"type": "MeshRenderer", "enabled": True},
                    ],
                    "transform": {
                        "position": {
                            "x": round(rng.uniform(-10, 10), 3),
                            "y": round(rng.uniform(0, 4), 3),
                            "z": round(rng.uniform(-10, 10), 3),
                        },
                        "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
                        "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
                    },
                }
            },
        }
        return json.dumps(payload)
    return f"ok op=object.create id={obj_id} parent=go_0000"


def reparent_payload(mode: str, iteration: int) -> str:
    target_id = f"go_{(iteration % 25) + 1:04d}"
    new_parent = f"go_{(iteration % 6):04d}"
    if mode == "baseline":
        return json.dumps(
            {
                "ok": True,
                "op": "object.reparent",
                "requestId": f"req_r_{iteration}",
                "data": {
                    "targetId": target_id,
                    "oldParentId": "go_0000",
                    "newParentId": new_parent,
                    "worldPositionStays": True,
                    "transformBefore": {"x": 1.0, "y": 2.0, "z": 3.0},
                    "transformAfter": {"x": 1.0, "y": 2.0, "z": 3.0},
                },
            }
        )
    return f"ok op=object.reparent id={target_id} parent={new_parent}"


def asset_search_payload(mode: str, iteration: int, rng: random.Random) -> str:
    if mode == "baseline":
        assets: list[dict[str, Any]] = []
        for idx in range(18):
            assets.append(
                {
                    "guid": f"guid_{iteration:03d}_{idx:03d}",
                    "path": f"Assets/Art/Folder_{idx % 4}/Tex_{idx}.png",
                    "name": f"Tex_{idx}",
                    "labels": ["ui", "hd"] if idx % 2 == 0 else ["world"],
                    "sizeBytes": int(rng.uniform(1000, 950000)),
                    "importer": {
                        "type": "TextureImporter",
                        "compression": "NormalQuality",
                        "maxSize": 2048,
                        "mipmap": idx % 2 == 0,
                    },
                    "lastModifiedUtc": "2026-02-20T03:11:24Z",
                }
            )
        return json.dumps(
            {
                "ok": True,
                "op": "asset.search",
                "requestId": f"req_a_{iteration}",
                "data": {"items": assets, "nextCursor": f"cursor_{iteration + 1}"},
                "meta": {"resultCount": len(assets), "query": "t:Texture"},
            }
        )
    ids = [f"guid_{iteration:03d}_{idx:03d}" for idx in range(10)]
    return (
        "ok op=asset.search count=10 next=cursor_"
        f"{iteration + 1} fields=guid,path rows="
        + ",".join(ids)
    )


def batch_payload(mode: str, iteration: int) -> str:
    total = 40
    if mode == "baseline":
        items: list[dict[str, Any]] = []
        for idx in range(total):
            items.append(
                {
                    "index": idx,
                    "op": "create_or_move",
                    "targetId": f"go_b_{idx:03d}",
                    "status": "ok",
                    "elapsedMs": 2 + (idx % 7),
                    "warnings": [] if idx % 9 else ["name_collision_renamed"],
                }
            )
        return json.dumps(
            {
                "ok": True,
                "op": "batch.apply",
                "requestId": f"req_b_{iteration}",
                "data": {"total": total, "okCount": total, "failCount": 0, "items": items},
            }
        )
    return f"ok op=batch.apply total={total} ok_count={total} fail_count=0"


def fail_payload(mode: str, scenario: str, iteration: int) -> str:
    if mode == "baseline":
        return json.dumps(
            {
                "ok": False,
                "op": scenario,
                "requestId": f"req_fail_{iteration}",
                "error": {
                    "code": "BATCH_PARTIAL_FAILURE",
                    "message": "2 operations failed due to duplicate names",
                    "details": {
                        "failedIndices": [19, 33],
                        "retriable": True,
                        "timeoutMs": 2500,
                    },
                },
            }
        )
    return "err code=BATCH_PARTIAL_FAILURE msg=2_failed_ops"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["baseline", "wrapper"], required=True)
    parser.add_argument("--scenario", choices=SCENARIOS, required=True)
    parser.add_argument("--iteration", type=int, default=0)
    args = parser.parse_args()

    rng = stable_rng(args.mode, args.scenario, args.iteration)
    sleep_latency(args.mode, args.scenario, rng)

    if maybe_fail(args.mode, args.scenario, args.iteration):
        print(fail_payload(args.mode, args.scenario, args.iteration))
        return 1

    if args.scenario == "hierarchy_query":
        print(hierarchy_payload(args.mode, args.iteration, rng))
    elif args.scenario == "object_create":
        print(object_create_payload(args.mode, args.iteration, rng))
    elif args.scenario == "reparent":
        print(reparent_payload(args.mode, args.iteration))
    elif args.scenario == "asset_search":
        print(asset_search_payload(args.mode, args.iteration, rng))
    elif args.scenario == "batch_ops":
        print(batch_payload(args.mode, args.iteration))
    else:
        print("err code=UNKNOWN_SCENARIO msg=unsupported")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

