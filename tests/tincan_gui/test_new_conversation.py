"""Tests: dead '+' icons consolidated; new-conversation flow opens thread (tincan-nwp7p).

Coverage:
  - ConversationListWidget exposes exactly ONE compose '+' button in the header.
  - That button emits compose_new_requested exactly once per click.
  - The compose button is a QToolButton with tooltip "New conversation".
  - _on_compose_new in MainWindow calls load_thread after the dialog is accepted.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QPushButton, QSystemTrayIcon, QToolButton

from tincan_gui.conversation_list import ConversationListWidget
from tincan_gui.main import NewConversationDialog


@pytest.fixture(autouse=True)
def _no_tray_show():
    with patch.object(QSystemTrayIcon, "show"):
        yield


# ---------------------------------------------------------------------------
# §1  ConversationListWidget — single compose button
# ---------------------------------------------------------------------------

class TestComposeButtonCount:
    """The conversation list header must have exactly ONE '+' / compose button."""

    def test_exactly_one_compose_toolbutton(self, qtbot):
        w = ConversationListWidget()
        qtbot.addWidget(w)

        # Find all QToolButton descendants with text "+"
        plus_buttons = [
            b for b in w.findChildren(QToolButton)
            if b.text() == "+"
        ]
        assert len(plus_buttons) == 1, (
            f"Expected 1 '+' QToolButton, found {len(plus_buttons)}"
        )

    def test_no_pushbutton_compose_duplicate(self, qtbot):
        w = ConversationListWidget()
        qtbot.addWidget(w)

        # Should be no QPushButton with text "+" (old duplicate)
        plus_push = [
            b for b in w.findChildren(QPushButton)
            if b.text() == "+"
        ]
        assert len(plus_push) == 0, (
            f"Found {len(plus_push)} duplicate QPushButton '+' — should be 0"
        )

    def test_compose_button_has_correct_tooltip(self, qtbot):
        w = ConversationListWidget()
        qtbot.addWidget(w)

        plus_buttons = [
            b for b in w.findChildren(QToolButton)
            if b.text() == "+"
        ]
        assert plus_buttons, "No '+' QToolButton found"
        assert plus_buttons[0].toolTip() == "New conversation"

    def test_compose_button_emits_signal_once(self, qtbot):
        w = ConversationListWidget()
        qtbot.addWidget(w)
        w.show()

        signals = []
        w.compose_new_requested.connect(lambda: signals.append(1))

        plus_buttons = [
            b for b in w.findChildren(QToolButton)
            if b.text() == "+"
        ]
        assert plus_buttons
        plus_buttons[0].click()

        assert signals == [1], f"Expected 1 signal, got {len(signals)}"

    def test_compose_button_is_accessible(self, qtbot):
        w = ConversationListWidget()
        qtbot.addWidget(w)

        plus_buttons = [
            b for b in w.findChildren(QToolButton)
            if b.text() == "+"
        ]
        assert plus_buttons
        assert plus_buttons[0].accessibleName() == "New conversation"


# ---------------------------------------------------------------------------
# §2  _on_compose_new — thread loads after dialog accepted
# ---------------------------------------------------------------------------

class TestOnComposeNewLoadsThread:
    """After the new-conversation dialog is accepted, the thread view must be loaded."""

    def _make_main(self):
        from tincan_gui.main import MainWindow
        win = MainWindow.__new__(MainWindow)
        win._conversations_by_id = {}
        win._messages_ok = True
        win._connected_device = "AA:BB:CC:DD:EE:FF"
        win._current_phone = ""
        win._current_phone_dialable = False
        win._pending_sends = set()
        win._self_echo_guard = set()
        win._sent_bodies = {}
        win._sent_cache = {}
        win._dbus_client = MagicMock()
        win._dbus_client.list_conversations.return_value = []
        win._thread_view = MagicMock()
        win._compose = MagicMock()
        win._compose.send_button = MagicMock()
        win._conv_list = MagicMock()
        return win

    def test_load_thread_called_for_single_phone(self):
        win = self._make_main()

        with patch("tincan_gui.main.NewConversationDialog") as MockDlg:
            dlg = MockDlg.return_value
            dlg.exec.return_value = 1  # QDialog.Accepted
            dlg.selected_phones.return_value = ["+14155550001"]
            win._on_compose_new()

        win._thread_view.load_thread.assert_called_once()
        call_args = win._thread_view.load_thread.call_args
        assert "+14155550001" in call_args.args or "+14155550001" in str(call_args)

    def test_current_phone_set_on_accept(self):
        win = self._make_main()

        with patch("tincan_gui.main.NewConversationDialog") as MockDlg:
            dlg = MockDlg.return_value
            dlg.exec.return_value = 1
            dlg.selected_phones.return_value = ["+14155550002"]
            win._on_compose_new()

        assert win._current_phone == "+14155550002"

    def test_load_thread_not_called_on_cancel(self):
        win = self._make_main()

        with patch("tincan_gui.main.NewConversationDialog") as MockDlg:
            dlg = MockDlg.return_value
            dlg.exec.return_value = 0  # QDialog.Rejected
            dlg.selected_phones.return_value = []
            win._on_compose_new()

        win._thread_view.load_thread.assert_not_called()

    def test_current_phone_not_changed_on_cancel(self):
        win = self._make_main()
        win._current_phone = "+19995550000"

        with patch("tincan_gui.main.NewConversationDialog") as MockDlg:
            dlg = MockDlg.return_value
            dlg.exec.return_value = 0
            dlg.selected_phones.return_value = []
            win._on_compose_new()

        assert win._current_phone == "+19995550000"

    def test_disconnected_does_not_open_dialog(self):
        win = self._make_main()
        win._connected_device = ""

        with patch("tincan_gui.main.NewConversationDialog") as MockDlg:
            win._on_compose_new()

        MockDlg.assert_not_called()

    def test_main_window_disables_compose_new_until_connected(self, qtbot, monkeypatch):
        from tincan_gui.dbus_client import TincandClient
        from tincan_gui.main import MainWindow

        monkeypatch.setattr(TincandClient, "get_status", lambda self: {"connected": False})
        monkeypatch.setattr(TincandClient, "list_conversations", lambda self: [])

        win = MainWindow()
        qtbot.addWidget(win)
        button = next(
            b for b in win._conv_list.findChildren(QToolButton)
            if b.text() == "+"
        )

        assert not button.isEnabled()
        assert button.toolTip() == "Connect a device to start a new conversation"

        monkeypatch.setattr(
            TincandClient,
            "get_status",
            lambda self: {
                "connected": True,
                "device_name": "Malala",
                "capabilities": {"messages": True, "contacts": True, "ancs": True},
            },
        )
        win._on_daemon_connected("AA:BB:CC:DD:EE:FF")
        assert button.isEnabled()

        win._on_daemon_disconnected()
        assert not button.isEnabled()


# ---------------------------------------------------------------------------
# §3 NewConversationDialog — eventFilter _autocomplete init guard (tincan-91th2)
# ---------------------------------------------------------------------------

class TestNewConversationDialogEventFilter:
    """NewConversationDialog must not crash with AttributeError on _autocomplete.

    Root cause: installEventFilter(self) was called before self._autocomplete
    was created, so any Qt event delivered to _text_input during widget setup
    (resize, polish, etc.) would reach the eventFilter's 'obj is self._autocomplete'
    check and raise AttributeError.
    """

    def test_dialog_instantiates_without_attribute_error(self, qtbot):
        """Creating NewConversationDialog must not raise AttributeError for _autocomplete."""
        # This fails with the broken code — Qt sends polish/resize events to
        # _text_input during setWidget() before _autocomplete is created.
        dlg = NewConversationDialog([], parent=None)
        qtbot.addWidget(dlg)

    def test_dialog_instantiates_with_contacts(self, qtbot):
        contacts = [{"name": "Alice", "phone": "+14155550001"}]
        dlg = NewConversationDialog(contacts, parent=None)
        qtbot.addWidget(dlg)

    def test_key_down_does_not_crash(self, qtbot):
        """Down-arrow key on _text_input must navigate autocomplete without AttributeError."""
        dlg = NewConversationDialog([], parent=None)
        qtbot.addWidget(dlg)
        key_event = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier
        )
        dlg.eventFilter(dlg._text_input, key_event)

    def test_selected_phones_initially_empty(self, qtbot):
        dlg = NewConversationDialog([], parent=None)
        qtbot.addWidget(dlg)
        assert dlg.selected_phones() == []
