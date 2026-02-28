"""Tests for uni_cli.formatter.compact — 3-1."""

from __future__ import annotations

from typing import Any

import pytest

from uni_cli.formatter.compact import (
    _esc,
    format_batch,
    format_error,
    format_hierarchy,
    format_json,
    format_object_result,
    format_ok,
    format_result,
    format_row,
    format_subsystem_result,
)


# ---------------------------------------------------------------------------
# _esc
# ---------------------------------------------------------------------------


class TestEsc:
    def test_none(self) -> None:
        assert _esc(None) == "-"

    def test_empty(self) -> None:
        assert _esc("") == "-"

    def test_whitespace_only(self) -> None:
        assert _esc("   ") == "-"

    def test_simple(self) -> None:
        assert _esc("Camera") == "Camera"

    def test_spaces_become_underscores(self) -> None:
        assert _esc("My Object") == "My_Object"

    def test_newlines_replaced(self) -> None:
        assert _esc("line1\nline2") == "line1_line2"

    def test_integer(self) -> None:
        assert _esc(123) == "123"

    def test_bool(self) -> None:
        assert _esc(True) == "True"


# ---------------------------------------------------------------------------
# format_error / format_ok / format_row
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_format_error(self) -> None:
        result = format_error("NOT_FOUND", "Object not found")
        assert result == "err code=NOT_FOUND msg=Object_not_found"

    def test_format_ok_basic(self) -> None:
        result = format_ok("hierarchy.ls", count=2)
        assert result == "ok op=hierarchy.ls count=2"

    def test_format_ok_multiple_kv(self) -> None:
        result = format_ok("hierarchy.ls", count=2, next="-", truncated=0)
        assert "op=hierarchy.ls" in result
        assert "count=2" in result
        assert "truncated=0" in result

    def test_format_row(self) -> None:
        fields = {"id": "instanceID", "name": "name"}
        data = {"instanceID": 1, "name": "Camera"}
        result = format_row(fields, data)
        assert result == "row id=1 name=Camera"

    def test_format_row_missing_field(self) -> None:
        fields = {"id": "instanceID", "name": "name", "tag": "tag"}
        data = {"instanceID": 1, "name": "Camera"}
        result = format_row(fields, data)
        assert "tag=-" in result


# ---------------------------------------------------------------------------
# format_hierarchy (collection)
# ---------------------------------------------------------------------------


class TestFormatHierarchy:
    def test_collection(self, hierarchy_response: dict[str, Any]) -> None:
        result = format_hierarchy(
            hierarchy_response, ["id", "name", "parent"], 120, "0"
        )
        lines = result.strip().split("\n")
        assert len(lines) == 3  # 2 rows + 1 ok
        assert lines[0].startswith("row ")
        assert "id=1" in lines[0]
        assert "name=Camera" in lines[0]
        assert lines[1].startswith("row ")
        assert "id=2" in lines[1]
        assert "name=Light" in lines[1]
        assert lines[2].startswith("ok op=hierarchy.ls")
        assert "count=2" in lines[2]

    def test_empty_collection(self, empty_hierarchy_response: dict[str, Any]) -> None:
        result = format_hierarchy(empty_hierarchy_response, ["id", "name"], 120, "0")
        lines = result.strip().split("\n")
        assert len(lines) == 1
        assert "count=0" in lines[0]
        assert lines[0].startswith("ok op=hierarchy.ls")

    def test_limit_truncation(self) -> None:
        nodes = [{"instanceID": i, "name": f"Obj{i}"} for i in range(10)]
        data = {"hierarchy": nodes}
        result = format_hierarchy(data, ["id", "name"], 3, "0")
        lines = result.strip().split("\n")
        assert len(lines) == 4  # 3 rows + 1 ok
        assert "count=3" in lines[-1]
        assert "truncated=1" in lines[-1]

    def test_no_truncation_marker_when_within_limit(self) -> None:
        data = {"hierarchy": [{"instanceID": 1, "name": "A"}]}
        result = format_hierarchy(data, ["id"], 10, "0")
        assert "truncated=0" in result

    def test_field_aliases(self) -> None:
        """instanceID should map to 'id' field alias."""
        data = {
            "hierarchy": [{"instanceID": 42, "name": "Obj", "parentInstanceID": -1}]
        }
        result = format_hierarchy(data, ["id", "name", "parent"], 10, "0")
        assert "id=42" in result
        assert "parent=-1" in result

    def test_alternate_data_keys(self) -> None:
        """nodes key should also work as hierarchy source."""
        data = {"nodes": [{"instanceID": 5, "name": "NodeObj"}]}
        result = format_hierarchy(data, ["id", "name"], 10, "0")
        assert "id=5" in result
        assert "name=NodeObj" in result

    def test_next_cursor(self) -> None:
        data = {"hierarchy": [{"instanceID": 1, "name": "A"}], "nextCursor": "abc123"}
        result = format_hierarchy(data, ["id"], 10, "0")
        assert "next=abc123" in result


