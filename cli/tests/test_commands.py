"""Tests for uni_cli.commands — 3-3."""

from __future__ import annotations

import json
from typing import Any

import pytest
from helpers import make_tool_result
from uni_cli.commands.asset import run_create as asset_create
from uni_cli.commands.asset import run_delete as asset_delete
from uni_cli.commands.asset import run_info as asset_info
from uni_cli.commands.asset import run_search as asset_search
from uni_cli.commands.batch import run_apply
from uni_cli.commands.hierarchy import run_ls
from uni_cli.commands.object import run_create as obj_create
from uni_cli.commands.object import run_delete as obj_delete
from uni_cli.commands.object import run_get as obj_get
from uni_cli.commands.object import run_modify as obj_modify
from uni_cli.commands.subsystem import run_subsystem
from uni_cli.transport.mcp_client import McpClient

INSTANCE_ID = "test-project@abc123"


# ---------------------------------------------------------------------------
# hierarchy.py
# ---------------------------------------------------------------------------


class TestHierarchy:
    def test_run_ls_calls_manage_scene(self, mock_client: McpClient) -> None:
        mock_client.call_tool.return_value = make_tool_result({"hierarchy": [{"instanceID": 1, "name": "Cam"}]})

        result = run_ls(mock_client, INSTANCE_ID, "id,name", 50, "0")

        mock_client.call_tool.assert_called_once_with(
            "manage_scene",
            {
                "action": "get_hierarchy",
                "page_size": 50,
                "cursor": 0,
                "include_transform": True,
                "max_depth": 4,
                "unity_instance": INSTANCE_ID,
            },
        )
        assert result["hierarchy"][0]["name"] == "Cam"

    def test_run_ls_cursor_string(self, mock_client: McpClient) -> None:
        mock_client.call_tool.return_value = make_tool_result({"hierarchy": []})

        run_ls(mock_client, INSTANCE_ID, "id", 10, "not_a_digit")

        args = mock_client.call_tool.call_args[0][1]
        assert args["cursor"] == 0


# ---------------------------------------------------------------------------
# object.py
# ---------------------------------------------------------------------------


class TestObject:
    def test_run_create(self, mock_client: McpClient) -> None:
        mock_client.call_tool.return_value = make_tool_result({"instanceID": 42, "name": "Sphere"})

        result = obj_create(mock_client, INSTANCE_ID, "Sphere", "Sphere", "1,2,3")

        args = mock_client.call_tool.call_args[0][1]
        assert args["action"] == "create"
        assert args["name"] == "Sphere"
        assert args["primitive_type"] == "Sphere"
        assert args["position"] == [1.0, 2.0, 3.0]
        assert args["unity_instance"] == INSTANCE_ID
        assert result["instanceID"] == 42

    def test_run_create_empty_preset_no_primitive(self, mock_client: McpClient) -> None:
        mock_client.call_tool.return_value = make_tool_result({"instanceID": 1, "name": "E"})

        obj_create(mock_client, INSTANCE_ID, "E", "empty", "0,0,0")

        args = mock_client.call_tool.call_args[0][1]
        assert "primitive_type" not in args
        assert "position" not in args

    def test_run_delete(self, mock_client: McpClient) -> None:
        mock_client.call_tool.return_value = make_tool_result({"name": "Gone"})

        obj_delete(mock_client, INSTANCE_ID, "OldObj")

        args = mock_client.call_tool.call_args[0][1]
        assert args["action"] == "delete"
        assert args["target"] == "OldObj"
        assert args["search_method"] == "by_name"

    def test_run_get(self, mock_client: McpClient) -> None:
        mock_client.call_tool.return_value = make_tool_result({"instanceID": 5, "name": "Player"})

        result = obj_get(mock_client, INSTANCE_ID, "Player")

        args = mock_client.call_tool.call_args[0][1]
        assert args["action"] == "get"
        assert args["target"] == "Player"
        assert result["name"] == "Player"

    def test_run_modify(self, mock_client: McpClient) -> None:
        mock_client.call_tool.return_value = make_tool_result({"name": "Renamed"})

        obj_modify(
            mock_client,
            INSTANCE_ID,
            "OldName",
            pos="1,2,3",
            parent="Parent",
            name="NewName",
            active=True,
        )

        args = mock_client.call_tool.call_args[0][1]
        assert args["action"] == "modify"
        assert args["target"] == "OldName"
        assert args["position"] == [1.0, 2.0, 3.0]
        assert args["parent"] == "Parent"
        assert args["name"] == "NewName"
        assert args["active"] is True

    def test_run_modify_partial(self, mock_client: McpClient) -> None:
        mock_client.call_tool.return_value = make_tool_result({"name": "X"})

        obj_modify(mock_client, INSTANCE_ID, "X")

        args = mock_client.call_tool.call_args[0][1]
        assert "position" not in args
        assert "parent" not in args
        assert "name" not in args
        assert "active" not in args


# ---------------------------------------------------------------------------
# asset.py
# ---------------------------------------------------------------------------


