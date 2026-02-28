#!/usr/bin/env python3
"""Tier 2 deterministic task definitions for end-to-end benchmark."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PolicyStep:
    action: str
    tool_name: str
    arguments: dict[str, Any]
    extract: list[str]
    description: str
    wrapper_needs_followup: bool = False
    followup_tool: str | None = None
    followup_args: dict[str, Any] | None = None


@dataclass
class TaskDef:
    id: str
    name: str
    category: str
    description: str
    setup_steps: list[PolicyStep] = field(default_factory=list)
    verify_steps: list[PolicyStep] = field(default_factory=list)
    cleanup_steps: list[PolicyStep] = field(default_factory=list)


CREATE_TAGGED_CUBE = TaskDef(
    id="create_tagged_cube",
    name="Create Tagged Cube",
    category="write-heavy",
    description=(
        "Create Bench_Cube at origin, add Rigidbody(mass=2), and assign BenchTag."
    ),
    setup_steps=[
        PolicyStep(
            action="tool_call",
            tool_name="manage_editor",
            arguments={"action": "add_tag", "tag_name": "BenchTag"},
            extract=["tag_created"],
            description="Ensure BenchTag exists.",
        ),
        PolicyStep(
            action="tool_call",
            tool_name="manage_gameobject",
            arguments={
                "action": "create",
                "name": "Bench_Cube",
                "primitive_type": "Cube",
                "position": [0.0, 0.0, 0.0],
            },
            extract=["created_id", "created_name"],
            description="Create Bench_Cube at world origin.",
        ),
        PolicyStep(
            action="tool_call",
            tool_name="manage_components",
            arguments={
                "action": "add",
                "target": "Bench_Cube",
                "search_method": "by_name",
                "component_name": "Rigidbody",
                "properties": {"mass": 2.0},
            },
            extract=["rigidbody_added"],
            description="Add Rigidbody with mass=2.",
        ),
        PolicyStep(
            action="tool_call",
            tool_name="manage_gameobject",
            arguments={
                "action": "modify",
                "target": "Bench_Cube",
                "search_method": "by_name",
                "tag": "BenchTag",
            },
            extract=["tag_set"],
            description="Assign BenchTag to Bench_Cube.",
        ),
    ],
    verify_steps=[
        PolicyStep(
            action="verify",
            tool_name="find_gameobjects",
            arguments={
                "name": "Bench_Cube",
                "search_method": "exact",
                "limit": 10,
                "cursor": 0,
            },
            extract=["bench_cube_exists", "bench_cube_ids", "truncated", "next_cursor"],
            description="Verify Bench_Cube exists.",
            wrapper_needs_followup=True,
            followup_tool="find_gameobjects",
            followup_args={
                "name": "Bench_Cube",
                "search_method": "exact",
                "fields": ["id", "name", "parent"],
                "limit": 100,
                "cursor": 0,
            },
        ),
        PolicyStep(
            action="verify",
            tool_name="read_resource",
            arguments={
                "uri_template": "mcpforunity://gameobject/{first_bench_cube_id}/components"
            },
            extract=["has_rigidbody", "rigidbody_mass"],
            description="Verify Bench_Cube contains Rigidbody with expected mass.",
        ),
    ],
    cleanup_steps=[
        PolicyStep(
            action="tool_call",
            tool_name="manage_gameobject",
            arguments={
                "action": "delete",
                "target": "Bench_Cube",
                "search_method": "by_name",
            },
            extract=["deleted"],
            description="Delete Bench_Cube.",
        )
    ],
)


HIERARCHY_AUDIT = TaskDef(
    id="hierarchy_audit",
    name="Hierarchy Audit",
    category="read-heavy",
    description=(
        "Read hierarchy, count roots, then count descendants for each root and re-check "
        "with a second full hierarchy fetch."
    ),
    setup_steps=[
        PolicyStep(
            action="tool_call",
            tool_name="manage_scene",
            arguments={
                "action": "get_hierarchy",
                "page_size": 120,
                "cursor": 0,
                "include_transform": False,
                "max_depth": 8,
            },
            extract=[
                "hierarchy_rows",
                "root_ids",
                "root_count",
                "truncated",
                "next_cursor",
            ],
            description="Fetch hierarchy snapshot and derive root objects.",
            wrapper_needs_followup=True,
            followup_tool="manage_scene",
            followup_args={
                "action": "get_hierarchy",
                "page_size": 120,
                "cursor": "{next_cursor}",
                "include_transform": False,
                "max_depth": 8,
            },
        ),
        PolicyStep(
            action="tool_call",
            tool_name="find_gameobjects",
            arguments={
                "action": "children",
                "search_method": "by_parent_id",
                "parent_id": "{item}",
                "__for_each_fact": "root_ids",
                "limit": 500,
                "cursor": 0,
            },
            extract=["descendant_counts"],
            description="Count descendants for each root via child query.",
            wrapper_needs_followup=True,
            followup_tool="find_gameobjects",
            followup_args={
                "action": "children",
                "search_method": "by_parent_id",
                "parent_id": "{item}",
                "limit": 500,
                "cursor": "{next_cursor}",
                "fields": ["id", "name", "parent"],
            },
        ),
    ],
    verify_steps=[
        PolicyStep(
            action="verify",
            tool_name="manage_scene",
            arguments={
                "action": "get_hierarchy",
                "page_size": 200,
                "cursor": 0,
                "include_transform": False,
                "max_depth": 8,
            },
            extract=["verify_root_count", "verify_descendant_total", "counts_match"],
            description="Refetch hierarchy and compare counts with first pass.",
        )
    ],
    cleanup_steps=[],
)


MATERIAL_SWAP = TaskDef(
    id="material_swap",
    name="Material Swap",
    category="mixed",
    description=(
        "Ensure Bench_Glow material exists and assign it to objects named "
        "Bench_Target_*."
    ),
    setup_steps=[
        PolicyStep(
            action="tool_call",
            tool_name="manage_asset",
            arguments={
                "action": "search",
                "path": "Assets/Bench",
                "query": "Bench_Glow",
                "filter_type": "Material",
                "page_size": 20,
                "page_number": 1,
            },
            extract=["bench_glow_found", "bench_glow_path"],
            description="Search for Bench_Glow material asset.",
            wrapper_needs_followup=True,
            followup_tool="manage_asset",
            followup_args={
                "action": "search",
                "path": "Assets/Bench",
                "query": "Bench_Glow",
                "filter_type": "Material",
                "page_size": 100,
                "page_number": 1,
                "fields": ["path", "name"],
            },
        ),
        PolicyStep(
            action="followup",
            tool_name="manage_material",
            arguments={
                "action": "create_if_missing",
                "name": "Bench_Glow",
                "path": "Assets/Bench/Bench_Glow.mat",
                "shader": "Universal Render Pipeline/Lit",
            },
            extract=["material_created_or_exists", "bench_glow_path"],
            description="Create Bench_Glow material when missing.",
        ),
        PolicyStep(
            action="tool_call",
            tool_name="find_gameobjects",
            arguments={
                "name_prefix": "Bench_Target_",
                "search_method": "prefix",
                "limit": 200,
                "cursor": 0,
            },
            extract=[
                "target_ids",
                "target_names",
                "target_count",
                "truncated",
                "next_cursor",
            ],
            description="Find all Bench_Target_* objects.",
            wrapper_needs_followup=True,
            followup_tool="find_gameobjects",
            followup_args={
                "name_prefix": "Bench_Target_",
                "search_method": "prefix",
                "fields": ["id", "name", "parent"],
                "limit": 200,
                "cursor": "{next_cursor}",
            },
        ),
        PolicyStep(
            action="tool_call",
            tool_name="manage_components",
            arguments={
                "action": "set_property",
                "component_name": "Renderer",
                "property_path": "material",
                "value": "{bench_glow_path}",
                "target": "{item}",
                "search_method": "by_id",
                "__for_each_fact": "target_ids",
            },
            extract=["material_assignments"],
            description="Assign Bench_Glow to each target renderer.",
        ),
    ],
    verify_steps=[
        PolicyStep(
            action="verify",
            tool_name="read_resource",
            arguments={
                "uri_template": "mcpforunity://gameobject/{item}/components",
                "__for_each_fact": "target_ids",
            },
            extract=["material_verified_count", "material_mismatch_ids"],
            description="Verify each target renderer references Bench_Glow.",
        )
    ],
    cleanup_steps=[],
)


def get_task_stub(task_id: str) -> TaskDef:
    return TaskDef(
        id=task_id,
        name=f"[STUB] {task_id}",
        category="mixed",
        description="Placeholder task definition for Tier 2 benchmark expansion.",
        setup_steps=[],
        verify_steps=[],
        cleanup_steps=[],
    )


STUB_TASK_IDS = [
    "batch_grid_spawner",
    "prefab_roundtrip",
    "basic_ui_setup",
    "large_asset_inventory_filter",
    "console_driven_fix_loop",
]

ALL_TASKS: list[TaskDef] = [
    CREATE_TAGGED_CUBE,
    HIERARCHY_AUDIT,
    MATERIAL_SWAP,
    *[get_task_stub(task_id) for task_id in STUB_TASK_IDS],
]

IMPLEMENTED_TASKS: list[str] = [
    CREATE_TAGGED_CUBE.id,
    HIERARCHY_AUDIT.id,
    MATERIAL_SWAP.id,
]
