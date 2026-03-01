"""Tests for uni_cli.transport.mcp_client — 3-2."""

from __future__ import annotations

import io
import json
from unittest.mock import MagicMock, patch

import pytest
from helpers import make_instances_resource, make_tool_result
from uni_cli.transport.mcp_client import (
    McpClient,
    McpError,
    extract_text,
    parse_result_json,
    resolve_instance,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_urlopen(
    response_body: str | bytes,
    *,
    status: int = 200,
    content_type: str = "application/json",
    session_id: str | None = None,
) -> MagicMock:
    """Create a mock for urllib.request.urlopen returning given body."""
    if isinstance(response_body, str):
        response_body = response_body.encode("utf-8")

    resp = MagicMock()
    resp.read.return_value = response_body
    resp.readline = io.BytesIO(response_body).readline
    resp.status = status
    headers = MagicMock()
    headers.get = lambda key, default=None: {
        "content-type": content_type,
        "mcp-session-id": session_id,
    }.get(key, default)
    resp.headers = headers
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# ---------------------------------------------------------------------------
# JSON-RPC request format
# ---------------------------------------------------------------------------


class TestJsonRpcFormat:
    @patch("uni_cli.transport.mcp_client.urllib.request.urlopen")
    def test_call_tool_sends_correct_jsonrpc(self, mock_urlopen: MagicMock) -> None:
        """call_tool must send {"jsonrpc": "2.0", "method": "tools/call", "id": N}."""
        result_payload = json.dumps({"jsonrpc": "2.0", "id": 2, "result": make_tool_result({"ok": True})})
        mock_urlopen.return_value = _fake_urlopen(result_payload)

        client = McpClient(url="http://localhost:8080/mcp")
        client.session_id = "sid-1"
        client._seq = 2
        client.call_tool("manage_scene", {"action": "get_hierarchy"})

        call_args = mock_urlopen.call_args
        request_obj = call_args[0][0]
        sent_body = json.loads(request_obj.data.decode("utf-8"))

        assert sent_body["jsonrpc"] == "2.0"
        assert sent_body["method"] == "tools/call"
        assert sent_body["id"] == 2
        assert sent_body["params"]["name"] == "manage_scene"
        assert sent_body["params"]["arguments"]["action"] == "get_hierarchy"

    @patch("uni_cli.transport.mcp_client.urllib.request.urlopen")
    def test_initialize_sends_correct_format(self, mock_urlopen: MagicMock) -> None:
        """initialize must send method='initialize' with protocolVersion."""
        init_response = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {}}})
        mock_urlopen.side_effect = [
            _fake_urlopen(init_response, session_id="new-sid"),
            _fake_urlopen("", status=200),
        ]

        client = McpClient(url="http://localhost:8080/mcp")
        client.initialize()

        init_call = mock_urlopen.call_args_list[0]
        sent = json.loads(init_call[0][0].data.decode("utf-8"))
        assert sent["method"] == "initialize"
        assert sent["params"]["protocolVersion"] == "2025-03-26"
        assert sent["params"]["clientInfo"]["name"] == "uni-cli"


# ---------------------------------------------------------------------------
# Session ID management
# ---------------------------------------------------------------------------


class TestSessionId:
    @patch("uni_cli.transport.mcp_client.urllib.request.urlopen")
    def test_session_id_captured_from_response(self, mock_urlopen: MagicMock) -> None:
        """First response's mcp-session-id header should be stored."""
        init_resp = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {}}})
        mock_urlopen.side_effect = [
            _fake_urlopen(init_resp, session_id="captured-sid"),
            _fake_urlopen("", status=200),
        ]

        client = McpClient(url="http://localhost:8080/mcp")
        client.initialize()
        assert client.session_id == "captured-sid"

    @patch("uni_cli.transport.mcp_client.urllib.request.urlopen")
    def test_session_id_sent_in_subsequent_requests(self, mock_urlopen: MagicMock) -> None:
        """After init, subsequent requests should include mcp-session-id header."""
        tool_resp = json.dumps({"jsonrpc": "2.0", "id": 1, "result": make_tool_result({"ok": True})})
        mock_urlopen.return_value = _fake_urlopen(tool_resp)

        client = McpClient(url="http://localhost:8080/mcp")
        client.session_id = "existing-sid"
        client.call_tool("manage_scene", {"action": "get_hierarchy"})

        request_obj = mock_urlopen.call_args[0][0]
        assert request_obj.get_header("Mcp-session-id") == "existing-sid"


