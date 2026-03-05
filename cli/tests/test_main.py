"""Tests for uni_cli.main — 3-4."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from helpers import make_tool_result
from uni_cli.main import _build_parser, _dispatch, main

# ---------------------------------------------------------------------------
# argparse (_build_parser)
# ---------------------------------------------------------------------------


class TestArgparse:
    def test_hierarchy_ls(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["hierarchy", "ls", "--limit", "10"])
        assert args.command == "hierarchy"
        assert args.action == "ls"
        assert args.limit == 10

    def test_hierarchy_ls_defaults(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["hierarchy", "ls"])
        assert args.fields == "id,name,parent"
        assert args.limit == 120
        assert args.cursor == "0"

    def test_object_create(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["object", "create", "--name", "Cube", "--preset", "Cube"])
        assert args.command == "object"
        assert args.action == "create"
        assert args.name == "Cube"
        assert args.preset == "Cube"

    def test_object_modify(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(
            [
                "object",
                "modify",
                "--target",
                "Obj",
                "--pos",
                "1,2,3",
                "--name",
                "New",
            ]
        )
        assert args.target == "Obj"
        assert args.pos == "1,2,3"
        assert args.new_name == "New"

    def test_object_delete(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["object", "delete", "--target", "Obj"])
        assert args.action == "delete"
        assert args.target == "Obj"

    def test_asset_search(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(
            [
                "asset",
                "search",
                "--query",
                "*.cs",
                "--filter-type",
                "MonoScript",
                "--limit",
                "20",
            ]
        )
        assert args.command == "asset"
        assert args.action == "search"
        assert args.query == "*.cs"
        assert args.filter_type == "MonoScript"
        assert args.limit == 20

    def test_batch_apply(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["batch", "apply", "--file", "ops.json"])
        assert args.command == "batch"
        assert args.action == "apply"
        assert args.batch_file == "ops.json"

    def test_subsystem_action(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["ui-toolkit", "list_documents"])
        assert args.command == "ui-toolkit"
        assert args.action == "list_documents"

    def test_subsystem_extra_args(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["dots", "create_world", "--args", '{"name": "W1"}'])
        assert args.command == "dots"
        assert args.extra_args == '{"name": "W1"}'

    def test_format_flag(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["--format", "json", "hierarchy", "ls"])
        assert args.output_format == "json"

    def test_format_default(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["hierarchy", "ls"])
        assert args.output_format == "compact"

    def test_url_default(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["hierarchy", "ls"])
        assert args.url == "http://127.0.0.1:8080/mcp"

    def test_url_override(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["--url", "http://custom:9090/mcp", "hierarchy", "ls"])
        assert args.url == "http://custom:9090/mcp"

    def test_tools_command(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["tools"])
        assert args.command == "tools"


# ---------------------------------------------------------------------------
# _dispatch
# ---------------------------------------------------------------------------


class TestDispatch:
    def _make_args(self, argv: list[str]) -> Any:
        parser = _build_parser()
        return parser.parse_args(argv)

    @patch("uni_cli.commands.hierarchy.run_ls")
    def test_hierarchy_ls_dispatch(self, mock_run: MagicMock) -> None:
        mock_run.return_value = {"hierarchy": []}
        args = self._make_args(["hierarchy", "ls", "--limit", "5"])

        cmd, action, data = _dispatch(MagicMock(), "inst@1", args)

        assert cmd == "hierarchy"
        assert action == "ls"
        mock_run.assert_called_once()

    @patch("uni_cli.commands.object.run_create")
    def test_object_create_dispatch(self, mock_run: MagicMock) -> None:
        mock_run.return_value = {"instanceID": 1}
        args = self._make_args(["object", "create", "--name", "Cube"])

        cmd, action, _ = _dispatch(MagicMock(), "inst@1", args)

        assert cmd == "object"
        assert action == "create"
        mock_run.assert_called_once()

    @patch("uni_cli.commands.object.run_delete")
    def test_object_delete_dispatch(self, mock_run: MagicMock) -> None:
        mock_run.return_value = {}
        args = self._make_args(["object", "delete", "--target", "X"])

        cmd, action, _ = _dispatch(MagicMock(), "inst@1", args)

        assert cmd == "object"
        assert action == "delete"

    @patch("uni_cli.commands.object.run_get")
    def test_object_get_dispatch(self, mock_run: MagicMock) -> None:
        mock_run.return_value = {"name": "Obj"}
        args = self._make_args(["object", "get", "--target", "Obj"])

        cmd, action, _ = _dispatch(MagicMock(), "inst@1", args)

        assert cmd == "object"
        assert action == "get"

    @patch("uni_cli.commands.object.run_modify")
    def test_object_modify_dispatch(self, mock_run: MagicMock) -> None:
        mock_run.return_value = {"name": "Mod"}
        args = self._make_args(["object", "modify", "--target", "X"])

        cmd, action, _ = _dispatch(MagicMock(), "inst@1", args)

        assert cmd == "object"
        assert action == "modify"

    @patch("uni_cli.commands.asset.run_search")
    def test_asset_search_dispatch(self, mock_run: MagicMock) -> None:
        mock_run.return_value = {"assets": []}
        args = self._make_args(["asset", "search"])

        cmd, action, _ = _dispatch(MagicMock(), "inst@1", args)

        assert cmd == "asset"
        assert action == "search"

    @patch("uni_cli.commands.asset.run_info")
    def test_asset_info_dispatch(self, mock_run: MagicMock) -> None:
        mock_run.return_value = {"path": "x"}
        args = self._make_args(["asset", "info", "--path", "Assets/x.cs"])

        cmd, action, _ = _dispatch(MagicMock(), "inst@1", args)

        assert cmd == "asset"
        assert action == "info"

    @patch("uni_cli.commands.asset.run_create")
    def test_asset_create_dispatch(self, mock_run: MagicMock) -> None:
        mock_run.return_value = {"path": "x"}
        args = self._make_args(["asset", "create", "--path", "Assets/x.mat", "--type", "Material"])

        cmd, action, _ = _dispatch(MagicMock(), "inst@1", args)

        assert cmd == "asset"
        assert action == "create"

    @patch("uni_cli.commands.asset.run_delete")
    def test_asset_delete_dispatch(self, mock_run: MagicMock) -> None:
        mock_run.return_value = {}
        args = self._make_args(["asset", "delete", "--path", "Assets/x.mat"])

        cmd, action, _ = _dispatch(MagicMock(), "inst@1", args)

        assert cmd == "asset"
        assert action == "delete"

    @patch("uni_cli.commands.batch.run_apply")
    def test_batch_apply_dispatch(self, mock_run: MagicMock) -> None:
        mock_run.return_value = {"results": []}
        args = self._make_args(["batch", "apply", "--file", "ops.json"])

        cmd, action, _ = _dispatch(MagicMock(), "inst@1", args)

        assert cmd == "batch"
        assert action == "apply"

    @patch("uni_cli.commands.subsystem.run_subsystem")
    def test_subsystem_dispatch(self, mock_run: MagicMock) -> None:
        mock_run.return_value = {"items": []}
        args = self._make_args(["ui-toolkit", "list_documents"])

        cmd, action, _ = _dispatch(MagicMock(), "inst@1", args)

        assert cmd == "ui-toolkit"
        assert action == "list_documents"

    def test_tools_dispatch(self) -> None:
        mock_client = MagicMock()
        mock_client.list_tools.return_value = [
            {"name": "manage_scene", "description": "Scene ops"},
        ]
        args = self._make_args(["tools"])

        cmd, action, data = _dispatch(mock_client, "inst@1", args)

        assert cmd == "tools"
        assert action == "list"
        assert len(data["tools"]) == 1
        assert data["tools"][0]["name"] == "manage_scene"

    def test_unknown_command(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["hierarchy", "ls"])
        args.command = "nonexistent"
        args.action = "nope"

        _, _, data = _dispatch(MagicMock(), "inst@1", args)

        assert data.get("success") is False
        assert "Unknown command" in data.get("error", "")


# ---------------------------------------------------------------------------
# main (integration — format flag)
# ---------------------------------------------------------------------------


class TestMain:
    @patch("uni_cli.main.is_server_running", return_value=True)
    @patch("uni_cli.main.resolve_instance", return_value="inst@1")
    @patch("uni_cli.main.McpClient")
    def test_compact_output(
        self,
        MockClient: MagicMock,
        mock_resolve: MagicMock,
        mock_server_running: MagicMock,
        capsys: Any,
    ) -> None:
        client = MockClient.return_value
        client.initialize.return_value = {"capabilities": {}}
        client.call_tool.return_value = make_tool_result({"instanceID": 10, "name": "Cube"})

        with patch("sys.argv", ["uni-cli", "object", "create", "--name", "Cube"]):
            ret = main()

        assert ret == 0
        out = capsys.readouterr().out
        assert "op=object.create" in out
        assert "name=Cube" in out

    @patch("uni_cli.main.is_server_running", return_value=True)
    @patch("uni_cli.main.resolve_instance", return_value="inst@1")
    @patch("uni_cli.main.McpClient")
    def test_json_output(
        self,
        MockClient: MagicMock,
        mock_resolve: MagicMock,
        mock_server_running: MagicMock,
        capsys: Any,
    ) -> None:
        client = MockClient.return_value
        client.initialize.return_value = {"capabilities": {}}
        client.call_tool.return_value = make_tool_result({"instanceID": 10, "name": "Cube"})

        with patch(
            "sys.argv",
            ["uni-cli", "--format", "json", "object", "create", "--name", "C"],
        ):
            ret = main()

        assert ret == 0
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed["instanceID"] == 10

    @patch("uni_cli.main.McpClient")
    def test_no_command_shows_help(self, MockClient: MagicMock, capsys: Any) -> None:
        with patch("sys.argv", ["uni-cli"]):
            ret = main()

        assert ret == 0
        out = capsys.readouterr().out
        assert "usage:" in out.lower() or "uni-cli" in out

    @patch("uni_cli.main.is_server_running", return_value=True)
    @patch("uni_cli.main.McpClient")
    def test_connection_error(self, MockClient: MagicMock, mock_server_running: MagicMock, capsys: Any) -> None:
        from uni_cli.transport.mcp_client import McpError

        client = MockClient.return_value
        client.initialize.side_effect = McpError("INIT_FAILED", "conn refused")

        with patch("sys.argv", ["uni-cli", "hierarchy", "ls"]):
            ret = main()

        assert ret == 1
        out = capsys.readouterr().out
        assert "err" in out
        assert "INIT_FAILED" in out