class TestAsset:
    def test_run_search(self, mock_client: McpClient) -> None:
        mock_client.call_tool.return_value = make_tool_result({"assets": [{"path": "Assets/x.cs"}]})

        asset_search(mock_client, INSTANCE_ID, "*.cs", "MonoScript", "path,name", 20)

        args = mock_client.call_tool.call_args[0][1]
        assert args["action"] == "search"
        assert args["search_pattern"] == "*.cs"
        assert args["filter_type"] == "MonoScript"
        assert args["page_size"] == 20
        assert args["unity_instance"] == INSTANCE_ID

    def test_run_search_no_filter(self, mock_client: McpClient) -> None:
        mock_client.call_tool.return_value = make_tool_result({"assets": []})

        asset_search(mock_client, INSTANCE_ID, "", None, "path", 10)

        args = mock_client.call_tool.call_args[0][1]
        assert "search_pattern" not in args
        assert "filter_type" not in args

    def test_run_info(self, mock_client: McpClient) -> None:
        mock_client.call_tool.return_value = make_tool_result({"path": "Assets/Tex.png", "size": 1024})

        asset_info(mock_client, INSTANCE_ID, "Assets/Tex.png")

        args = mock_client.call_tool.call_args[0][1]
        assert args["action"] == "get_info"
        assert args["path"] == "Assets/Tex.png"

    def test_run_create(self, mock_client: McpClient) -> None:
        mock_client.call_tool.return_value = make_tool_result({"path": "Assets/New.mat"})

        asset_create(mock_client, INSTANCE_ID, "Assets/New.mat", "Material")

        args = mock_client.call_tool.call_args[0][1]
        assert args["action"] == "create"
        assert args["path"] == "Assets/New.mat"
        assert args["asset_type"] == "Material"

    def test_run_delete(self, mock_client: McpClient) -> None:
        mock_client.call_tool.return_value = make_tool_result({"deleted": True})

        asset_delete(mock_client, INSTANCE_ID, "Assets/Old.mat")

        args = mock_client.call_tool.call_args[0][1]
        assert args["action"] == "delete"
        assert args["path"] == "Assets/Old.mat"


# ---------------------------------------------------------------------------
# batch.py
# ---------------------------------------------------------------------------


class TestBatch:
    def test_run_apply(self, mock_client: McpClient, tmp_path: Any) -> None:
        batch_file = tmp_path / "batch.json"
        batch_file.write_text(
            json.dumps(
                {
                    "commands": [
                        {
                            "tool": "manage_gameobject",
                            "params": {"action": "create", "name": "A"},
                        },
                        {
                            "tool": "manage_gameobject",
                            "params": {"action": "create", "name": "B"},
                        },
                    ],
                    "parallel": False,
                    "fail_fast": True,
                }
            )
        )

        mock_client.call_tool.return_value = make_tool_result({"results": [{"id": "op1"}, {"id": "op2"}]})

        run_apply(mock_client, INSTANCE_ID, str(batch_file))

        args = mock_client.call_tool.call_args[0][1]
        assert args["commands"][0]["params"]["unity_instance"] == INSTANCE_ID
        assert args["commands"][1]["params"]["unity_instance"] == INSTANCE_ID
        assert args["parallel"] is False
        assert args["fail_fast"] is True
        assert mock_client.call_tool.call_args[0][0] == "batch_execute"

    def test_run_apply_empty_commands(self, mock_client: McpClient, tmp_path: Any) -> None:
        batch_file = tmp_path / "empty.json"
        batch_file.write_text(json.dumps({"commands": []}))

        result = run_apply(mock_client, INSTANCE_ID, str(batch_file))

        assert result["success"] is False
        assert "No commands" in result["error"]
        mock_client.call_tool.assert_not_called()


# ---------------------------------------------------------------------------
# subsystem.py
# ---------------------------------------------------------------------------


class TestSubsystem:
    @pytest.mark.parametrize(
        "command,expected_tool",
        [
            ("ui-toolkit", "manage_ui_toolkit"),
            ("addressables", "manage_addressables"),
            ("dots", "manage_dots"),
            ("shader-graph", "manage_shader_graph"),
        ],
    )
    def test_tool_name_mapping(
        self,
        mock_client: McpClient,
        command: str,
        expected_tool: str,
    ) -> None:
        mock_client.call_tool.return_value = make_tool_result({"items": []})

        run_subsystem(mock_client, INSTANCE_ID, command, "list")

        assert mock_client.call_tool.call_args[0][0] == expected_tool

    def test_action_passed(self, mock_client: McpClient) -> None:
        mock_client.call_tool.return_value = make_tool_result({"items": []})

        run_subsystem(mock_client, INSTANCE_ID, "dots", "list_worlds")

        args = mock_client.call_tool.call_args[0][1]
        assert args["action"] == "list_worlds"
        assert args["unity_instance"] == INSTANCE_ID

    def test_extra_args_merged(self, mock_client: McpClient) -> None:
        mock_client.call_tool.return_value = make_tool_result({"items": []})

        run_subsystem(mock_client, INSTANCE_ID, "ui-toolkit", "create", {"path": "Assets/X.uxml"})

        args = mock_client.call_tool.call_args[0][1]
        assert args["path"] == "Assets/X.uxml"
        assert args["action"] == "create"

    def test_unknown_subsystem(self, mock_client: McpClient) -> None:
        result = run_subsystem(mock_client, INSTANCE_ID, "unknown-system", "list")

        assert result["success"] is False
        assert "Unknown subsystem" in result["error"]
        mock_client.call_tool.assert_not_called()
