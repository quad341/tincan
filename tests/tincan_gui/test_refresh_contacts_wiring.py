"""Tests: MainWindow.refresh_requested → TincandClient.refresh_contacts wiring (tincan-mox38).

Coverage:
  - Emitting refresh_requested calls refresh_contacts on the dbus client.
  - The connection is established during __init__ (before show()).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QSystemTrayIcon

from tincan_gui.dbus_client import TincandClient
from tincan_gui.main import MainWindow


@pytest.fixture(autouse=True)
def _no_tray_show():
    with patch.object(QSystemTrayIcon, "show"):
        yield


@pytest.fixture(autouse=True)
def _no_live_daemon(monkeypatch):
    monkeypatch.setattr(TincandClient, "get_status", lambda self: {})
    monkeypatch.setattr(TincandClient, "get_messages", lambda self, cid: [])
    monkeypatch.setattr(TincandClient, "list_conversations", lambda self: [])
    monkeypatch.setattr(TincandClient, "mark_conversation_read", lambda self, cid: None)
    monkeypatch.setattr(TincandClient, "fetch_contact_photo", lambda self, cid: None)


class TestMainWindowRefreshContactsWiring:
    """refresh_requested emits → _dbus_client.refresh_contacts() is called."""

    def test_refresh_requested_triggers_refresh_contacts(self, qtbot, monkeypatch):
        called = []
        monkeypatch.setattr(TincandClient, "refresh_contacts", lambda self: called.append(True))

        win = MainWindow()
        qtbot.addWidget(win)

        win.refresh_requested.emit()

        assert called, "refresh_contacts not called when refresh_requested was emitted"

    def test_connection_established_before_window_shown(self, qtbot, monkeypatch):
        """Signal wiring happens in __init__; show() is not required."""
        called = []
        monkeypatch.setattr(TincandClient, "refresh_contacts", lambda self: called.append(True))

        win = MainWindow()
        qtbot.addWidget(win)
        # deliberately NOT calling win.show()

        win.refresh_requested.emit()

        assert called