# ---------------------------------------------------------------------------
# format_object_result (single item)
# ---------------------------------------------------------------------------


class TestFormatObjectResult:
    def test_create(self, object_create_response: dict[str, Any]) -> None:
        result = format_object_result("create", object_create_response)
        assert result == "ok op=object.create name=Cube id=123"

    def test_delete(self) -> None:
        data = {"name": "OldObject", "instanceID": 99}
        result = format_object_result("delete", data)
        assert "op=object.delete" in result
        assert "name=OldObject" in result

    def test_missing_fields_fallback(self) -> None:
        data: dict[str, Any] = {}
        result = format_object_result("get", data)
        assert "name=-" in result
        assert "id=-" in result


# ---------------------------------------------------------------------------
# format_asset_search
# ---------------------------------------------------------------------------


class TestFormatAssetSearch:
    def test_basic_search(self, asset_search_response: dict[str, Any]) -> None:
        from uni_cli.formatter.compact import format_asset_search

        result = format_asset_search(asset_search_response, ["path", "name"], 10)
        lines = result.strip().split("\n")
        assert len(lines) == 3  # 2 rows + ok
        assert "path=Assets/Scenes/Main.unity" in lines[0]
        assert "name=Main.unity" in lines[0]
        assert "count=2" in lines[-1]

    def test_truncation_at_limit(self) -> None:
        from uni_cli.formatter.compact import format_asset_search

        assets = [{"path": f"Assets/f{i}.cs", "name": f"f{i}.cs"} for i in range(5)]
        data = {"assets": assets}
        result = format_asset_search(data, ["path"], 3)
        lines = result.strip().split("\n")
        assert len(lines) == 4  # 3 rows + ok
        assert "truncated=1" in lines[-1]


# ---------------------------------------------------------------------------
# format_batch
# ---------------------------------------------------------------------------


class TestFormatBatch:
    def test_mixed_results(self, batch_response: dict[str, Any]) -> None:
        result = format_batch(batch_response)
        assert "op=batch.apply" in result
        assert "total=3" in result
        assert "ok_count=2" in result
        assert "fail_count=1" in result
        assert "fail_ids=op3" in result

    def test_all_success(self) -> None:
        data = {"results": [{"id": "a", "success": True}, {"id": "b", "success": True}]}
        result = format_batch(data)
        assert "total=2" in result
        assert "ok_count=2" in result
        assert "fail_count=0" in result
        assert "fail_ids" not in result

    def test_empty_results(self) -> None:
        data: dict[str, Any] = {"results": []}
        result = format_batch(data)
        assert "total=0" in result


# ---------------------------------------------------------------------------
# format_subsystem_result
# ---------------------------------------------------------------------------


