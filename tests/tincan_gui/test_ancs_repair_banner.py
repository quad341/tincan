"""Tests: ANCSRepairBanner widget and ancs_needs_repair integration in MainWindow.
Bead: tincan-5mze.4

Coverage:
  §1  ANCSRepairBanner smoke tests — instantiation, structure, accessible name
  §2  _apply_capabilities(ancs_needs_repair=True) shows repair banner, hides StateC
  §3  _apply_capabilities(ancs_needs_repair=False) hides repair banner, restores StateC
  §4  reconnect_clicked signal fires when Reconnect button is clicked
  §5  Notification dedup — _repair_notified rate-limits repeated FALLBACK notifications
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QSystemTrayIcon

from tincan_gui.degradation_banners import ANCSRepairBanner
from tincan_gui.main import MainWindow


@pytest.fixture(autouse=True)
def _no_tray_show():
    with patch.object(QSystemTrayIcon, "show"):
        yield


# ---------------------------------------------------------------------------
# §1 ANCSRepairBanner smoke tests
# ---------------------------------------------------------------------------

class TestANCSRepairBannerSmoke:
    """ANCSRepairBanner instantiates and exposes the expected structure."""

    def test_instantiates_without_error(self, qtbot):
        banner = ANCSRepairBanner()
        qtbot.addWidget(banner)

    def test_has_reconnect_button(self, qtbot):
        banner = ANCSRepairBanner()
        qtbot.addWidget(banner)
        buttons = banner.findChildren(QPushButton)
        assert any("Reconnect" in b.text() for b in buttons)

    def test_fixed_height_56(self, qtbot):
        banner = ANCSRepairBanner()
        qtbot.addWidget(banner)
        assert banner.minimumHeight() == 56
        assert banner.maximumHeight() == 56

    def test_accessible_name_not_empty(self, qtbot):
        banner = ANCSRepairBanner()
        qtbot.addWidget(banner)
        assert banner.accessibleName() != ""

    def test_accessible_name_mentions_reconnect(self, qtbot):
        banner = ANCSRepairBanner()
        qtbot.addWidget(banner)
        assert "Reconnect" in banner.accessibleName() or "reconnect" in banner.accessibleName()


# ---------------------------------------------------------------------------
# §2 _apply_capabilities: ancs_needs_repair=True shows banner, hides StateC
# ---------------------------------------------------------------------------

class TestApplyCapabilitiesRepairBannerTrue:
    """ancs_needs_repair=True shows ANCSRepairBanner and suppresses State C."""

    def test_ancs_needs_repair_true_shows_repair_banner(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        with patch.object(window._notifier, "dispatch_repair"):
            window._apply_capabilities({"ancs_needs_repair": True})
        assert window._banner_ancs_repair.isVisible()

    def test_ancs_needs_repair_true_hides_banner_c_even_when_ancs_false(self, qtbot):
        """ANCSRepairBanner takes precedence over State C banner."""
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window._banner_c.show()
        with patch.object(window._notifier, "dispatch_repair"):
            window._apply_capabilities({"ancs": False, "ancs_needs_repair": True})
        assert not window._banner_c.isVisible()

    def test_ancs_needs_repair_true_does_not_show_banner_c(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        with patch.object(window._notifier, "dispatch_repair"):
            window._apply_capabilities({"ancs": False, "ancs_needs_repair": True})
        assert not window._banner_c.isVisible()


# ---------------------------------------------------------------------------
# §3 _apply_capabilities: ancs_needs_repair=False hides banner, restores StateC
# ---------------------------------------------------------------------------

class TestApplyCapabilitiesRepairBannerFalse:
    """ancs_needs_repair=False hides ANCSRepairBanner; StateC shows when ancs also False."""

    def test_ancs_needs_repair_false_hides_repair_banner(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window._banner_ancs_repair.show()
        window._apply_capabilities({"ancs_needs_repair": False})
        assert not window._banner_ancs_repair.isVisible()

    def test_ancs_needs_repair_false_shows_banner_c_when_ancs_false(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window._apply_capabilities({"ancs": False, "ancs_needs_repair": False})
        assert window._banner_c.isVisible()

    def test_ancs_needs_repair_false_hides_banner_c_when_ancs_true(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window._apply_capabilities({"ancs": True, "ancs_needs_repair": False})
        assert not window._banner_c.isVisible()


# ---------------------------------------------------------------------------
# §4 reconnect_clicked signal fires when Reconnect button is clicked
# ---------------------------------------------------------------------------

class TestReconnectClickedSignal:
    """Clicking the Reconnect button emits reconnect_clicked."""

    def test_reconnect_clicked_emits_signal(self, qtbot):
        banner = ANCSRepairBanner()
        qtbot.addWidget(banner)
        banner.show()

        received = []
        banner.reconnect_clicked.connect(lambda: received.append(True))

        btn = next(b for b in banner.findChildren(QPushButton) if "Reconnect" in b.text())
        qtbot.mouseClick(btn, Qt.LeftButton)

        assert received

    def test_reconnect_clicked_connected_to_open_pairing_wizard(self, qtbot):
        """In MainWindow, reconnect_clicked opens the pairing wizard."""
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        with patch.object(window, "_open_pairing_wizard") as mock_wizard:
            window._banner_ancs_repair.reconnect_clicked.emit()
        mock_wizard.assert_called_once()


# ---------------------------------------------------------------------------
# §5 Notification dedup — _repair_notified rate-limits repeated FALLBACK notifications
# ---------------------------------------------------------------------------

class TestRepairNotificationDedup:
    """dispatch_repair fires once on first FALLBACK; suppressed until wizard resets flag."""

    def test_first_fallback_fires_notification(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        with patch.object(window._notifier, "dispatch_repair") as mock_dispatch:
            window._apply_capabilities({"ancs_needs_repair": True})
        mock_dispatch.assert_called_once()

    def test_second_fallback_suppressed_when_repair_notified(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        with patch.object(window._notifier, "dispatch_repair") as mock_dispatch:
            window._apply_capabilities({"ancs_needs_repair": True})  # first — fires
            mock_dispatch.reset_mock()
            window._apply_capabilities({"ancs_needs_repair": True})  # second — suppressed
        mock_dispatch.assert_not_called()

    def test_notification_fires_again_after_wizard_success_resets_flag(self, qtbot):
        """ancs_needs_repair=False resets _repair_notified; next FALLBACK fires again."""
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        with patch.object(window._notifier, "dispatch_repair") as mock_dispatch:
            window._apply_capabilities({"ancs_needs_repair": True})   # first FALLBACK
            window._apply_capabilities({"ancs_needs_repair": False})  # wizard success → reset
            mock_dispatch.reset_mock()
            window._apply_capabilities({"ancs_needs_repair": True})   # new FALLBACK — fires
        mock_dispatch.assert_called_once()

    def test_repair_notified_flag_set_on_first_fallback(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        assert not window._repair_notified
        with patch.object(window._notifier, "dispatch_repair"):
            window._apply_capabilities({"ancs_needs_repair": True})
        assert window._repair_notified

    def test_repair_notified_flag_cleared_on_wizard_success(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        with patch.object(window._notifier, "dispatch_repair"):
            window._apply_capabilities({"ancs_needs_repair": True})
        assert window._repair_notified
        window._apply_capabilities({"ancs_needs_repair": False})
        assert not window._repair_notified
