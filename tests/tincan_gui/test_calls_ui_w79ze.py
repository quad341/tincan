"""pytest-qt behavioral tests for Calls UI (tincan-8dehj).
Bead: tincan-w79ze

Tests should FAIL on the current branch (DialpadDialog / _sync_call_state not
yet present) and PASS once tincan-pyefu lands on main.

Coverage:
  §1 ThreadHeader Call button — hidden on group thread, visible on 1:1
  §2 TitleBar Dial button — disabled when call_setup_ready=False
  §3 DialpadDialog Call button — disabled when number field has <4 digits
  §4 call_requested signal — emitted with entered number on Enter key press
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSystemTrayIcon

from tincan_gui.main import DialpadDialog, MainWindow


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _no_tray_show():
    """Suppress QSystemTrayIcon.show() which errors in headless CI."""
    with patch.object(QSystemTrayIcon, "show"):
        yield


@pytest.fixture()
def window(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    return w


# ---------------------------------------------------------------------------
# §1 ThreadHeader Call button — group vs 1:1 (tincan-w79ze)
# ---------------------------------------------------------------------------

class TestThreadHeaderCallButton:
    """_sync_call_state hides the Call button for group threads; shows it for 1:1."""

    def test_call_button_hidden_on_group_thread(self, qtbot, window):
        """is_group=True → ThreadHeader Call button is hidden."""
        window._current_phone = "5551234567"
        window._call_setup_ready = True
        window._current_phone_dialable = True
        window._current_is_group = True

        window._sync_call_state()

        assert window._thread_view._header._call_btn.isHidden()

    def test_call_button_visible_on_one_to_one_thread(self, qtbot, window):
        """is_group=False with dialable phone → Call button is visible."""
        window._current_phone = "5551234567"
        window._call_setup_ready = True
        window._current_phone_dialable = True
        window._current_is_group = False

        window._sync_call_state()

        assert window._thread_view._header._call_btn.isVisible()

    def test_call_button_hidden_when_no_phone_selected(self, qtbot, window):
        """No conversation selected (empty phone) → Call button hidden regardless of group flag."""
        window._current_phone = ""
        window._call_setup_ready = True
        window._current_is_group = False

        window._sync_call_state()

        assert window._thread_view._header._call_btn.isHidden()


# ---------------------------------------------------------------------------
# §2 TitleBar Dial button — gated on call_setup_ready (tincan-w79ze)
# ---------------------------------------------------------------------------

class TestDialButtonCallSetupReady:
    """_sync_call_state enables/disables the TitleBar Dial button per call_setup_ready."""

    def test_dial_button_disabled_when_call_setup_not_ready(self, qtbot, window):
        """call_setup_ready=False → TitleBar Dial button is disabled."""
        window._call_setup_ready = False

        window._sync_call_state()

        assert not window._title_bar.dial_button.isEnabled()

    def test_dial_button_enabled_when_call_setup_ready(self, qtbot, window):
        """call_setup_ready=True → TitleBar Dial button is enabled."""
        window._call_setup_ready = True

        window._sync_call_state()

        assert window._title_bar.dial_button.isEnabled()

    def test_call_button_disabled_when_setup_not_ready_and_phone_selected(self, qtbot, window):
        """call_setup_ready=False → per-thread Call button shown but disabled."""
        window._current_phone = "5551234567"
        window._current_is_group = False
        window._current_phone_dialable = True
        window._call_setup_ready = False

        window._sync_call_state()

        assert not window._thread_view._header._call_btn.isEnabled()


# ---------------------------------------------------------------------------
# §3 DialpadDialog Call button — gated on ≥4 digits (tincan-w79ze)
# ---------------------------------------------------------------------------

class TestDialpadDialogCallButton:
    """DialpadDialog disables its Call button for <4 digits, enables it for ≥4."""

    @pytest.fixture()
    def dialog(self, qtbot):
        d = DialpadDialog()
        qtbot.addWidget(d)
        d.show()
        return d

    def test_call_button_initially_disabled(self, qtbot, dialog):
        """Call button starts disabled (empty field has 0 digits)."""
        assert not dialog._call_btn.isEnabled()

    def test_call_button_disabled_with_three_digits(self, qtbot, dialog):
        """Number field = '123' (3 digits) → Call button disabled."""
        dialog._number_input.setText("123")

        assert not dialog._call_btn.isEnabled()

    def test_call_button_enabled_at_four_digit_boundary(self, qtbot, dialog):
        """Number field = '1234' (4 digits, short-code lower bound) → Call button enabled."""
        dialog._number_input.setText("1234")

        assert dialog._call_btn.isEnabled()

    def test_call_button_enabled_with_full_phone_number(self, qtbot, dialog):
        """Number field = '4155550101' (10 digits) → Call button enabled."""
        dialog._number_input.setText("4155550101")

        assert dialog._call_btn.isEnabled()

    def test_call_button_re_disabled_when_digits_fall_below_threshold(self, qtbot, dialog):
        """Deleting digits past the threshold re-disables the Call button."""
        dialog._number_input.setText("1234")
        assert dialog._call_btn.isEnabled()

        dialog._number_input.setText("123")

        assert not dialog._call_btn.isEnabled()


# ---------------------------------------------------------------------------
# §4 call_requested signal — Enter key with entered number (tincan-w79ze)
# ---------------------------------------------------------------------------

class TestDialpadDialogEnterKey:
    """DialpadDialog emits call_requested(number) when Enter is pressed and Call is enabled."""

    @pytest.fixture()
    def dialog(self, qtbot):
        d = DialpadDialog()
        qtbot.addWidget(d)
        d.show()
        return d

    def test_enter_emits_call_requested_with_entered_number(self, qtbot, dialog):
        """Enter key with a valid number emits call_requested carrying that number."""
        dialog._number_input.setText("4155550101")

        with qtbot.waitSignal(dialog.call_requested, timeout=1000) as sig:
            qtbot.keyClick(dialog, Qt.Key.Key_Return)

        assert sig.args == ["4155550101"]

    def test_enter_does_not_emit_when_field_below_threshold(self, qtbot, dialog):
        """Enter key with <4 digits does NOT emit call_requested (Call button disabled)."""
        dialog._number_input.setText("123")

        received = []
        dialog.call_requested.connect(received.append)
        qtbot.keyClick(dialog, Qt.Key.Key_Return)

        assert received == []

    def test_enter_key_enter_variant_also_emits(self, qtbot, dialog):
        """Key_Enter (numpad Enter) also fires the call when enabled."""
        dialog._number_input.setText("4155550101")

        with qtbot.waitSignal(dialog.call_requested, timeout=1000) as sig:
            qtbot.keyClick(dialog, Qt.Key.Key_Enter)

        assert sig.args == ["4155550101"]
