"""Tests: call_link_ready wiring in _apply_capabilities / _sync_call_state (tincan-piiml).

Bead: tincan-piiml (tests) — blocked-by tincan-uuia9 (build), parent tincan-bhij3.
Source: tincan_gui/main.py _apply_capabilities / _sync_call_state / _on_daemon_disconnected,
tincan_gui/thread_view.py ThreadHeader.set_call_button.

call_link_ready reflects the live SCO/audio link state (whether CallController
currently has a bound VoiceCallManager), distinct from the static
call_setup_ready (HFP SELinux module presence only). Both the title-bar Dial
button and the per-thread Call button must gate on it, defaulting
conservatively to False when the key is absent — the opposite direction from
call_setup_ready's default-True.

Covered cases (acceptance criteria on tincan-piiml):
  §1 call_link_ready=False -> both buttons disabled, tooltip + accessibleDescription
     set to the link-not-ready copy
  §2 absent key defaults to False (opposite direction from call_setup_ready)
  §3 _on_daemon_disconnected resets the flag and disables both buttons
  §4 precedence: call_setup_ready=False wins over call_link_ready=False
  §5 (woven through §1/§4) assert setAccessibleDescription() return values directly,
     not just isEnabled()/tooltip
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QSystemTrayIcon

from tincan_gui.main import MainWindow

_SETUP_TOOLTIP = "Call setup incomplete — load the tincan HFP SELinux module to enable calls."
_LINK_TOOLTIP = "Call link not ready — make sure your iPhone is nearby with Bluetooth on."


@pytest.fixture(autouse=True)
def _no_tray_show():
    """Suppress the system tray icon popup that would error in headless CI."""
    with patch.object(QSystemTrayIcon, "show"):
        yield


@pytest.fixture()
def window(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    return w


def _make_callable_context(win: MainWindow) -> None:
    """Give the window an active 1:1 conversation so the thread-header call
    button participates in _sync_call_state (visible, not hidden)."""
    win._current_phone = "+15551234567"
    win._current_phone_dialable = True
    win._current_is_group = False
    win._current_contact_name = "Alice"


# ---------------------------------------------------------------------------
# §1 + §5 _apply_capabilities({"call_link_ready": False}) — disabled state, copy + a11y
# ---------------------------------------------------------------------------

class TestApplyCapabilitiesCallLinkReadyDisabled:
    """call_link_ready=False disables both call affordances with the link-not-ready copy."""

    def test_dial_button_disabled(self, window):
        _make_callable_context(window)
        window._apply_capabilities({"call_link_ready": False})

        assert not window._title_bar.dial_button.isEnabled()

    def test_dial_button_tooltip_is_link_copy(self, window):
        _make_callable_context(window)
        window._apply_capabilities({"call_link_ready": False})

        assert window._title_bar.dial_button.toolTip() == _LINK_TOOLTIP

    def test_dial_button_accessible_description_is_link_copy(self, window):
        _make_callable_context(window)
        window._apply_capabilities({"call_link_ready": False})

        assert window._title_bar.dial_button.accessibleDescription() == _LINK_TOOLTIP

    def test_thread_header_call_button_disabled(self, window):
        _make_callable_context(window)
        window._apply_capabilities({"call_link_ready": False})

        assert not window._thread_view._header._call_btn.isEnabled()

    def test_thread_header_call_button_tooltip_is_link_copy(self, window):
        _make_callable_context(window)
        window._apply_capabilities({"call_link_ready": False})

        assert window._thread_view._header._call_btn.toolTip() == _LINK_TOOLTIP

    def test_thread_header_call_button_accessible_description_is_link_copy(self, window):
        _make_callable_context(window)
        window._apply_capabilities({"call_link_ready": False})

        desc = window._thread_view._header._call_btn.accessibleDescription()
        assert desc == _LINK_TOOLTIP


# ---------------------------------------------------------------------------
# §2 _apply_capabilities({}) — call_link_ready key fully absent
# ---------------------------------------------------------------------------

class TestApplyCapabilitiesCallLinkReadyDefault:
    """call_link_ready defaults to False when absent — opposite of call_setup_ready's default-True."""

    def test_absent_key_defaults_to_false(self, window):
        # Force a prior ready state first so a pass here proves the value is
        # re-derived from the dict, not just coincidentally left over from
        # MainWindow.__init__'s own False default.
        window._call_link_ready = True

        window._apply_capabilities({})

        assert window._call_link_ready is False

    def test_absent_key_disables_dial_button(self, window):
        window._apply_capabilities({"call_link_ready": True})
        assert window._title_bar.dial_button.isEnabled()  # sanity: starts enabled

        window._apply_capabilities({})

        assert not window._title_bar.dial_button.isEnabled()


# ---------------------------------------------------------------------------
# §3 _on_daemon_disconnected — resets call_link_ready and re-syncs button state
# ---------------------------------------------------------------------------

class TestOnDaemonDisconnectedResetsCallLinkReady:
    """_on_daemon_disconnected resets call_link_ready to False and disables both buttons."""

    def test_flag_reset_to_false(self, window):
        _make_callable_context(window)
        window._apply_capabilities({"call_link_ready": True})
        assert window._call_link_ready is True  # sanity: ready before disconnect

        window._on_daemon_disconnected()

        assert window._call_link_ready is False

    def test_dial_button_disabled_after_disconnect(self, window):
        _make_callable_context(window)
        window._apply_capabilities({"call_link_ready": True})
        assert window._title_bar.dial_button.isEnabled()  # sanity: ready before disconnect

        window._on_daemon_disconnected()

        assert not window._title_bar.dial_button.isEnabled()

    def test_thread_header_call_button_disabled_after_disconnect(self, window):
        _make_callable_context(window)
        window._apply_capabilities({"call_link_ready": True})
        assert window._thread_view._header._call_btn.isEnabled()  # sanity

        window._on_daemon_disconnected()

        assert not window._thread_view._header._call_btn.isEnabled()


# ---------------------------------------------------------------------------
# §4 Precedence — call_setup_ready=False AND call_link_ready=False simultaneously
# ---------------------------------------------------------------------------

class TestPrecedenceCallSetupReadyBeatsCallLinkReady:
    """When both flags are False, the existing setup-not-ready copy wins (short-circuit order)."""

    def test_dial_button_tooltip_is_setup_copy(self, window):
        _make_callable_context(window)
        window._apply_capabilities({"call_setup_ready": False, "call_link_ready": False})

        assert window._title_bar.dial_button.toolTip() == _SETUP_TOOLTIP

    def test_dial_button_accessible_description_is_setup_copy(self, window):
        _make_callable_context(window)
        window._apply_capabilities({"call_setup_ready": False, "call_link_ready": False})

        assert window._title_bar.dial_button.accessibleDescription() == _SETUP_TOOLTIP

    def test_thread_header_call_button_tooltip_is_setup_copy(self, window):
        _make_callable_context(window)
        window._apply_capabilities({"call_setup_ready": False, "call_link_ready": False})

        assert window._thread_view._header._call_btn.toolTip() == _SETUP_TOOLTIP

    def test_thread_header_call_button_accessible_description_is_setup_copy(self, window):
        _make_callable_context(window)
        window._apply_capabilities({"call_setup_ready": False, "call_link_ready": False})

        desc = window._thread_view._header._call_btn.accessibleDescription()
        assert desc == _SETUP_TOOLTIP