# ---------------------------------------------------------------------------
# Sequence numbers
# ---------------------------------------------------------------------------


class TestSequenceNumbers:
    @patch("uni_cli.transport.mcp_client.urllib.request.urlopen")
    def test_id_increments_per_request(self, mock_urlopen: MagicMock) -> None:
        """Each call_tool should increment the sequence id."""
        client = McpClient(url="http://localhost:8080/mcp")
        client.session_id = "sid"

        def make_resp(req, **kwargs):
            body = json.loads(req.data.decode("utf-8"))
            resp_body = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": make_tool_result({"ok": True}),
                }
            )
            return _fake_urlopen(resp_body)

        mock_urlopen.side_effect = make_resp

        assert client._seq == 1
        client.call_tool("tool_a", {})
        assert client._seq == 2
        client.call_tool("tool_b", {})
        assert client._seq == 3


# ---------------------------------------------------------------------------
# McpError
# ---------------------------------------------------------------------------


class TestMcpError:
    @patch("uni_cli.transport.mcp_client.urllib.request.urlopen")
    def test_jsonrpc_error_raises_mcp_error(self, mock_urlopen: MagicMock) -> None:
        """JSON-RPC error response should raise McpError."""
        error_resp = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "error": {"code": -32600, "message": "Invalid Request"},
            }
        )
        mock_urlopen.return_value = _fake_urlopen(error_resp)

        client = McpClient(url="http://localhost:8080/mcp")
        client.session_id = "sid"
        with pytest.raises(McpError) as exc_info:
            client.call_tool("bad_tool", {})
        assert exc_info.value.code == "-32600"
        assert "Invalid Request" in exc_info.value.message

    @patch("uni_cli.transport.mcp_client.urllib.request.urlopen")
    def test_tool_is_error_raises_mcp_error(self, mock_urlopen: MagicMock) -> None:
        """Tool result with isError=True should raise McpError."""
        result = make_tool_result({"error": "something broke"}, is_error=True)
        resp = json.dumps({"jsonrpc": "2.0", "id": 1, "result": result})
        mock_urlopen.return_value = _fake_urlopen(resp)

        client = McpClient(url="http://localhost:8080/mcp")
        client.session_id = "sid"
        with pytest.raises(McpError) as exc_info:
            client.call_tool("broken_tool", {})
        assert exc_info.value.code == "TOOL_ERROR"

    @patch("uni_cli.transport.mcp_client.urllib.request.urlopen")
    def test_no_response_raises_mcp_error(self, mock_urlopen: MagicMock) -> None:
        """Empty/unparseable response should raise McpError(NO_RESPONSE)."""
        mock_urlopen.return_value = _fake_urlopen("not json at all")

        client = McpClient(url="http://localhost:8080/mcp")
        client.session_id = "sid"
        with pytest.raises(McpError) as exc_info:
            client.call_tool("some_tool", {})
        assert exc_info.value.code == "NO_RESPONSE"

    def test_mcp_error_attributes(self) -> None:
        err = McpError("CODE", "msg", {"extra": 1})
        assert err.code == "CODE"
        assert err.message == "msg"
        assert err.data == {"extra": 1}
        assert "CODE: msg" in str(err)

    @patch("uni_cli.transport.mcp_client.urllib.request.urlopen")
    def test_init_failure_raises(self, mock_urlopen: MagicMock) -> None:
        """initialize with no result should raise McpError(INIT_FAILED)."""
        mock_urlopen.return_value = _fake_urlopen("{}")

        client = McpClient(url="http://localhost:8080/mcp")
        with pytest.raises(McpError) as exc_info:
            client.initialize()
        assert exc_info.value.code == "INIT_FAILED"


