"""Behavior tests: BT-disconnected state must be visually obvious (tincan-w0bdi).

The disconnect banner (StateABanner) must be shown whenever the GUI knows
the phone is not connected — including on cold start, not only on an explicit
disconnect signal.  The title-bar chip ("○ Disconnected") is too subtle; the
banner is the unmistakable indicator.

Coverage:
  - Cold start with connected=False → banner_a visible immediately.
  - Cold start with connected=True → banner_a hidden.
  - _on_daemon_disconnected signal → banner_a becomes visible.
  - _on_daemon_connected signal → banner_a cleared.
  - Banner label uses a legible font size (≥11pt).
  - Banner text contains the key message ("Connection lost" or "reconnecting").
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
def _no_list_conversations(monkeypatch):
    monkeypatch.setattr(TincandClient, "list_conversations", lambda self: [])


class TestBTDisconnectBannerOnStartup:
    """Cold-start: banner_a reflects daemon's reported connected state (tincan-w0bdi)."""

    def test_banner_shown_on_startup_when_phone_not_connected(self, qtbot, monkeypatch):
        """If daemon says connected=False at startup, banner_a must be visible."""
        monkeypatch.setattr(
            TincandClient, "get_status", lambda self: {"connected": False}
        )
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        assert window._banner_a.isVisible(), (
            "Disconnect banner must be visible on startup when phone is not connected"
        )

    def test_banner_hidden_on_startup_when_connected(self, qtbot, monkeypatch):
        """Connected at startup → banner_a must stay hidden."""
        monkeypatch.setattr(
            TincandClient,
            "get_status",
            lambda self: {
                "connected": True,
                "device_name": "iPhone",
                "capabilities": {},
            },
        )
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        assert not window._banner_a.isVisible()

    def test_banner_hidden_when_daemon_not_available(self, qtbot, monkeypatch):
        """No daemon response at startup → banner_a stays hidden (daemon is starting)."""
        monkeypatch.setattr(TincandClient, "get_status", lambda self: {})
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        assert not window._banner_a.isVisible()


class TestBTDisconnectBannerOnSignals:
    """Signal-driven transitions clear / restore the banner (tincan-w0bdi)."""

    def test_disconnect_signal_shows_banner(self, qtbot, monkeypatch):
        """_on_daemon_disconnected → banner_a becomes visible."""
        monkeypatch.setattr(
            TincandClient,
            "get_status",
            lambda self: {
                "connected": True,
                "device_name": "iPhone",
                "capabilities": {},
            },
        )
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()

        window._on_daemon_disconnected()
        assert window._banner_a.isVisible()

    def test_reconnect_signal_hides_banner(self, qtbot, monkeypatch):
        """_on_daemon_connected after a disconnect → banner_a cleared."""
        monkeypatch.setattr(
            TincandClient, "get_status", lambda self: {"connected": False}
        )
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        assert window._banner_a.isVisible()

        monkeypatch.setattr(
            TincandClient,
            "get_status",
            lambda self: {
                "connected": True,
                "device_name": "iPhone",
                "capabilities": {},
            },
        )
        window._on_daemon_connected("AA:BB:CC:DD:EE:FF")
        assert not window._banner_a.isVisible()


class TestBTDisconnectBannerPresentation:
    """Banner must be unmistakable — legible font, meaningful text (tincan-w0bdi)."""

    @pytest.fixture(autouse=True)
    def _disconnected_window(self, qtbot, monkeypatch):
        monkeypatch.setattr(
            TincandClient, "get_status", lambda self: {"connected": False}
        )
        self.window = MainWindow()
        qtbot.addWidget(self.window)
        self.window.show()

    def test_banner_label_font_size_is_legible(self):
        """Banner label must use ≥11pt font — default system 9pt is too small."""
        label = self.window._banner_a._label
        size = label.font().pointSize()
        assert size >= 11, (
            f"Banner label is {size}pt — must be ≥11pt to be unmistakable"
        )

    def test_banner_text_mentions_connection_loss(self):
        """Banner must communicate that the connection is lost."""
        label = self.window._banner_a._label
        text = label.text().lower()
        assert (
            "connection" in text or "connected" in text
            or "reconnect" in text or "bluetooth" in text
        ), (
            f"Banner text must reference the connection: got {label.text()!r}"
        )
