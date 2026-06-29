"""Unit tests for tincand/mcp/server.py — error mapping, get_daemon_status guarantee,
and __main__ --help smoke test."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest
from mcp.server.fastmcp.exceptions import ToolError

import tincand.mcp.server as server_mod
from tincand.mcp.dbus_bridge import (
    TincandError,
    TincandInvalidArgument,
    TincandNotConnected,
    TincandNotRunning,
)


@pytest.fixture()
def mock_bridge():
    bridge = MagicMock()
    with patch.object(server_mod, "_bridge", bridge):
        yield bridge


_FALLBACK_STATUS = {
    "connected": False,
    "device_address": "",
    "device_name": "",
    "capabilities": {
        "messages": False,
        "contacts": False,
        "contacts_empty": True,
        "ancs": False,
        "ancs_needs_repair": False,
    },
}


class TestGetDaemonStatusAlwaysSucceeds:
    """get_daemon_status must never raise — docstring guarantee."""

    def test_returns_status_when_daemon_ok(self, mock_bridge):
        mock_bridge.get_status.return_value = {
            "connected": True,
            "device_address": "AA:BB:CC:DD:EE:FF",
            "device_name": "Test Phone",
            "capabilities": {
                "messages": True,
                "contacts": True,
                "contacts_empty": False,
                "ancs": False,
                "ancs_needs_repair": False,
            },
        }
        result = server_mod.get_daemon_status()
        assert result["connected"] is True
        assert result["device_address"] == "AA:BB:CC:DD:EE:FF"

    def test_returns_fallback_when_daemon_not_running(self, mock_bridge):
        mock_bridge.get_status.side_effect = TincandNotRunning("not running")
        result = server_mod.get_daemon_status()
        assert result == _FALLBACK_STATUS

    def test_fallback_connected_is_false(self, mock_bridge):
        mock_bridge.get_status.side_effect = TincandNotRunning("not running")
        assert server_mod.get_daemon_status()["connected"] is False

    def test_raises_tool_error_on_not_connected(self, mock_bridge):
        mock_bridge.get_status.side_effect = TincandNotConnected("not connected")
        with pytest.raises(ToolError):
            server_mod.get_daemon_status()

    def test_raises_tool_error_on_tincan_error(self, mock_bridge):
        mock_bridge.get_status.side_effect = TincandError("fail", "im.tincan.Error.Unknown")
        with pytest.raises(ToolError):
            server_mod.get_daemon_status()


class TestErrorMapping:
    """_mcp_error must convert each bridge exception to ToolError with appropriate message."""

    def test_not_running_maps_to_tool_error(self, mock_bridge):
        mock_bridge.list_conversations.side_effect = TincandNotRunning("not running")
        with pytest.raises(ToolError, match="not running"):
            server_mod.list_conversations()

    def test_not_connected_maps_to_tool_error(self, mock_bridge):
        mock_bridge.list_conversations.side_effect = TincandNotConnected("not connected")
        with pytest.raises(ToolError, match="not connected"):
            server_mod.list_conversations()

    def test_invalid_argument_maps_to_tool_error(self, mock_bridge):
        mock_bridge.send_message.side_effect = TincandInvalidArgument("bad arg")
        with pytest.raises(ToolError, match="Invalid argument"):
            server_mod.send_message("+1234567890", "hello")

    def test_tincan_error_maps_to_tool_error(self, mock_bridge):
        mock_bridge.send_message.side_effect = TincandError("fail", "im.tincan.Error.X")
        with pytest.raises(ToolError):
            server_mod.send_message("+1234567890", "hello")

    def test_get_contacts_not_connected(self, mock_bridge):
        mock_bridge.get_contacts.side_effect = TincandNotConnected("not connected")
        with pytest.raises(ToolError):
            server_mod.get_contacts()


class TestSendMessageDocstring:
    def test_side_effect_warning_present(self):
        doc = server_mod.send_message.__doc__
        assert "SIDE EFFECT" in doc


class TestSetAppFilterDocstring:
    def test_next_notification_line_present(self):
        doc = server_mod.set_app_filter.__doc__
        assert "next notification" in doc


class TestMainHelp:
    """python -m tincand.mcp --help must exit 0 and print usage."""

    def test_help_exits_0(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["tincand.mcp", "--help"])
        from tincand.mcp.__main__ import main
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

    def test_help_prints_usage(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["tincand.mcp", "--help"])
        from tincand.mcp.__main__ import main
        with pytest.raises(SystemExit):
            main()
        out = capsys.readouterr().out
        assert "usage" in out.lower()
        assert "get_daemon_status" in out
