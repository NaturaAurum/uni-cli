"""Shared fixtures for uni-cli tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from uni_cli.transport.mcp_client import McpClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_client() -> McpClient:
    client = McpClient(url="http://localhost:8080/mcp")
    client.session_id = "test-session-id"
    client.call_tool = MagicMock()  # type: ignore[assignment]
    client.read_resource = MagicMock()  # type: ignore[assignment]
    client.list_tools = MagicMock()  # type: ignore[assignment]
    return client


@pytest.fixture()
def hierarchy_response() -> dict[str, Any]:
    return {
        "hierarchy": [
            {"instanceID": 1, "name": "Camera", "parentInstanceID": -1, "active": True},
            {"instanceID": 2, "name": "Light", "parentInstanceID": -1, "active": True},
        ],
    }


@pytest.fixture()
def empty_hierarchy_response() -> dict[str, Any]:
    return {"hierarchy": []}


@pytest.fixture()
def object_create_response() -> dict[str, Any]:
    return {"instanceID": 123, "name": "Cube"}


@pytest.fixture()
def asset_search_response() -> dict[str, Any]:
    return {
        "assets": [
            {
                "path": "Assets/Scenes/Main.unity",
                "name": "Main.unity",
                "assetType": "Scene",
            },
            {
                "path": "Assets/Scripts/Player.cs",
                "name": "Player.cs",
                "assetType": "MonoScript",
            },
        ],
    }


@pytest.fixture()
def batch_response() -> dict[str, Any]:
    return {
        "results": [
            {"id": "op1", "success": True},
            {"id": "op2", "success": True},
            {"id": "op3", "error": "Not found"},
        ],
    }


@pytest.fixture()
def error_response() -> dict[str, Any]:
    return {"error": "Not found"}