class TestFormatSubsystemResult:
    def test_list_result(self) -> None:
        data = {
            "documents": [
                {"name": "MainUI.uxml", "path": "Assets/UI/MainUI.uxml"},
                {"name": "Style.uss", "path": "Assets/UI/Style.uss"},
            ]
        }
        result = format_subsystem_result("ui_toolkit", "list_documents", data)
        lines = result.strip().split("\n")
        assert len(lines) == 3  # 2 rows + ok
        assert "name=MainUI.uxml" in lines[0]
        assert "ok op=ui_toolkit.list_documents" in lines[-1]
        assert "count=2" in lines[-1]

    def test_single_item_result(self) -> None:
        data = {"graphId": "abc123", "nodeCount": 12}
        result = format_subsystem_result("shader_graph", "get_info", data)
        assert "ok op=shader_graph.get_info" in result
        assert "graphId=abc123" in result
        assert "nodeCount=12" in result

    def test_skips_internal_keys(self) -> None:
        data = {"success": True, "message": "done", "worldId": "w1"}
        result = format_subsystem_result("dots", "create_world", data)
        assert "worldId=w1" in result
        assert "success" not in result.split("op=")[1]
        assert "message" not in result.split("op=")[1]


# ---------------------------------------------------------------------------
# format_result (top-level dispatcher)
# ---------------------------------------------------------------------------


class TestFormatResult:
    def test_hierarchy_dispatch(self, hierarchy_response: dict[str, Any]) -> None:
        result = format_result("hierarchy", "ls", hierarchy_response)
        assert "op=hierarchy.ls" in result
        assert "count=2" in result

    def test_object_dispatch(self, object_create_response: dict[str, Any]) -> None:
        result = format_result("object", "create", object_create_response)
        assert "op=object.create" in result

    def test_asset_search_dispatch(self, asset_search_response: dict[str, Any]) -> None:
        result = format_result("asset", "search", asset_search_response)
        assert "op=asset.search" in result

    def test_batch_dispatch(self, batch_response: dict[str, Any]) -> None:
        result = format_result("batch", "apply", batch_response)
        assert "op=batch.apply" in result

    def test_subsystem_dispatch(self) -> None:
        data = {"items": [{"name": "g1"}]}
        result = format_result("ui-toolkit", "list", data)
        assert "op=ui_toolkit.list" in result

    def test_fallback(self) -> None:
        data = {"foo": "bar", "baz": 42}
        result = format_result("unknown", "cmd", data)
        assert "op=unknown.cmd" in result
        assert "foo=bar" in result

    def test_unwrap_data_envelope(self) -> None:
        data = {"data": {"instanceID": 10, "name": "Wrapped"}}
        result = format_result("object", "create", data)
        assert "id=10" in result
        assert "name=Wrapped" in result

    def test_error_response(self, error_response: dict[str, Any]) -> None:
        # Error dict doesn't have special handling in format_result;
        # it goes through fallback formatter. The caller (main.py) handles
        # {"success": False} before reaching format_result.
        result = format_result("object", "get", error_response)
        assert "op=object.get" in result


# ---------------------------------------------------------------------------
# Special characters
# ---------------------------------------------------------------------------


class TestSpecialCharacters:
    def test_name_with_spaces(self) -> None:
        data = {"hierarchy": [{"instanceID": 1, "name": "My Object"}]}
        result = format_hierarchy(data, ["id", "name"], 10, "0")
        assert "name=My_Object" in result

    def test_name_with_quotes(self) -> None:
        """Quotes inside values are kept as-is after _esc (no space, no newline)."""
        data = {"hierarchy": [{"instanceID": 1, "name": 'Say"Hello"'}]}
        result = format_hierarchy(data, ["name"], 10, "0")
        # _esc only replaces spaces/newlines; quotes pass through
        assert 'name=Say"Hello"' in result

    def test_name_with_newlines(self) -> None:
        data = {"hierarchy": [{"instanceID": 1, "name": "Line1\nLine2"}]}
        result = format_hierarchy(data, ["name"], 10, "0")
        assert "name=Line1_Line2" in result


# ---------------------------------------------------------------------------
# format_json
# ---------------------------------------------------------------------------


class TestFormatJson:
    def test_basic(self) -> None:
        data = {"foo": 1}
        result = format_json(data)
        assert '"foo": 1' in result

    def test_unicode(self) -> None:
        data = {"name": "日本語"}
        result = format_json(data)
        assert "日本語" in result
