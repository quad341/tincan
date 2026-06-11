"""Tests: HFP call UI wiring — disable_answer, _apply_capabilities call_setup_ready,
_on_answer_accepted, _on_call_decline, _on_hang_up, TincandClient.answer/hangup/dial.

Bead: tincan-8pgco
Source: tincan-jni3z commit 11826c6f (feat/call-ui-jni3z)

All test cases drive BEHAVIOR against the described acceptance criteria.
Tests should FAIL on main before the feature is merged (AttributeError /
ImportError for missing methods / attributes) and PASS once the builder
lands tincan-jni3z.

Covered paths:
  §1 IncomingCallDialog.disable_answer(reason)
  §2 MainWindow._apply_capabilities — call_setup_ready key
  §3 MainWindow._on_answer_accepted — dbus.answer() + enter in-call UI
  §4 MainWindow._on_call_decline — dbus.hangup() + clear dialog ref
  §5 MainWindow._on_hang_up — dbus.hangup()
  §6 TincandClient.answer / hangup / dial — im.tincan.Calls dispatch
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QLabel, QSystemTrayIcon, QWidget

import tincan_gui.call_panel as _cp_module
from tincan_gui.call_panel import IncomingCallDialog
from tincan_gui.dbus_client import TincandClient
from tincan_gui.main import MainWindow


# ---------------------------------------------------------------------------
# Module-level fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _no_tray_show():
    """Suppress the system tray icon popup that would error in headless CI."""
    with patch.object(QSystemTrayIcon, "show"):
        yield


@pytest.fixture(autouse=True)
def _patch_avatar():
    """Replace AvatarWidget with a plain QLabel.

    call_panel.py calls AvatarWidget(name, size=N) but the current
    AvatarWidget only accepts (name, parent=None).  Patch so the
    behavioral tests for call panels can run independently of that bug.
    """
    def _fake_avatar(name, size=None, parent=None):
        lbl = QLabel(name[:2].upper() if name else "?")
        if size:
            lbl.setFixedSize(size, size)
        return lbl

    with patch.object(_cp_module, "AvatarWidget", side_effect=_fake_avatar):
        yield


@pytest.fixture()
def parent_widget(qtbot):
    w = QWidget()
    w.resize(400, 300)
    qtbot.addWidget(w)
    w.show()
    return w


@pytest.fixture()
def window(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    return w


# ---------------------------------------------------------------------------
# §1 IncomingCallDialog.disable_answer(reason) — tincan-jni3z
# ---------------------------------------------------------------------------

class TestDisableAnswer:
    """disable_answer(reason) disables Answer and surfaces reason via tooltip + accessible description."""

    @pytest.fixture()
    def dialog(self, qtbot, parent_widget):
        d = IncomingCallDialog(
            caller_name="Alice",
            caller_number="+15551234567",
            avatar_pixmap=None,
            parent=parent_widget,
        )
        qtbot.addWidget(d)
        d.show()
        return d

    def test_button_is_disabled(self, dialog):
        """Answer button must be disabled after disable_answer()."""
        dialog.disable_answer("Call setup required")

        assert not dialog._answer_btn.isEnabled()

    def test_tooltip_matches_reason(self, dialog):
        """Answer button tooltip must match the reason string."""
        reason = "Phone calls: setup required."
        dialog.disable_answer(reason)

        assert dialog._answer_btn.toolTip() == reason

    def test_accessible_description_matches_reason(self, dialog):
        """accessibleDescription must be set for screen-reader access."""
        reason = "Accessible setup message"
        dialog.disable_answer(reason)

        assert dialog._answer_btn.accessibleDescription() == reason


# ---------------------------------------------------------------------------
# §2 MainWindow._apply_capabilities — call_setup_ready key (tincan-jni3z)
# ---------------------------------------------------------------------------

class TestApplyCapabilitiesCallSetupReady:
    """_apply_capabilities(caps) tracks call_setup_ready and shows/hides CallSetupRequiredBanner."""

    def test_false_sets_flag_and_shows_banner(self, qtbot, window):
        """call_setup_ready=False → _call_setup_ready False + banner visible."""
        window._apply_capabilities({"call_setup_ready": False})

        assert window._call_setup_ready is False
        assert window._banner_call_setup.isVisible()

    def test_true_clears_flag_and_hides_banner(self, qtbot, window):
        """call_setup_ready=True → _call_setup_ready True + banner hidden."""
        window._banner_call_setup.show()  # force visible first

        window._apply_capabilities({"call_setup_ready": True})

        assert window._call_setup_ready is True
        assert not window._banner_call_setup.isVisible()

    def test_absent_key_defaults_true_banner_hidden(self, qtbot, window):
        """call_setup_ready absent → defaults True (conservative: don't block calls)."""
        window._apply_capabilities({})

        assert window._call_setup_ready is True
        assert not window._banner_call_setup.isVisible()


# ---------------------------------------------------------------------------
# §3 MainWindow._on_answer_accepted (tincan-jni3z)
# ---------------------------------------------------------------------------

class TestOnAnswerAccepted:
    """_on_answer_accepted calls dbus_client.answer() and enters the in-call UI."""

    def test_calls_dbus_answer(self, qtbot, window, monkeypatch):
        """_on_answer_accepted must call dbus_client.answer() to signal the HFP stack."""
        mock_answer = MagicMock()
        monkeypatch.setattr(window._dbus_client, "answer", mock_answer)
        window._call_caller_name = "Bob"

        window._on_answer_accepted()

        mock_answer.assert_called_once()

    def test_compose_stack_switches_to_incall(self, qtbot, window, monkeypatch):
        """_on_answer_accepted enters the in-call UI (compose_stack at _PAGE_INCALL)."""
        monkeypatch.setattr(window._dbus_client, "answer", lambda: None)
        window._call_caller_name = "Bob"

        window._on_answer_accepted()

        assert window._compose_stack.currentIndex() == window._PAGE_INCALL


# ---------------------------------------------------------------------------
# §4 MainWindow._on_call_decline (tincan-jni3z)
# ---------------------------------------------------------------------------

class TestOnCallDecline:
    """_on_call_decline calls dbus_client.hangup() and clears the dialog reference."""

    def test_calls_dbus_hangup(self, qtbot, window, monkeypatch):
        """_on_call_decline must call dbus_client.hangup() to decline via HFP."""
        mock_hangup = MagicMock()
        monkeypatch.setattr(window._dbus_client, "hangup", mock_hangup)
        window._incall_dialog = MagicMock()

        window._on_call_decline()

        mock_hangup.assert_called_once()

    def test_clears_incall_dialog_reference(self, qtbot, window, monkeypatch):
        """_on_call_decline sets _incall_dialog to None (GC + no stale reference)."""
        monkeypatch.setattr(window._dbus_client, "hangup", lambda: None)
        window._incall_dialog = MagicMock()

        window._on_call_decline()

        assert window._incall_dialog is None


# ---------------------------------------------------------------------------
# §5 MainWindow._on_hang_up (tincan-jni3z)
# ---------------------------------------------------------------------------

class TestOnHangUp:
    """_on_hang_up calls dbus_client.hangup() (public method, not _dbus_call directly)."""

    def test_calls_dbus_hangup(self, qtbot, window, monkeypatch):
        """_on_hang_up must delegate to the public hangup() method."""
        mock_hangup = MagicMock()
        monkeypatch.setattr(window._dbus_client, "hangup", mock_hangup)

        window._on_hang_up()

        mock_hangup.assert_called_once()


# ---------------------------------------------------------------------------
# §6 TincandClient.answer / hangup / dial — im.tincan.Calls dispatch (tincan-jni3z)
# ---------------------------------------------------------------------------

class TestTincandClientCallMethods:
    """answer/hangup/dial route to im.tincan.Calls with correct method names and args."""

    @pytest.fixture()
    def _dbus_calls(self, monkeypatch):
        """Return a list that records each _dbus_call invocation as (iface, method, args)."""
        calls = []

        def _capture(self, iface, method, *args):
            calls.append((iface, method, args))
            return None

        monkeypatch.setattr(TincandClient, "_dbus_call", _capture)
        return calls

    def test_answer_uses_calls_interface(self, _dbus_calls):
        """answer() dispatches via im.tincan.Calls."""
        TincandClient().answer()

        assert _dbus_calls[0][0] == "im.tincan.Calls"

    def test_answer_method_name_is_answer(self, _dbus_calls):
        """answer() passes 'Answer' as the method name."""
        TincandClient().answer()

        assert _dbus_calls[0][1] == "Answer"

    def test_answer_passes_call_id_arg(self, _dbus_calls):
        """answer(call_id) forwards the call_id string."""
        TincandClient().answer("call-42")

        assert _dbus_calls[0][2] == ("call-42",)

    def test_answer_default_call_id_is_empty_string(self, _dbus_calls):
        """answer() with no arg passes an empty string call_id."""
        TincandClient().answer()

        assert _dbus_calls[0][2] == ("",)

    def test_hangup_uses_calls_interface(self, _dbus_calls):
        """hangup() dispatches via im.tincan.Calls."""
        TincandClient().hangup()

        assert _dbus_calls[0][0] == "im.tincan.Calls"

    def test_hangup_method_name_is_hangup(self, _dbus_calls):
        """hangup() passes 'Hangup' as the method name."""
        TincandClient().hangup()

        assert _dbus_calls[0][1] == "Hangup"

    def test_hangup_passes_call_id_arg(self, _dbus_calls):
        """hangup(call_id) forwards the call_id string."""
        TincandClient().hangup("call-99")

        assert _dbus_calls[0][2] == ("call-99",)

    def test_dial_uses_calls_interface(self, _dbus_calls):
        """dial(number) dispatches via im.tincan.Calls."""
        TincandClient().dial("+15551234567")

        assert _dbus_calls[0][0] == "im.tincan.Calls"

    def test_dial_method_name_is_dial(self, _dbus_calls):
        """dial() passes 'Dial' as the method name."""
        TincandClient().dial("+15551234567")

        assert _dbus_calls[0][1] == "Dial"

    def test_dial_passes_number_arg(self, _dbus_calls):
        """dial(number) forwards the number string."""
        TincandClient().dial("+15551234567")

        assert _dbus_calls[0][2] == ("+15551234567",)

    def test_dial_returns_result_coerced_to_string(self, monkeypatch):
        """dial() returns the _dbus_call result as str."""
        monkeypatch.setattr(TincandClient, "_dbus_call", lambda self, *a: "assigned-id")

        result = TincandClient().dial("5551234567")

        assert result == "assigned-id"
        assert isinstance(result, str)

    def test_dial_returns_empty_string_when_dbus_returns_none(self, monkeypatch):
        """dial() returns '' when _dbus_call returns None (daemon absent)."""
        monkeypatch.setattr(TincandClient, "_dbus_call", lambda self, *a: None)

        result = TincandClient().dial("5551234567")

        assert result == ""
