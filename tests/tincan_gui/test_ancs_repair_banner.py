"""Tests: ANCSRepairBanner widget and ancs_needs_repair integration in MainWindow.
Bead: tincan-5mze.4
Updated: tincan-nbjrp (honest state model — ancs_status string)

Coverage:
  §1  ANCSRepairBanner smoke tests — instantiation, structure, accessible name
  §2  _apply_ancs_status("fallback") shows repair banner, hides StateC
  §3  _apply_ancs_status("armed"/"active") hides repair banner; StateC only during HEALING
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

    def test_minimum_height_64(self, qtbot):
        """kzgk7.5: headline+body layout requires at least 64 px."""
        banner = ANCSRepairBanner()
        qtbot.addWidget(banner)
        assert banner.minimumHeight() == 64

    def test_accessible_name_not_empty(self, qtbot):
        banner = ANCSRepairBanner()
        qtbot.addWidget(banner)
        assert banner.accessibleName() != ""

    def test_accessible_name_mentions_bluetooth(self, qtbot):
        """kzgk7.5: accessible name is the headline, not a reconnect string."""
        banner = ANCSRepairBanner()
        qtbot.addWidget(banner)
        assert "Bluetooth" in banner.accessibleName() or "bluetooth" in banner.accessibleName()


# ---------------------------------------------------------------------------
# §2 _apply_ancs_status("fallback"): shows repair banner, hides StateC
# ---------------------------------------------------------------------------

class TestApplyAncsStatusFallback:
    """ancs_status="fallback" shows ANCSRepairBanner and suppresses State C."""

    def test_fallback_shows_repair_banner(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        with patch.object(window._notifier, "dispatch_repair"):
            window._apply_ancs_status("fallback")
        assert window._banner_ancs_repair.isVisible()

    def test_fallback_hides_banner_c(self, qtbot):
        """FALLBACK → ANCSRepairBanner; StateCBanner (HEALING) must be hidden."""
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window._banner_c.show()
        with patch.object(window._notifier, "dispatch_repair"):
            window._apply_ancs_status("fallback")
        assert not window._banner_c.isVisible()

    def test_fallback_does_not_show_banner_c(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        with patch.object(window._notifier, "dispatch_repair"):
            window._apply_ancs_status("fallback")
        assert not window._banner_c.isVisible()


# ---------------------------------------------------------------------------
# §3 _apply_ancs_status("armed"/"active"): hides repair banner; StateC only in HEALING
# ---------------------------------------------------------------------------

class TestApplyAncsStatusNonFallback:
    """armed/active hides ANCSRepairBanner; StateCBanner only visible during HEALING."""

    def test_armed_hides_repair_banner(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window._banner_ancs_repair.show()
        window._apply_ancs_status("armed")
        assert not window._banner_ancs_repair.isVisible()

    def test_armed_hides_banner_c(self, qtbot):
        """ARMED (soliciting) must not show State C — that's only for HEALING."""
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window._banner_c.show()
        window._apply_ancs_status("armed")
        assert not window._banner_c.isVisible()

    def test_active_hides_banner_c(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window._banner_c.show()
        window._apply_ancs_status("active")
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

    def test_reconnect_clicked_calls_ancs_heal(self, qtbot):
        """kzgk7.5: reconnect_clicked triggers HEALING via request_ancs_heal, not the wizard."""
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        with patch.object(window._dbus_client, "request_ancs_heal") as mock_heal:
            window._banner_ancs_repair.reconnect_clicked.emit()
        mock_heal.assert_called_once()


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
            window._apply_ancs_status("fallback")
        mock_dispatch.assert_called_once()

    def test_second_fallback_suppressed_when_repair_notified(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        with patch.object(window._notifier, "dispatch_repair") as mock_dispatch:
            window._apply_ancs_status("fallback")  # first — fires
            mock_dispatch.reset_mock()
            window._apply_ancs_status("fallback")  # second — suppressed
        mock_dispatch.assert_not_called()

    def test_notification_fires_again_after_wizard_success_resets_flag(self, qtbot):
        """ancs_status="armed" resets _repair_notified; next FALLBACK fires again."""
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        with patch.object(window._notifier, "dispatch_repair") as mock_dispatch:
            window._apply_ancs_status("fallback")  # first FALLBACK
            window._apply_ancs_status("armed")     # heal success → reset
            mock_dispatch.reset_mock()
            window._apply_ancs_status("fallback")  # new FALLBACK — fires
        mock_dispatch.assert_called_once()

    def test_repair_notified_flag_set_on_first_fallback(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        assert not window._repair_notified
        with patch.object(window._notifier, "dispatch_repair"):
            window._apply_ancs_status("fallback")
        assert window._repair_notified

    def test_repair_notified_flag_cleared_on_non_fallback(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        with patch.object(window._notifier, "dispatch_repair"):
            window._apply_ancs_status("fallback")
        assert window._repair_notified
        window._apply_ancs_status("armed")
        assert not window._repair_notified