# ---------------------------------------------------------------------------
# Instance resolution
# ---------------------------------------------------------------------------


class TestInstanceResolution:
    def test_no_selector_returns_first(self, mock_client: McpClient) -> None:
        """No selector → return first available instance."""
        mock_client.read_resource.return_value = make_instances_resource(
            {"id": "proj@aaa", "name": "MyProject"},
            {"id": "proj@bbb", "name": "OtherProject"},
        )
        result = resolve_instance(mock_client, None)
        assert result == "proj@aaa"

    def test_exact_id_match(self, mock_client: McpClient) -> None:
        mock_client.read_resource.return_value = make_instances_resource(
            {"id": "proj@aaa", "name": "A"},
            {"id": "proj@bbb", "name": "B"},
        )
        result = resolve_instance(mock_client, "proj@bbb")
        assert result == "proj@bbb"

    def test_prefix_match(self, mock_client: McpClient) -> None:
        mock_client.read_resource.return_value = make_instances_resource(
            {"id": "myproject@abc123def", "name": "MyProject"},
        )
        result = resolve_instance(mock_client, "myproject@abc")
        assert result == "myproject@abc123def"

    def test_name_match(self, mock_client: McpClient) -> None:
        mock_client.read_resource.return_value = make_instances_resource(
            {"id": "proj@aaa", "name": "Alpha"},
            {"id": "proj@bbb", "name": "Beta"},
        )
        result = resolve_instance(mock_client, "Beta")
        assert result == "proj@bbb"

    def test_ambiguous_name_raises(self, mock_client: McpClient) -> None:
        mock_client.read_resource.return_value = make_instances_resource(
            {"id": "a@1", "name": "Same"},
            {"id": "b@2", "name": "Same"},
        )
        with pytest.raises(McpError) as exc_info:
            resolve_instance(mock_client, "Same")
        assert exc_info.value.code == "AMBIGUOUS_INSTANCE"

    def test_not_found_raises(self, mock_client: McpClient) -> None:
        mock_client.read_resource.return_value = make_instances_resource(
            {"id": "proj@aaa", "name": "Alpha"},
        )
        with pytest.raises(McpError) as exc_info:
            resolve_instance(mock_client, "NonExistent")
        assert exc_info.value.code == "INSTANCE_NOT_FOUND"

    def test_no_instances_raises(self, mock_client: McpClient) -> None:
        mock_client.read_resource.return_value = {"contents": []}
        with pytest.raises(McpError) as exc_info:
            resolve_instance(mock_client, None)
        assert exc_info.value.code == "NO_INSTANCES"


# ---------------------------------------------------------------------------
# extract_text / parse_result_json
# ---------------------------------------------------------------------------


class TestTextHelpers:
    def test_extract_text(self) -> None:
        result = make_tool_result({"hello": "world"})
        text = extract_text(result)
        parsed = json.loads(text)
        assert parsed == {"hello": "world"}

    def test_extract_text_empty(self) -> None:
        assert extract_text({"content": []}) == ""

    def test_parse_result_json(self) -> None:
        result = make_tool_result({"key": "value"})
        parsed = parse_result_json(result)
        assert parsed == {"key": "value"}

    def test_parse_result_json_non_json(self) -> None:
        result = {"content": [{"type": "text", "text": "plain text"}]}
        assert parse_result_json(result) is None

    def test_parse_result_json_empty(self) -> None:
        result = {"content": [{"type": "text", "text": ""}]}
        assert parse_result_json(result) is None
