"""Tests: DesktopNotifier dispatch, SettingsDialog, click-to-raise, tray menu.
Bead: tincan-rovp.6 (test coverage for desktop notification feature)

Coverage:
  - DesktopNotifier._should_notify(): direction, status, is_new, disabled-setting, dedup guard
  - DesktopNotifier.dispatch(): Notify() called/skipped via mocked dbus.SessionBus
  - DesktopNotifier._on_action_invoked_signal(): callback dispatch and no-op paths
  - SettingsDialog: checkbox default, QSettings persistence, notifications_toggled signal
  - SettingsDialog: APPEARANCE section has no interactive controls; dialog is modal
  - SettingsDialog: Space toggles checkbox; Esc/Close closes dialog
  - ConversationListWidget.select_conversation(): selects correct item, emits signal
  - MainWindow._on_notification_clicked(): raises window, calls select_conversation
  - TrayIcon.sync_notifications_action(): checkbox state synchronization
  - TrayIcon._on_menu_about_to_show(): reads desktop_enabled from QSettings on open
  - §11 Actionable notifications (tincan-5ptsg): reply + mark-read action buttons
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSystemTrayIcon

from tincan_gui.conversation_list import ConversationData, ConversationListWidget
from tincan_gui.main import MainWindow
from tincan_gui.notifications import DesktopNotifier
from tincan_gui.settings_dialog import SettingsDialog


@pytest.fixture(autouse=True)
def _no_tray_show():
    with patch.object(QSystemTrayIcon, "show"):
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_settings(desktop_enabled: bool = True) -> MagicMock:
    """Return a QSettings mock whose value() returns desktop_enabled."""
    s = MagicMock()
    s.value.return_value = desktop_enabled
    return s


def _make_dbus_mock():
    """Minimal dbus module mock: UInt32/Int32/Array/Dictionary are identity; Interface
    returns a mock iface whose Notify() returns 42; DBusException aliases Exception."""
    mock_iface = MagicMock()
    mock_iface.Notify.return_value = 42

    mock_dbus = MagicMock()
    mock_dbus.UInt32 = lambda x: x
    mock_dbus.Int32 = lambda x: x
    mock_dbus.Array = lambda x, signature=None: x
    mock_dbus.Dictionary = lambda x, signature=None: x
    mock_dbus.Interface.return_value = mock_iface
    mock_dbus.DBusException = Exception  # lets except dbus.DBusException work

    return mock_dbus, MagicMock(), mock_iface


def _make_notifier_with_mock_bus():
    """Create a DesktopNotifier with _bus pre-set to a MagicMock so _ensure_bus()
    returns immediately without attempting a real D-Bus connection."""
    notifier = DesktopNotifier()
    mock_bus = MagicMock()
    notifier._bus = mock_bus
    return notifier, mock_bus


_INBOUND_NEW = {
    "direction": "inbound",
    "status": "unread",
    "is_new": True,
    "body": "Hello world",
    "timestamp": "2026-06-02T10:00:00",
    "conversation_id": "conv-alice",
    "from": "Alice",
}

_DBUS_MODULES = {"dbus": None, "dbus.mainloop": None, "dbus.mainloop.glib": None}


def _dbus_patches(mock_dbus, mock_glib):
    """Return a dict for patch.dict(sys.modules, ...) covering the dbus import tree."""
    return {
        "dbus": mock_dbus,
        "dbus.mainloop": MagicMock(),
        "dbus.mainloop.glib": mock_glib,
    }


# ---------------------------------------------------------------------------
# §1 _should_notify() — decision logic
# ---------------------------------------------------------------------------

class TestShouldNotify:
    """_should_notify() gates the Notify() call correctly for direction, status, dedup."""

    def test_inbound_unread_returns_true(self):
        notifier = DesktopNotifier()
        with patch("tincan_gui._settings.app_settings", return_value=_mock_settings(True)):
            assert notifier._should_notify({**_INBOUND_NEW, "status": "unread"}) is True

    def test_inbound_status_new_returns_true(self):
        notifier = DesktopNotifier()
        with patch("tincan_gui._settings.app_settings", return_value=_mock_settings(True)):
            msg = {**_INBOUND_NEW, "status": "new", "is_new": False}
            assert notifier._should_notify(msg) is True

    def test_inbound_is_new_without_status_returns_true(self):
        notifier = DesktopNotifier()
        msg = {"direction": "inbound", "is_new": True,
               "body": "Hey", "timestamp": "t0", "conversation_id": "c1"}
        with patch("tincan_gui._settings.app_settings", return_value=_mock_settings(True)):
            assert notifier._should_notify(msg) is True

    def test_outbound_returns_false(self):
        notifier = DesktopNotifier()
        with patch("tincan_gui._settings.app_settings", return_value=_mock_settings(True)):
            assert notifier._should_notify({**_INBOUND_NEW, "direction": "outbound"}) is False

    def test_inbound_read_and_not_is_new_returns_false(self):
        notifier = DesktopNotifier()
        with patch("tincan_gui._settings.app_settings", return_value=_mock_settings(True)):
            assert notifier._should_notify(
                {**_INBOUND_NEW, "status": "read", "is_new": False}
            ) is False

    def test_disabled_setting_returns_false_for_valid_inbound(self):
        notifier = DesktopNotifier()
        with patch("tincan_gui._settings.app_settings", return_value=_mock_settings(False)):
            assert notifier._should_notify(_INBOUND_NEW) is False

    def test_dedup_same_body_and_timestamp_returns_false_on_repeat(self):
        notifier = DesktopNotifier()
        with patch("tincan_gui._settings.app_settings", return_value=_mock_settings(True)):
            first = notifier._should_notify(_INBOUND_NEW)
            second = notifier._should_notify(_INBOUND_NEW)
        assert first is True
        assert second is False

    def test_dedup_different_conversations_are_independent(self):
        notifier = DesktopNotifier()
        msg_a = {**_INBOUND_NEW, "conversation_id": "conv-a"}
        msg_b = {**_INBOUND_NEW, "conversation_id": "conv-b"}
        with patch("tincan_gui._settings.app_settings", return_value=_mock_settings(True)):
            assert notifier._should_notify(msg_a) is True
            assert notifier._should_notify(msg_b) is True

    def test_dedup_different_body_same_conv_is_not_deduped(self):
        notifier = DesktopNotifier()
        msg1 = {**_INBOUND_NEW, "body": "first message"}
        msg2 = {**_INBOUND_NEW, "body": "second message"}
        with patch("tincan_gui._settings.app_settings", return_value=_mock_settings(True)):
            assert notifier._should_notify(msg1) is True
            assert notifier._should_notify(msg2) is True


# ---------------------------------------------------------------------------
# §2 Dispatch — mocked dbus.SessionBus
# ---------------------------------------------------------------------------

class TestDispatch:
    """dispatch() calls Notify() via dbus when warranted; skips on every no-notify path."""

    def test_inbound_is_new_calls_notify_once(self):
        mock_dbus, mock_glib, mock_iface = _make_dbus_mock()
        notifier, mock_bus = _make_notifier_with_mock_bus()
        mock_bus.get_object.return_value = MagicMock()
        mock_dbus.Interface.return_value = mock_iface

        with patch.dict(sys.modules, _dbus_patches(mock_dbus, mock_glib)):
            with patch("tincan_gui._settings.app_settings", return_value=_mock_settings(True)):
                notifier.dispatch(_INBOUND_NEW)

        mock_iface.Notify.assert_called_once()

    def test_outbound_does_not_call_notify(self):
        mock_dbus, mock_glib, mock_iface = _make_dbus_mock()
        notifier, _ = _make_notifier_with_mock_bus()

        with patch.dict(sys.modules, _dbus_patches(mock_dbus, mock_glib)):
            with patch("tincan_gui._settings.app_settings", return_value=_mock_settings(True)):
                notifier.dispatch({**_INBOUND_NEW, "direction": "outbound"})

        mock_iface.Notify.assert_not_called()

    def test_disabled_setting_does_not_call_notify(self):
        mock_dbus, mock_glib, mock_iface = _make_dbus_mock()
        notifier, _ = _make_notifier_with_mock_bus()

        with patch.dict(sys.modules, _dbus_patches(mock_dbus, mock_glib)):
            with patch("tincan_gui._settings.app_settings", return_value=_mock_settings(False)):
                notifier.dispatch(_INBOUND_NEW)

        mock_iface.Notify.assert_not_called()

    def test_dedup_repeated_message_calls_notify_only_once(self):
        mock_dbus, mock_glib, mock_iface = _make_dbus_mock()
        notifier, mock_bus = _make_notifier_with_mock_bus()
        mock_bus.get_object.return_value = MagicMock()
        mock_dbus.Interface.return_value = mock_iface

        with patch.dict(sys.modules, _dbus_patches(mock_dbus, mock_glib)):
            with patch("tincan_gui._settings.app_settings", return_value=_mock_settings(True)):
                notifier.dispatch(_INBOUND_NEW)
                notifier.dispatch(_INBOUND_NEW)

        assert mock_iface.Notify.call_count == 1

    def test_notify_records_notif_id_for_conv(self):
        mock_dbus, mock_glib, mock_iface = _make_dbus_mock()
        mock_iface.Notify.return_value = 7
        notifier, mock_bus = _make_notifier_with_mock_bus()
        mock_bus.get_object.return_value = MagicMock()
        mock_dbus.Interface.return_value = mock_iface

        with patch.dict(sys.modules, _dbus_patches(mock_dbus, mock_glib)):
            with patch("tincan_gui._settings.app_settings", return_value=_mock_settings(True)):
                notifier.dispatch(_INBOUND_NEW)

        assert notifier._notif_to_conv[7] == "conv-alice"


# ---------------------------------------------------------------------------
# §2b DispatchAppNotification — dedup (tincan-qt852 AC 8)
# ---------------------------------------------------------------------------

class TestDispatchAppNotification:
    """dispatch_app_notification() dedups on (app_id, title, body) triple."""

    def test_duplicate_triple_suppressed(self):
        mock_dbus, mock_glib, mock_iface = _make_dbus_mock()
        mock_iface.Notify.return_value = 1
        notifier, mock_bus = _make_notifier_with_mock_bus()
        mock_bus.get_object.return_value = MagicMock()
        mock_dbus.Interface.return_value = mock_iface
        notif = {"app_id": "com.foo.App", "title": "Title", "body": "Hello"}
        with patch.dict(sys.modules, _dbus_patches(mock_dbus, mock_glib)):
            notifier.dispatch_app_notification(notif)
            notifier.dispatch_app_notification(notif)
        assert mock_iface.Notify.call_count == 1

    def test_distinct_body_passes_through(self):
        mock_dbus, mock_glib, mock_iface = _make_dbus_mock()
        mock_iface.Notify.return_value = 1
        notifier, mock_bus = _make_notifier_with_mock_bus()
        mock_bus.get_object.return_value = MagicMock()
        mock_dbus.Interface.return_value = mock_iface
        notif1 = {"app_id": "com.foo.App", "title": "Title", "body": "First"}
        notif2 = {"app_id": "com.foo.App", "title": "Title", "body": "Second"}
        with patch.dict(sys.modules, _dbus_patches(mock_dbus, mock_glib)):
            notifier.dispatch_app_notification(notif1)
            notifier.dispatch_app_notification(notif2)
        assert mock_iface.Notify.call_count == 2


# ---------------------------------------------------------------------------
# §3 ActionInvoked signal handler
# ---------------------------------------------------------------------------

class TestActionInvokedSignalHandler:
    """_on_action_invoked_signal routes click-to-raise or no-ops safely."""

    def test_default_action_invokes_callback_with_conv_id(self):
        received = []
        notifier = DesktopNotifier(on_action_invoked=lambda cid: received.append(cid))
        notifier._notif_to_conv[42] = "conv-alice"

        notifier._on_action_invoked_signal(42, "default")

        assert received == ["conv-alice"]

    def test_non_default_action_does_not_invoke_callback(self):
        received = []
        notifier = DesktopNotifier(on_action_invoked=lambda cid: received.append(cid))
        notifier._notif_to_conv[42] = "conv-alice"

        notifier._on_action_invoked_signal(42, "close")

        assert received == []

    def test_unknown_notif_id_does_not_invoke_callback(self):
        # notif ID 99 is not in _notif_to_conv — spurious signal is ignored.
        received = []
        notifier = DesktopNotifier(on_action_invoked=lambda cid: received.append(cid))

        notifier._on_action_invoked_signal(99, "default")

        assert received == []

    def test_open_action_on_app_notification_invokes_callback(self):
        # Regression: 'Open' on an ANCS app notification must raise the window
        # even though conv_id == "" (no conversation to select).
        received = []
        notifier = DesktopNotifier(on_action_invoked=lambda cid: received.append(cid))
        notifier._notif_to_conv[42] = ""  # app notification: known ID, no conv

        notifier._on_action_invoked_signal(42, "open")

        assert received == [""]

    def test_no_callback_does_not_raise(self):
        notifier = DesktopNotifier(on_action_invoked=None)
        notifier._notif_to_conv[1] = "conv-x"

        notifier._on_action_invoked_signal(1, "default")
        # Must not raise


# ---------------------------------------------------------------------------
# §4 SettingsDialog — state and persistence
# ---------------------------------------------------------------------------

class TestSettingsDialogState:
    """SettingsDialog reads QSettings on init, persists on toggle, emits signal."""

    def test_checkbox_is_checked_when_setting_is_true(self, qtbot):
        with patch("tincan_gui.settings_dialog.app_settings", return_value=_mock_settings(True)):
            dlg = SettingsDialog()
            qtbot.addWidget(dlg)

        assert dlg._desktop_cb.isChecked() is True

    def test_checkbox_is_unchecked_when_setting_is_false(self, qtbot):
        with patch("tincan_gui.settings_dialog.app_settings", return_value=_mock_settings(False)):
            dlg = SettingsDialog()
            qtbot.addWidget(dlg)

        assert dlg._desktop_cb.isChecked() is False

    def test_unchecking_checkbox_calls_set_value_false(self, qtbot):
        mock_settings = _mock_settings(True)
        with patch("tincan_gui.settings_dialog.app_settings", return_value=mock_settings):
            dlg = SettingsDialog()
            qtbot.addWidget(dlg)
            dlg._desktop_cb.setChecked(False)

        mock_settings.setValue.assert_called_with("notifications/desktop_enabled", False)

    def test_checking_checkbox_calls_set_value_true(self, qtbot):
        mock_settings = _mock_settings(False)
        with patch("tincan_gui.settings_dialog.app_settings", return_value=mock_settings):
            dlg = SettingsDialog()
            qtbot.addWidget(dlg)
            dlg._desktop_cb.setChecked(True)

        mock_settings.setValue.assert_called_with("notifications/desktop_enabled", True)

    def test_toggle_emits_notifications_toggled_false(self, qtbot):
        mock_settings = _mock_settings(True)
        received = []
        with patch("tincan_gui.settings_dialog.app_settings", return_value=mock_settings):
            dlg = SettingsDialog()
            qtbot.addWidget(dlg)
            dlg.notifications_toggled.connect(lambda v: received.append(v))
            dlg._desktop_cb.setChecked(False)

        assert received == [False]

    def test_toggle_emits_notifications_toggled_true(self, qtbot):
        mock_settings = _mock_settings(False)
        received = []
        with patch("tincan_gui.settings_dialog.app_settings", return_value=mock_settings):
            dlg = SettingsDialog()
            qtbot.addWidget(dlg)
            dlg.notifications_toggled.connect(lambda v: received.append(v))
            dlg._desktop_cb.setChecked(True)

        assert received == [True]

    def test_desktop_notifications_enabled_property_reflects_checkbox(self, qtbot):
        with patch("tincan_gui.settings_dialog.app_settings", return_value=_mock_settings(True)):
            dlg = SettingsDialog()
            qtbot.addWidget(dlg)

        assert dlg.desktop_notifications_enabled is True


# ---------------------------------------------------------------------------
# §5 SettingsDialog — APPEARANCE section and keyboard accessibility
# ---------------------------------------------------------------------------

class TestSettingsDialogAccessibility:
    """APPEARANCE section is decorative only; dialog is modal and keyboard-navigable."""

    def test_appearance_section_has_no_interactive_controls(self, qtbot):
        from PySide6.QtWidgets import QAbstractButton, QComboBox, QDialogButtonBox, QLineEdit

        with patch("tincan_gui.settings_dialog.app_settings", return_value=_mock_settings(True)):
            dlg = SettingsDialog()
            qtbot.addWidget(dlg)

        # PySide6 findChildren() accepts one type at a time.
        interactive = (
            dlg.findChildren(QAbstractButton)
            + dlg.findChildren(QLineEdit)
            + dlg.findChildren(QComboBox)
        )
        # Strip the known checkboxes and anything inside the QDialogButtonBox.
        known = {dlg._desktop_cb, dlg._mirror_cb, dlg._close_to_tray_cb}
        unexpected = [
            w for w in interactive
            if w not in known
            and not isinstance(w.parent(), QDialogButtonBox)
            and not isinstance(w, QDialogButtonBox)
        ]
        assert unexpected == []

    def test_dialog_is_modal(self, qtbot):
        with patch("tincan_gui.settings_dialog.app_settings", return_value=_mock_settings(True)):
            dlg = SettingsDialog()
            qtbot.addWidget(dlg)

        assert dlg.isModal() is True

    def test_reject_fires_rejected_signal(self, qtbot):
        with patch("tincan_gui.settings_dialog.app_settings", return_value=_mock_settings(True)):
            dlg = SettingsDialog()
            qtbot.addWidget(dlg)

        rejected_fired = []
        dlg.rejected.connect(lambda: rejected_fired.append(True))
        dlg.reject()

        assert len(rejected_fired) == 1

    def test_space_key_toggles_checkbox(self, qtbot):
        with patch("tincan_gui.settings_dialog.app_settings", return_value=_mock_settings(True)):
            dlg = SettingsDialog()
            qtbot.addWidget(dlg)

        before = dlg._desktop_cb.isChecked()
        dlg._desktop_cb.setFocus()
        qtbot.keyClick(dlg._desktop_cb, Qt.Key.Key_Space)

        assert dlg._desktop_cb.isChecked() is not before

    def test_escape_key_closes_dialog(self, qtbot):
        with patch("tincan_gui.settings_dialog.app_settings", return_value=_mock_settings(True)):
            dlg = SettingsDialog()
            qtbot.addWidget(dlg)
            dlg.show()

        rejected_fired = []
        dlg.rejected.connect(lambda: rejected_fired.append(True))
        qtbot.keyClick(dlg, Qt.Key.Key_Escape)

        assert len(rejected_fired) == 1


# ---------------------------------------------------------------------------
# §6 ConversationListWidget.select_conversation()
# ---------------------------------------------------------------------------

class TestSelectConversation:
    """select_conversation() selects the matching item, emits conversation_selected."""

    def _load_widget(self, qtbot):
        widget = ConversationListWidget()
        qtbot.addWidget(widget)
        widget.load_conversations([
            ConversationData(id="c1", name="Alice", phone="+1 555-0100",
                             preview="Hey", timestamp="10:00"),
            ConversationData(id="c2", name="Bob", phone="+1 555-0101",
                             preview="Hi", timestamp="09:00"),
            ConversationData(id="c3", name="Carol", phone="+1 555-0102",
                             preview="Hello", timestamp="08:00"),
        ])
        return widget

    def test_select_first_item_by_id(self, qtbot):
        widget = self._load_widget(qtbot)
        widget.select_conversation("c1")
        assert widget.current_index() == 0

    def test_select_middle_item_by_id(self, qtbot):
        widget = self._load_widget(qtbot)
        widget.select_conversation("c2")
        assert widget.current_index() == 1

    def test_select_last_item_by_id(self, qtbot):
        widget = self._load_widget(qtbot)
        widget.select_conversation("c3")
        assert widget.current_index() == 2

    def test_select_conversation_emits_signal_with_correct_id(self, qtbot):
        widget = self._load_widget(qtbot)
        received = []
        widget.conversation_selected.connect(lambda cid: received.append(cid))

        widget.select_conversation("c2")

        assert received == ["c2"]

    def test_unknown_id_does_not_crash_and_leaves_index_unchanged(self, qtbot):
        widget = self._load_widget(qtbot)
        widget.select_conversation("nonexistent")
        assert widget.current_index() == -1

    def test_selected_item_has_selected_flag_set(self, qtbot):
        widget = self._load_widget(qtbot)
        widget.select_conversation("c1")
        assert widget._items[0]._selected is True

    def test_previous_selection_is_deselected_when_new_item_selected(self, qtbot):
        widget = self._load_widget(qtbot)
        widget.select_conversation("c1")
        widget.select_conversation("c2")
        assert widget._items[0]._selected is False
        assert widget._items[1]._selected is True


# ---------------------------------------------------------------------------
# §7 MainWindow._on_notification_clicked
# ---------------------------------------------------------------------------

class TestOnNotificationClicked:
    """_on_notification_clicked raises the window and selects the conversation."""

    def test_window_becomes_visible_on_click(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        # Window starts hidden (no show() called in __init__)
        window.hide()

        window._on_notification_clicked("c1")

        assert window.isVisible()

    def test_select_conversation_called_with_correct_id(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)

        selected = []
        window._conv_list.select_conversation = lambda cid: selected.append(cid)

        window._on_notification_clicked("c2")

        assert selected == ["c2"]

    def test_empty_conv_id_does_not_call_select_conversation(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)

        selected = []
        window._conv_list.select_conversation = lambda cid: selected.append(cid)

        window._on_notification_clicked("")

        assert selected == []

    def test_unknown_conv_id_does_not_crash(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()

        # "nonexistent" won't match any conversation — select_conversation no-ops
        window._on_notification_clicked("nonexistent-conv")


# ---------------------------------------------------------------------------
# §8 TrayIcon.sync_notifications_action
# ---------------------------------------------------------------------------

class TestTrayIconSyncNotificationsAction:
    """sync_notifications_action() keeps tray checkbox in sync with dialog changes."""

    def test_sync_true_checks_the_action(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window._tray._notif_action.setChecked(False)

        window._tray.sync_notifications_action(True)

        assert window._tray._notif_action.isChecked() is True

    def test_sync_false_unchecks_the_action(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window._tray._notif_action.setChecked(True)

        window._tray.sync_notifications_action(False)

        assert window._tray._notif_action.isChecked() is False

    def test_settings_dialog_wiring_propagates_toggle_to_tray(self, qtbot):
        """SettingsDialog.notifications_toggled wired to sync_notifications_action."""
        window = MainWindow()
        qtbot.addWidget(window)

        mock_settings = _mock_settings(True)
        with patch("tincan_gui.settings_dialog.app_settings", return_value=mock_settings):
            dlg = SettingsDialog(window)
            qtbot.addWidget(dlg)
            dlg.notifications_toggled.connect(window._tray.sync_notifications_action)

            dlg._desktop_cb.setChecked(False)

        assert window._tray._notif_action.isChecked() is False


# ---------------------------------------------------------------------------
# §9 TrayIcon — tray menu state mirrors QSettings
# ---------------------------------------------------------------------------

class TestTrayIconMenuState:
    """Tray notifications action syncs from QSettings each time the menu opens."""

    def test_menu_about_to_show_checks_action_when_setting_true(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window._tray._notif_action.setChecked(False)

        with patch("tincan_gui.tray.app_settings", return_value=_mock_settings(True)):
            window._tray._on_menu_about_to_show()

        assert window._tray._notif_action.isChecked() is True

    def test_menu_about_to_show_unchecks_action_when_setting_false(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window._tray._notif_action.setChecked(True)

        with patch("tincan_gui.tray.app_settings", return_value=_mock_settings(False)):
            window._tray._on_menu_about_to_show()

        assert window._tray._notif_action.isChecked() is False

    def test_tray_toggle_writes_desktop_enabled_to_settings(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)

        mock_settings = _mock_settings(True)
        with patch("tincan_gui.tray.app_settings", return_value=mock_settings):
            window._tray._on_notifications_toggled(False)

        mock_settings.setValue.assert_called_with("notifications/desktop_enabled", False)


# ---------------------------------------------------------------------------
# §10 End-to-end: _on_message_received → notifier.dispatch (ikpf9 regression)
# ---------------------------------------------------------------------------

class TestMessageReceivedTriggersNotification:
    """_on_message_received must call _notifier.dispatch for inbound messages.

    Regression guard for tincan-ikpf9: messages were arriving at the daemon
    but the GUI produced zero notification activity.  The notification path
    must be called for every inbound message that passes the receive handler.
    """

    _INBOUND_UNREAD = {
        "direction": "inbound",
        "status": "unread",
        "is_new": True,
        "body": "R u busy",
        "timestamp": "20260605T120000",
        "conversation_id": "+18157916347",
        "from": "Mom Wordelman",
        "display_name": "Mom Wordelman",
    }

    def test_inbound_message_calls_notifier_dispatch(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        dispatch_calls = []
        window._notifier.dispatch = lambda msg: dispatch_calls.append(msg)

        window._on_message_received(self._INBOUND_UNREAD)

        assert len(dispatch_calls) == 1, (
            "_on_message_received must call _notifier.dispatch for inbound messages"
        )

    def test_dispatch_called_before_thread_guard(self, qtbot):
        """Notification fires even when no conversation is selected (thread guard fires later)."""
        window = MainWindow()
        qtbot.addWidget(window)
        window._current_phone = ""  # no conversation selected
        dispatch_calls = []
        window._notifier.dispatch = lambda msg: dispatch_calls.append(msg)

        window._on_message_received(self._INBOUND_UNREAD)

        assert len(dispatch_calls) == 1

    def test_outbound_echo_suppression_does_not_skip_dispatch(self, qtbot):
        """Outbound echo suppression returns early — dispatch still fires before those guards."""
        window = MainWindow()
        qtbot.addWidget(window)
        dispatch_calls = []
        window._notifier.dispatch = lambda msg: dispatch_calls.append(msg)
        outbound = {**self._INBOUND_UNREAD, "direction": "outbound"}

        window._on_message_received(outbound)

        assert len(dispatch_calls) == 1

    def test_notification_not_fired_when_desktop_disabled(self, qtbot):
        """When desktop_enabled=False, _should_notify returns False and Notify() is NOT called."""
        mock_dbus, mock_glib, mock_iface = _make_dbus_mock()
        window = MainWindow()
        qtbot.addWidget(window)
        window._notifier._bus = MagicMock()
        window._notifier._bus.get_object.return_value = MagicMock()
        mock_dbus.Interface.return_value = mock_iface

        with patch.dict(sys.modules, _dbus_patches(mock_dbus, mock_glib)):
            with patch("tincan_gui._settings.app_settings", return_value=_mock_settings(False)):
                window._on_message_received(self._INBOUND_UNREAD)

        mock_iface.Notify.assert_not_called()

    def test_notification_fired_when_desktop_enabled(self, qtbot):
        """When desktop_enabled=True, _notify() calls Notify() via mock dbus."""
        mock_dbus, mock_glib, mock_iface = _make_dbus_mock()
        window = MainWindow()
        qtbot.addWidget(window)
        window._notifier._bus = MagicMock()
        window._notifier._bus.get_object.return_value = MagicMock()
        mock_dbus.Interface.return_value = mock_iface

        with patch.dict(sys.modules, _dbus_patches(mock_dbus, mock_glib)):
            with patch("tincan_gui._settings.app_settings", return_value=_mock_settings(True)):
                window._on_message_received(self._INBOUND_UNREAD)

        mock_iface.Notify.assert_called_once()


# ---------------------------------------------------------------------------
# §11 Actionable notifications — reply + mark-read buttons (tincan-5ptsg)
# ---------------------------------------------------------------------------

class TestActionableNotifications:
    """Notifications expose 'reply' and 'mark-read' action buttons; each fires the right callback.
    """

    # --- action buttons appear in Notify() call ---

    def test_notify_call_includes_reply_action(self):
        mock_dbus, mock_glib, mock_iface = _make_dbus_mock()
        mock_iface.Notify.return_value = 1
        notifier, mock_bus = _make_notifier_with_mock_bus()
        mock_bus.get_object.return_value = MagicMock()
        mock_dbus.Interface.return_value = mock_iface

        with patch.dict(sys.modules, _dbus_patches(mock_dbus, mock_glib)):
            with patch("tincan_gui._settings.app_settings", return_value=_mock_settings(True)):
                notifier.dispatch(_INBOUND_NEW)

        actions = mock_iface.Notify.call_args[0][5]
        assert "reply" in actions, f"'reply' action id missing from {actions}"

    def test_notify_call_includes_mark_read_action(self):
        mock_dbus, mock_glib, mock_iface = _make_dbus_mock()
        mock_iface.Notify.return_value = 1
        notifier, mock_bus = _make_notifier_with_mock_bus()
        mock_bus.get_object.return_value = MagicMock()
        mock_dbus.Interface.return_value = mock_iface

        with patch.dict(sys.modules, _dbus_patches(mock_dbus, mock_glib)):
            with patch("tincan_gui._settings.app_settings", return_value=_mock_settings(True)):
                notifier.dispatch(_INBOUND_NEW)

        actions = mock_iface.Notify.call_args[0][5]
        assert "mark-read" in actions, f"'mark-read' action id missing from {actions}"

    # --- action callbacks ---

    def test_reply_action_invokes_on_action_invoked_callback(self):
        received = []
        notifier = DesktopNotifier(on_action_invoked=lambda cid: received.append(cid))
        notifier._notif_to_conv[10] = "conv-alice"

        notifier._on_action_invoked_signal(10, "reply")

        assert received == ["conv-alice"]

    def test_mark_read_action_invokes_on_mark_read_callback(self):
        marked = []
        notifier = DesktopNotifier(
            on_action_invoked=lambda cid: None,
            on_mark_read=lambda cid: marked.append(cid),
        )
        notifier._notif_to_conv[10] = "conv-alice"

        notifier._on_action_invoked_signal(10, "mark-read")

        assert marked == ["conv-alice"]

    def test_mark_read_callback_not_called_for_other_actions(self):
        marked = []
        notifier = DesktopNotifier(
            on_mark_read=lambda cid: marked.append(cid),
        )
        notifier._notif_to_conv[10] = "conv-alice"

        notifier._on_action_invoked_signal(10, "default")
        notifier._on_action_invoked_signal(10, "reply")
        notifier._on_action_invoked_signal(10, "close")

        assert marked == []

    def test_mark_read_no_callback_does_not_raise(self):
        notifier = DesktopNotifier(on_mark_read=None)
        notifier._notif_to_conv[10] = "conv-alice"

        notifier._on_action_invoked_signal(10, "mark-read")
        # must not raise

    # --- MainWindow wiring ---

    def test_main_window_mark_read_callback_calls_dbus_client(self, qtbot):
        """on_mark_read wired in MainWindow calls dbus_client.mark_conversation_read."""
        window = MainWindow()
        qtbot.addWidget(window)
        marked = []
        window._dbus_client.mark_conversation_read = lambda cid: marked.append(cid)

        window._on_notification_mark_read("conv-alice")

        assert marked == ["conv-alice"]

    def test_main_window_notifier_has_mark_read_wired(self, qtbot):
        """DesktopNotifier constructed with on_mark_read pointing to MainWindow method."""
        window = MainWindow()
        qtbot.addWidget(window)

        assert window._notifier._on_mark_read is not None
