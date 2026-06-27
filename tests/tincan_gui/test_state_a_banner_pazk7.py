"""Behavioral tests: StateABanner set_reason + set_reconnecting + _had_connection_this_session.
Bead: tincan-pazk7 (FR-A2+A3)

Coverage:
  §1 set_reason("NEUTRAL") — label / sub_label / reconnect_btn copy
  §2 set_reason("OUT_OF_RANGE") — label / sub_label / reconnect_btn copy
  §3 set_reconnecting(True) — button disabled, busy copy, sub_label, stylesheet, timer active
  §4 set_reconnecting(False) — restores idle state via set_reason(current_reason)
  §5 timer auto-reset — timeout signal fires set_reconnecting(False) → button re-enabled
  §6 _had_connection_this_session — NEUTRAL before first connect, OUT_OF_RANGE after connect

All tests mock TincandClient — no real D-Bus required.
Run with: python -m pytest tests/tincan_gui/test_state_a_banner_pazk7.py -v
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QSystemTrayIcon

from tincan_gui.dbus_client import TincandClient
from tincan_gui.degradation_banners import StateABanner
from tincan_gui.main import MainWindow


@pytest.fixture(autouse=True)
def _no_tray_show():
    with patch.object(QSystemTrayIcon, "show"):
        yield


@pytest.fixture(autouse=True)
def _no_list_conversations(monkeypatch):
    monkeypatch.setattr(TincandClient, "list_conversations", lambda self: [])


# ---------------------------------------------------------------------------
# §1 set_reason("NEUTRAL") copy
# ---------------------------------------------------------------------------

class TestSetReasonNeutral:
    """NEUTRAL: first-launch copy — user has not yet paired any device."""

    @pytest.fixture(autouse=True)
    def _banner(self, qtbot):
        self.banner = StateABanner()
        qtbot.addWidget(self.banner)
        self.banner.set_reason("NEUTRAL")

    def test_label_mentions_not_connected(self):
        text = self.banner._label.text().lower()
        assert "not connected" in text, (
            f"NEUTRAL label must say 'not connected'; got {self.banner._label.text()!r}"
        )

    def test_sub_label_guides_to_settings(self):
        text = self.banner._sub_label.text().lower()
        assert "settings" in text, (
            f"NEUTRAL sub_label must reference Settings; got {self.banner._sub_label.text()!r}"
        )

    def test_reconnect_btn_says_connect_device(self):
        text = self.banner._reconnect_btn.text().lower()
        assert "connect" in text and "device" in text, (
            f"NEUTRAL button must say 'Connect device'; got {self.banner._reconnect_btn.text()!r}"
        )

    def test_reconnect_btn_is_enabled(self):
        assert self.banner._reconnect_btn.isEnabled(), (
            "NEUTRAL reconnect button must be enabled"
        )

    def test_timer_stopped_after_set_reason(self):
        assert not self.banner._reconnect_timer.isActive(), (
            "set_reason must stop any running timer"
        )


# ---------------------------------------------------------------------------
# §2 set_reason("OUT_OF_RANGE") copy
# ---------------------------------------------------------------------------

class TestSetReasonOutOfRange:
    """OUT_OF_RANGE: post-connect disconnect copy — device was in range then moved away."""

    @pytest.fixture(autouse=True)
    def _banner(self, qtbot):
        self.banner = StateABanner()
        qtbot.addWidget(self.banner)
        self.banner.set_reason("OUT_OF_RANGE")

    def test_label_mentions_connection_lost(self):
        text = self.banner._label.text().lower()
        assert "connection lost" in text, (
            f"OUT_OF_RANGE label must say 'connection lost'; got {self.banner._label.text()!r}"
        )

    def test_sub_label_mentions_bluetooth_range(self):
        text = self.banner._sub_label.text().lower()
        assert "closer" in text or "range" in text or "iphone" in text, (
            f"OUT_OF_RANGE sub_label must reference bringing device closer; "
            f"got {self.banner._sub_label.text()!r}"
        )

    def test_reconnect_btn_says_reconnect(self):
        text = self.banner._reconnect_btn.text().lower()
        assert "reconnect" in text, (
            f"OUT_OF_RANGE button must say 'Reconnect'; got {self.banner._reconnect_btn.text()!r}"
        )

    def test_reconnect_btn_is_enabled(self):
        assert self.banner._reconnect_btn.isEnabled(), (
            "OUT_OF_RANGE reconnect button must be enabled"
        )

    def test_timer_stopped_after_set_reason(self):
        assert not self.banner._reconnect_timer.isActive(), (
            "set_reason must stop any running timer"
        )

    def test_neutral_and_out_of_range_labels_differ(self, qtbot):
        neutral = StateABanner()
        qtbot.addWidget(neutral)
        neutral.set_reason("NEUTRAL")
        assert self.banner._label.text() != neutral._label.text(), (
            "NEUTRAL and OUT_OF_RANGE must show distinct label copy"
        )

    def test_neutral_and_out_of_range_buttons_differ(self, qtbot):
        neutral = StateABanner()
        qtbot.addWidget(neutral)
        neutral.set_reason("NEUTRAL")
        assert self.banner._reconnect_btn.text() != neutral._reconnect_btn.text(), (
            "NEUTRAL and OUT_OF_RANGE must show distinct button copy"
        )


# ---------------------------------------------------------------------------
# §3 set_reconnecting(True) — busy state
# ---------------------------------------------------------------------------

class TestSetReconnectingTrue:
    """set_reconnecting(True) must indicate progress and prevent duplicate triggers."""

    @pytest.fixture(autouse=True)
    def _banner(self, qtbot):
        self.banner = StateABanner()
        qtbot.addWidget(self.banner)
        self.banner.set_reason("OUT_OF_RANGE")
        self.banner.set_reconnecting(True)

    def test_button_is_disabled(self):
        assert not self.banner._reconnect_btn.isEnabled(), (
            "Button must be disabled while reconnecting"
        )

    def test_button_text_indicates_progress(self):
        text = self.banner._reconnect_btn.text().lower()
        assert "reconnecting" in text, (
            f"Button must say 'Reconnecting…' while busy;"
            f" got {self.banner._reconnect_btn.text()!r}"
        )

    def test_sub_label_indicates_please_wait(self):
        text = self.banner._sub_label.text().lower()
        assert "wait" in text or "please" in text, (
            f"Sub-label must indicate please wait while reconnecting; "
            f"got {self.banner._sub_label.text()!r}"
        )

    def test_timer_is_active(self):
        assert self.banner._reconnect_timer.isActive(), (
            "10s auto-reset timer must be started by set_reconnecting(True)"
        )

    def test_timer_stopped_when_reconnecting_called_again(self, qtbot):
        """Calling set_reconnecting(True) twice must restart (not stack) the timer."""
        self.banner.set_reconnecting(True)
        assert self.banner._reconnect_timer.isActive(), (
            "Timer must still be active after a second set_reconnecting(True) call"
        )


# ---------------------------------------------------------------------------
# §4 set_reconnecting(False) — restores idle state
# ---------------------------------------------------------------------------

class TestSetReconnectingFalse:
    """set_reconnecting(False) must restore the idle state based on current_reason."""

    def test_restores_neutral_state(self, qtbot):
        banner = StateABanner()
        qtbot.addWidget(banner)
        banner.set_reason("NEUTRAL")
        banner.set_reconnecting(True)
        banner.set_reconnecting(False)
        assert banner._reconnect_btn.isEnabled(), (
            "Button must be re-enabled after set_reconnecting(False)"
        )
        text = banner._reconnect_btn.text().lower()
        assert "connect" in text and "device" in text, (
            f"NEUTRAL button text must be restored; got {banner._reconnect_btn.text()!r}"
        )

    def test_restores_out_of_range_state(self, qtbot):
        banner = StateABanner()
        qtbot.addWidget(banner)
        banner.set_reason("OUT_OF_RANGE")
        banner.set_reconnecting(True)
        banner.set_reconnecting(False)
        assert banner._reconnect_btn.isEnabled(), (
            "Button must be re-enabled after set_reconnecting(False)"
        )
        text = banner._reconnect_btn.text().lower()
        assert "reconnect" in text, (
            f"OUT_OF_RANGE button text must be restored; got {banner._reconnect_btn.text()!r}"
        )

    def test_timer_stopped_after_false(self, qtbot):
        banner = StateABanner()
        qtbot.addWidget(banner)
        banner.set_reconnecting(True)
        banner.set_reconnecting(False)
        assert not banner._reconnect_timer.isActive(), (
            "Timer must be stopped after set_reconnecting(False)"
        )


# ---------------------------------------------------------------------------
# §5 timer auto-reset — timeout fires set_reconnecting(False)
# ---------------------------------------------------------------------------

class TestTimerAutoReset:
    """After 10s the timer fires and restores the idle state automatically."""

    def test_timeout_signal_re_enables_button(self, qtbot):
        """Simulate timer expiry by emitting timeout directly."""
        banner = StateABanner()
        qtbot.addWidget(banner)
        banner.set_reason("OUT_OF_RANGE")
        banner.set_reconnecting(True)
        assert not banner._reconnect_btn.isEnabled(), "Pre-condition: button must be disabled"

        banner._reconnect_timer.timeout.emit()

        assert banner._reconnect_btn.isEnabled(), (
            "Button must be re-enabled when the 10s timer fires"
        )

    def test_timeout_signal_restores_button_text(self, qtbot):
        banner = StateABanner()
        qtbot.addWidget(banner)
        banner.set_reason("OUT_OF_RANGE")
        banner.set_reconnecting(True)

        banner._reconnect_timer.timeout.emit()

        text = banner._reconnect_btn.text().lower()
        assert "reconnect" in text and "…" not in banner._reconnect_btn.text(), (
            f"Button text must revert from 'Reconnecting…' after timeout; "
            f"got {banner._reconnect_btn.text()!r}"
        )

    def test_timeout_stops_timer(self, qtbot):
        banner = StateABanner()
        qtbot.addWidget(banner)
        banner.set_reconnecting(True)

        banner._reconnect_timer.timeout.emit()

        assert not banner._reconnect_timer.isActive(), (
            "Timer must not be active after timeout fires"
        )


# ---------------------------------------------------------------------------
# §6 _had_connection_this_session — NEUTRAL before first connect, OUT_OF_RANGE after
# ---------------------------------------------------------------------------

class TestHadConnectionThisSession:
    """_had_connection_this_session controls which reason the banner shows at disconnect."""

    def test_neutral_reason_before_any_connection(self, qtbot, monkeypatch):
        """First disconnect (no prior connection) must show NEUTRAL copy."""
        monkeypatch.setattr(TincandClient, "get_status", lambda self: {"connected": False})
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()

        assert not window._had_connection_this_session, (
            "_had_connection_this_session must be False before any connection"
        )
        text = window._banner_a._label.text().lower()
        assert "not connected" in text, (
            f"First-launch disconnect must show NEUTRAL ('not connected'); got {text!r}"
        )

    def test_out_of_range_reason_after_connection(self, qtbot, monkeypatch):
        """Disconnect after an established connection must show OUT_OF_RANGE copy."""
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

        window._on_daemon_connected("AA:BB:CC:DD:EE:FF")
        assert window._had_connection_this_session, (
            "_had_connection_this_session must be True after _on_daemon_connected"
        )

        window._on_daemon_disconnected()
        text = window._banner_a._label.text().lower()
        assert "connection lost" in text, (
            f"Post-connect disconnect must show OUT_OF_RANGE ('connection lost'); got {text!r}"
        )

    def test_flag_remains_true_after_reconnect_cycle(self, qtbot, monkeypatch):
        """_had_connection_this_session stays True across connect/disconnect cycles."""
        monkeypatch.setattr(TincandClient, "get_status", lambda self: {"connected": False})
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()

        window._on_daemon_connected("AA:BB:CC:DD:EE:FF")
        window._on_daemon_disconnected()
        window._on_daemon_connected("AA:BB:CC:DD:EE:FF")
        window._on_daemon_disconnected()

        assert window._had_connection_this_session, (
            "_had_connection_this_session must stay True across reconnect cycles"
        )
        text = window._banner_a._label.text().lower()
        assert "connection lost" in text, (
            f"Second disconnect must still show OUT_OF_RANGE; got {text!r}"
        )
