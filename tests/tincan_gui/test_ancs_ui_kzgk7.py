"""Tests: ANCSStatusDot and ANCSRepairBanner UI widgets (tincan-kzgk7.7).

Coverage:
  §1  ANCSStatusDot — ACTIVE state (ancs=True): visible, green, static, tooltip
  §2  ANCSStatusDot — HEALING state: visible, amber, pulse starts, tooltip
  §3  ANCSStatusDot — FALLBACK state (ancs_needs_repair=True): hidden
  §4  ANCSStatusDot — ARMED state (neither capability set yet): hidden at init
  §5  ANCSStatusDot — reduced-motion: no pulse when system prefers reduced animations
  §6  ANCSRepairBanner — visibility lifecycle via _apply_capabilities
  §7  ANCSRepairBanner — set_reconnecting() button state transitions (kzgk7.5)
  §8  MainWindow — _apply_capabilities drives dot via _title_bar.ancs_status_dot
  §9  MainWindow — _on_daemon_disconnected hides dot
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QSystemTrayIcon

from tincan_gui.ancs_status_dot import ANCSStatusDot
from tincan_gui.degradation_banners import ANCSRepairBanner
from tincan_gui.main import MainWindow


@pytest.fixture(autouse=True)
def _no_tray_show():
    with patch.object(QSystemTrayIcon, "show"):
        yield


# ---------------------------------------------------------------------------
# §1 ANCSStatusDot — ACTIVE state
# ---------------------------------------------------------------------------

class TestANCSStatusDotActive:
    """ancs=True → dot is visible, green, static, tooltip correct."""

    def test_active_dot_is_visible(self, qtbot):
        dot = ANCSStatusDot()
        qtbot.addWidget(dot)
        dot.update_state(ancs=True, ancs_needs_repair=False)
        assert dot.isVisible()

    def test_active_dot_is_green(self, qtbot):
        dot = ANCSStatusDot()
        qtbot.addWidget(dot)
        dot.update_state(ancs=True, ancs_needs_repair=False)
        assert dot._color.name() == "#22c55e"

    def test_active_dot_no_pulse_animation(self, qtbot):
        dot = ANCSStatusDot()
        qtbot.addWidget(dot)
        dot.update_state(ancs=True, ancs_needs_repair=False)
        assert dot._anim is None

    def test_active_dot_tooltip(self, qtbot):
        dot = ANCSStatusDot()
        qtbot.addWidget(dot)
        dot.update_state(ancs=True, ancs_needs_repair=False)
        assert dot.toolTip() == "Bluetooth notifications"

    def test_active_dot_accessible_name(self, qtbot):
        dot = ANCSStatusDot()
        qtbot.addWidget(dot)
        dot.update_state(ancs=True, ancs_needs_repair=False)
        name = dot.accessibleName()
        assert "active" in name.lower() or "Notifications" in name


# ---------------------------------------------------------------------------
# §2 ANCSStatusDot — HEALING state
# ---------------------------------------------------------------------------

class TestANCSStatusDotHealing:
    """ancs=False, ancs_needs_repair=False → visible, amber, pulse optional, tooltip."""

    def test_healing_dot_is_visible(self, qtbot):
        dot = ANCSStatusDot()
        qtbot.addWidget(dot)
        dot.update_state(ancs=False, ancs_needs_repair=False)
        assert dot.isVisible()

    def test_healing_dot_is_amber(self, qtbot):
        dot = ANCSStatusDot()
        qtbot.addWidget(dot)
        dot.update_state(ancs=False, ancs_needs_repair=False)
        assert dot._color.name() == "#d97706"

    def test_healing_dot_starts_pulse_when_not_reduced_motion(self, qtbot):
        dot = ANCSStatusDot()
        qtbot.addWidget(dot)
        with patch.object(dot, "_reduced_motion", return_value=False):
            dot.update_state(ancs=False, ancs_needs_repair=False)
        assert dot._anim is not None

    def test_healing_dot_tooltip(self, qtbot):
        dot = ANCSStatusDot()
        qtbot.addWidget(dot)
        dot.update_state(ancs=False, ancs_needs_repair=False)
        assert dot.toolTip() == "Reconnecting..."

    def test_healing_dot_accessible_name(self, qtbot):
        dot = ANCSStatusDot()
        qtbot.addWidget(dot)
        dot.update_state(ancs=False, ancs_needs_repair=False)
        assert "reconnect" in dot.accessibleName().lower()


# ---------------------------------------------------------------------------
# §3 ANCSStatusDot — FALLBACK state
# ---------------------------------------------------------------------------

class TestANCSStatusDotFallback:
    """ancs=False, ancs_needs_repair=True → dot is NOT visible."""

    def test_fallback_dot_is_hidden(self, qtbot):
        dot = ANCSStatusDot()
        qtbot.addWidget(dot)
        dot.update_state(ancs=False, ancs_needs_repair=True)
        assert not dot.isVisible()

    def test_fallback_stops_prior_pulse(self, qtbot):
        """Transitioning from HEALING to FALLBACK stops the animation."""
        dot = ANCSStatusDot()
        qtbot.addWidget(dot)
        with patch.object(dot, "_reduced_motion", return_value=False):
            dot.update_state(ancs=False, ancs_needs_repair=False)  # HEALING → pulse
        dot.update_state(ancs=False, ancs_needs_repair=True)  # FALLBACK
        assert dot._anim is None

    def test_transition_active_to_fallback_hides_dot(self, qtbot):
        """Going ACTIVE → FALLBACK hides a previously visible dot."""
        dot = ANCSStatusDot()
        qtbot.addWidget(dot)
        dot.update_state(ancs=True, ancs_needs_repair=False)
        dot.update_state(ancs=False, ancs_needs_repair=True)
        assert not dot.isVisible()


# ---------------------------------------------------------------------------
# §4 ANCSStatusDot — ARMED state (not yet initialized / before first cap event)
# ---------------------------------------------------------------------------

class TestANCSStatusDotArmed:
    """Dot is hidden at init before any capability event arrives."""

    def test_dot_hidden_at_init(self, qtbot):
        dot = ANCSStatusDot()
        qtbot.addWidget(dot)
        assert not dot.isVisible()

    def test_dot_excluded_from_tab_order(self, qtbot):
        """FocusPolicy=NoFocus keeps the dot out of the keyboard tab sequence."""
        dot = ANCSStatusDot()
        qtbot.addWidget(dot)
        assert dot.focusPolicy() == Qt.NoFocus


# ---------------------------------------------------------------------------
# §5 ANCSStatusDot — reduced-motion
# ---------------------------------------------------------------------------

class TestANCSStatusDotReducedMotion:
    """When system prefers reduced animations, HEALING dot is static (no pulse)."""

    def test_no_pulse_when_reduced_motion(self, qtbot):
        dot = ANCSStatusDot()
        qtbot.addWidget(dot)
        with patch.object(dot, "_reduced_motion", return_value=True):
            dot.update_state(ancs=False, ancs_needs_repair=False)
        assert dot._anim is None

    def test_still_visible_and_amber_with_reduced_motion(self, qtbot):
        """Reduced-motion suppresses animation but not visibility or color."""
        dot = ANCSStatusDot()
        qtbot.addWidget(dot)
        with patch.object(dot, "_reduced_motion", return_value=True):
            dot.update_state(ancs=False, ancs_needs_repair=False)
        assert dot.isVisible()
        assert dot._color.name() == "#d97706"


# ---------------------------------------------------------------------------
# §6 ANCSRepairBanner — visibility lifecycle
# ---------------------------------------------------------------------------

class TestANCSRepairBannerVisibility:
    """Banner hidden on init; shows/hides correctly via _apply_capabilities."""

    def test_banner_hidden_on_init(self, qtbot):
        banner = ANCSRepairBanner()
        qtbot.addWidget(banner)
        assert not banner.isVisible()

    def test_banner_shows_on_ancs_needs_repair_true(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        with patch.object(window._notifier, "dispatch_repair"):
            window._apply_capabilities({"ancs_needs_repair": True})
        assert window._banner_ancs_repair.isVisible()

    def test_banner_hides_when_active_restored(self, qtbot):
        """ancs=True (ACTIVE restored) hides the FALLBACK banner."""
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        with patch.object(window._notifier, "dispatch_repair"):
            window._apply_capabilities({"ancs_needs_repair": True})
        window._apply_capabilities({"ancs": True, "ancs_needs_repair": False})
        assert not window._banner_ancs_repair.isVisible()

    def test_banner_hides_when_healing_entered(self, qtbot):
        """HEALING state (ancs=False, repair=False) hides the banner."""
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        with patch.object(window._notifier, "dispatch_repair"):
            window._apply_capabilities({"ancs_needs_repair": True})
        window._apply_capabilities({"ancs": False, "ancs_needs_repair": False})
        assert not window._banner_ancs_repair.isVisible()

    def test_banner_headline_text(self, qtbot):
        """Banner contains the required headline text."""
        from PySide6.QtWidgets import QLabel
        banner = ANCSRepairBanner()
        qtbot.addWidget(banner)
        texts = [label.text() for label in banner.findChildren(QLabel)]
        assert any("Bluetooth notifications unavailable" in t for t in texts)


# ---------------------------------------------------------------------------
# §7 ANCSRepairBanner — set_reconnecting() button state transitions
# ---------------------------------------------------------------------------

class TestANCSRepairBannerReconnecting:
    """set_reconnecting(True) disables button with busy label; False restores idle."""

    def test_button_label_idle_on_init(self, qtbot):
        banner = ANCSRepairBanner()
        qtbot.addWidget(banner)
        assert "Try to Reconnect" in banner._reconnect_btn.text()

    def test_set_reconnecting_true_changes_label(self, qtbot):
        banner = ANCSRepairBanner()
        qtbot.addWidget(banner)
        banner.set_reconnecting(True)
        assert "Reconnecting" in banner._reconnect_btn.text()

    def test_set_reconnecting_true_disables_button(self, qtbot):
        banner = ANCSRepairBanner()
        qtbot.addWidget(banner)
        banner.set_reconnecting(True)
        assert not banner._reconnect_btn.isEnabled()

    def test_set_reconnecting_false_restores_idle_label(self, qtbot):
        banner = ANCSRepairBanner()
        qtbot.addWidget(banner)
        banner.set_reconnecting(True)
        banner.set_reconnecting(False)
        assert "Try to Reconnect" in banner._reconnect_btn.text()

    def test_set_reconnecting_false_re_enables_button(self, qtbot):
        banner = ANCSRepairBanner()
        qtbot.addWidget(banner)
        banner.set_reconnecting(True)
        banner.set_reconnecting(False)
        assert banner._reconnect_btn.isEnabled()

    def test_reconnect_click_calls_request_ancs_heal(self, qtbot):
        """kzgk7.5: clicking "Try to Reconnect" fires request_ancs_heal(), not the wizard."""
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        with patch.object(window._dbus_client, "request_ancs_heal") as mock_heal:
            window._banner_ancs_repair.reconnect_clicked.emit()
        mock_heal.assert_called_once()

    def test_reconnect_click_sets_banner_to_reconnecting(self, qtbot):
        """Click immediately puts the button into busy state."""
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        with patch.object(window._dbus_client, "request_ancs_heal"):
            window._banner_ancs_repair.reconnect_clicked.emit()
        assert not window._banner_ancs_repair._reconnect_btn.isEnabled()
        assert "Reconnecting" in window._banner_ancs_repair._reconnect_btn.text()

    def test_button_reverts_on_second_fallback(self, qtbot):
        """Full FALLBACK→click→HEALING-entered→HEALING-failed flow reverts button.

        The banner is hidden during HEALING (repair=False), which resets the button
        to idle via set_reconnecting(False). When FALLBACK re-enters, the button is
        already idle ('Try to Reconnect', enabled).
        """
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()

        # Step 1: FALLBACK entry — banner shows
        with patch.object(window._notifier, "dispatch_repair"):
            window._apply_capabilities({"ancs_needs_repair": True})

        # Step 2: user clicks → banner enters reconnecting state
        with patch.object(window._dbus_client, "request_ancs_heal"):
            window._banner_ancs_repair.reconnect_clicked.emit()

        # Step 3: HEALING entered → banner hides and button resets (repair=False path)
        window._apply_capabilities({"ancs": False, "ancs_needs_repair": False})

        # Step 4: HEALING failed → second FALLBACK
        with patch.object(window._notifier, "dispatch_repair"):
            window._apply_capabilities({"ancs_needs_repair": True})

        assert window._banner_ancs_repair._reconnect_btn.isEnabled()
        assert "Try to Reconnect" in window._banner_ancs_repair._reconnect_btn.text()


# ---------------------------------------------------------------------------
# §8 MainWindow — _apply_capabilities drives dot via _title_bar
# ---------------------------------------------------------------------------

class TestMainWindowAncsDotWiring:
    """_apply_capabilities routes ancs/ancs_needs_repair to ANCSStatusDot."""

    def test_apply_caps_active_shows_dot(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window._apply_capabilities({"ancs": True, "ancs_needs_repair": False})
        assert window._title_bar.ancs_status_dot.isVisible()

    def test_apply_caps_active_dot_is_green(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window._apply_capabilities({"ancs": True, "ancs_needs_repair": False})
        assert window._title_bar.ancs_status_dot._color.name() == "#22c55e"

    def test_apply_caps_healing_shows_dot(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window._apply_capabilities({"ancs": False, "ancs_needs_repair": False})
        assert window._title_bar.ancs_status_dot.isVisible()

    def test_apply_caps_healing_dot_is_amber(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window._apply_capabilities({"ancs": False, "ancs_needs_repair": False})
        assert window._title_bar.ancs_status_dot._color.name() == "#d97706"

    def test_apply_caps_fallback_hides_dot(self, qtbot):
        """FALLBACK (repair=True) hides the dot; ANCSRepairBanner takes over."""
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window._apply_capabilities({"ancs": True, "ancs_needs_repair": False})  # ACTIVE first
        with patch.object(window._notifier, "dispatch_repair"):
            window._apply_capabilities({"ancs": False, "ancs_needs_repair": True})
        assert not window._title_bar.ancs_status_dot.isVisible()


# ---------------------------------------------------------------------------
# §9 MainWindow — _on_daemon_disconnected hides dot
# ---------------------------------------------------------------------------

class TestMainWindowDotOnDisconnect:
    """_on_daemon_disconnected hides the ANCS status dot."""

    def test_dot_hidden_after_daemon_disconnect(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window._apply_capabilities({"ancs": True, "ancs_needs_repair": False})
        assert window._title_bar.ancs_status_dot.isVisible()
        window._on_daemon_disconnected()
        assert not window._title_bar.ancs_status_dot.isVisible()
