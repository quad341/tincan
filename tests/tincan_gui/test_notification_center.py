"""Tests: notification center — history tracking and dialog (tincan-ka57d).

Coverage:
  §1 DesktopNotifier.history() — entry tracking
     - SMS dispatch records a NotificationEntry(kind='sms')
     - ANCS app dispatch records a NotificationEntry(kind='app')
     - history() returns entries in insertion order
     - history is bounded at _HISTORY_SIZE

  §2 NotificationCenterDialog — rendering
     - shows "No notifications yet" when history is empty
     - shows one row per entry when history is non-empty
     - TitleBar exposes bell_button property
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSystemTrayIcon

from tincan_gui.notifications import _HISTORY_SIZE, DesktopNotifier, NotificationEntry


@pytest.fixture(autouse=True)
def _no_tray_show():
    with patch.object(QSystemTrayIcon, "show"):
        yield


# ---------------------------------------------------------------------------
# §1 DesktopNotifier.history()
# ---------------------------------------------------------------------------

class TestNotificationHistory:
    """DesktopNotifier records dispatched notifications in history()."""

    def _make_notifier(self) -> DesktopNotifier:
        n = DesktopNotifier()
        n._bus = MagicMock()  # prevent real dbus calls
        return n

    def test_history_empty_at_start(self):
        n = self._make_notifier()
        assert n.history() == []

    def test_sms_dispatch_adds_entry(self):
        n = self._make_notifier()
        msg = {
            "conversation_id": "c1",
            "display_name": "Alice",
            "body": "Hello there",
        }
        # Patch _should_notify to allow dispatch, and _notify to avoid dbus
        with patch.object(n, "_should_notify", return_value=True), \
             patch.object(n, "_notify"):
            n.dispatch(msg)

        h = n.history()
        assert len(h) == 1
        assert h[0].kind == "sms"
        assert h[0].sender == "Alice"
        assert h[0].body == "Hello there"
        assert h[0].conv_id == "c1"

    def test_app_dispatch_adds_entry(self):
        n = self._make_notifier()
        notif = {
            "app_id": "com.example.myapp",
            "title": "New alert",
            "subtitle": "",
            "body": "Something happened",
        }
        mock_settings = MagicMock()
        mock_settings.value.return_value = True
        with patch("tincan_gui._settings.app_settings", return_value=mock_settings), \
             patch.object(n, "_ensure_bus", return_value=MagicMock()):
            try:
                n.dispatch_app_notification(notif)
            except Exception:  # noqa: BLE001
                pass  # dbus may fail in tests; history is recorded before the call

        h = n.history()
        assert len(h) == 1
        assert h[0].kind == "app"
        assert h[0].sender == "com.example.myapp"
        assert "alert" in h[0].summary.lower() or h[0].summary == "New alert"

    def test_history_returns_entries_in_insertion_order(self):
        n = self._make_notifier()
        # Directly append to test ordering without dbus
        t = time.time()
        def _e(kind, sender, ts_offset=0):
            return NotificationEntry(ts=t + ts_offset, kind=kind, sender=sender,
                                     summary="x", body="", conv_id="")
        n._history.append(_e("sms", "Alice", 0))
        n._history.append(_e("app", "App", 1))
        n._history.append(_e("sms", "Bob", 2))

        senders = [e.sender for e in n.history()]
        assert senders == ["Alice", "App", "Bob"]

    def test_history_bounded_by_history_size(self):
        n = self._make_notifier()
        t = time.time()
        for i in range(_HISTORY_SIZE + 10):
            n._history.append(
                NotificationEntry(ts=t + i, kind="sms", sender=f"s{i}", summary="x",
                                  body="", conv_id="")
            )

        assert len(n.history()) == _HISTORY_SIZE
        # Oldest entries are evicted; newest are kept
        assert n.history()[-1].sender == f"s{_HISTORY_SIZE + 9}"


# ---------------------------------------------------------------------------
# §2 NotificationCenterDialog
# ---------------------------------------------------------------------------

class TestNotificationCenterDialog:
    """NotificationCenterDialog renders history correctly."""

    def _mock_notifier(self, entries: list[NotificationEntry]) -> MagicMock:
        n = MagicMock(spec=DesktopNotifier)
        n.history.return_value = entries
        return n

    def test_empty_state_shows_no_notifications_label(self, qtbot):
        from tincan_gui.notification_center import NotificationCenterDialog
        notifier = self._mock_notifier([])
        dlg = NotificationCenterDialog(notifier)
        qtbot.addWidget(dlg)
        dlg.show()

        # Find the "no notifications" label somewhere in the dialog
        from PySide6.QtWidgets import QLabel
        labels = dlg.findChildren(QLabel)
        texts = [lbl.text() for lbl in labels]
        assert any("No notifications" in t for t in texts), \
            f"Expected empty state label; found: {texts}"

    def test_entries_render_as_rows(self, qtbot):
        from tincan_gui.notification_center import NotificationCenterDialog, _NotifRow
        t = time.time()
        entries = [
            NotificationEntry(ts=t, kind="sms", sender="Alice", summary="Hello",
                              body="Hi there", conv_id="c1"),
            NotificationEntry(ts=t+1, kind="app", sender="Gmail", summary="New email",
                              body="You have mail", conv_id=""),
        ]
        notifier = self._mock_notifier(entries)
        dlg = NotificationCenterDialog(notifier)
        qtbot.addWidget(dlg)
        dlg.show()

        rows = dlg.findChildren(_NotifRow)
        assert len(rows) == 2

    def test_titlebar_exposes_bell_button(self, qtbot):
        from PySide6.QtWidgets import QToolButton

        from tincan_gui.main import TitleBar
        tb = TitleBar()
        qtbot.addWidget(tb)
        assert isinstance(tb.bell_button, QToolButton)
        assert tb.bell_button.toolTip() == "Notification center"


# ---------------------------------------------------------------------------
# §3 _NotifRow clickability (tincan-s0ira)
# ---------------------------------------------------------------------------

class TestNotifRowClickability:
    """_NotifRow click behavior: clicked signal, cursor, hover/base style restore."""

    def _make_entry(self, conv_id: str = "c1") -> NotificationEntry:
        return NotificationEntry(
            ts=0.0, kind="sms", sender="Alice", summary="Hi",
            body="Hello", conv_id=conv_id,
        )

    def test_mouse_press_with_conv_id_emits_clicked(self, qtbot):
        from tincan_gui.notification_center import _NotifRow
        entry = self._make_entry("c1")
        row = _NotifRow(entry, dark=False, conv_id="c1")
        qtbot.addWidget(row)
        row.show()

        received = []
        row.clicked.connect(received.append)
        qtbot.mouseClick(row, Qt.MouseButton.LeftButton)

        assert received == ["c1"]

    def test_mouse_press_without_conv_id_does_not_emit_clicked(self, qtbot):
        from tincan_gui.notification_center import _NotifRow
        entry = self._make_entry(conv_id="")
        row = _NotifRow(entry, dark=False, conv_id="")
        qtbot.addWidget(row)
        row.show()

        received = []
        row.clicked.connect(received.append)
        qtbot.mouseClick(row, Qt.MouseButton.LeftButton)

        assert received == []

    def test_pointing_hand_cursor_when_conv_id_set(self, qtbot):
        from tincan_gui.notification_center import _NotifRow
        entry = self._make_entry("c1")
        row = _NotifRow(entry, dark=False, conv_id="c1")
        qtbot.addWidget(row)

        assert row.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_no_pointing_hand_cursor_when_no_conv_id(self, qtbot):
        from tincan_gui.notification_center import _NotifRow
        entry = self._make_entry(conv_id="")
        row = _NotifRow(entry, dark=False, conv_id="")
        qtbot.addWidget(row)

        assert row.cursor().shape() != Qt.CursorShape.PointingHandCursor

    def test_enter_event_changes_style_when_conv_id_set(self, qtbot):
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QEnterEvent
        from PySide6.QtWidgets import QApplication

        from tincan_gui.notification_center import _NotifRow
        entry = self._make_entry("c1")
        row = _NotifRow(entry, dark=False, conv_id="c1")
        qtbot.addWidget(row)
        base_style = row.styleSheet()

        QApplication.sendEvent(row, QEnterEvent(QPointF(1, 1), QPointF(1, 1), QPointF(1, 1)))

        assert row.styleSheet() != base_style

    def test_enter_event_does_not_change_style_when_no_conv_id(self, qtbot):
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QEnterEvent
        from PySide6.QtWidgets import QApplication

        from tincan_gui.notification_center import _NotifRow
        entry = self._make_entry(conv_id="")
        row = _NotifRow(entry, dark=False, conv_id="")
        qtbot.addWidget(row)
        base_style = row.styleSheet()

        QApplication.sendEvent(row, QEnterEvent(QPointF(1, 1), QPointF(1, 1), QPointF(1, 1)))

        assert row.styleSheet() == base_style

    def test_leave_event_restores_base_style_after_hover(self, qtbot):
        from PySide6.QtCore import QEvent, QPointF
        from PySide6.QtGui import QEnterEvent
        from PySide6.QtWidgets import QApplication

        from tincan_gui.notification_center import _NotifRow
        entry = self._make_entry("c1")
        row = _NotifRow(entry, dark=False, conv_id="c1")
        qtbot.addWidget(row)
        base_style = row.styleSheet()

        QApplication.sendEvent(row, QEnterEvent(QPointF(1, 1), QPointF(1, 1), QPointF(1, 1)))
        assert row.styleSheet() != base_style, "hover style should differ from base"

        QApplication.sendEvent(row, QEvent(QEvent.Type.Leave))

        assert row.styleSheet() == base_style

    def test_on_select_callback_called_with_conv_id_on_click(self, qtbot):
        from tincan_gui.notification_center import NotificationCenterDialog, _NotifRow
        entries = [
            NotificationEntry(ts=0.0, kind="sms", sender="Alice", summary="Hi",
                              body="Hello", conv_id="c1"),
        ]
        notifier = MagicMock(spec=DesktopNotifier)
        notifier.history.return_value = entries

        selected = []
        dlg = NotificationCenterDialog(notifier, on_select=selected.append)
        qtbot.addWidget(dlg)
        dlg.show()

        rows = dlg.findChildren(_NotifRow)
        assert rows, "expected at least one _NotifRow"
        qtbot.mouseClick(rows[0], Qt.MouseButton.LeftButton)

        assert selected == ["c1"]

    def test_on_select_dialog_closed_on_row_click(self, qtbot):
        from tincan_gui.notification_center import NotificationCenterDialog, _NotifRow
        entries = [
            NotificationEntry(ts=0.0, kind="sms", sender="Alice", summary="Hi",
                              body="Hello", conv_id="c1"),
        ]
        notifier = MagicMock(spec=DesktopNotifier)
        notifier.history.return_value = entries

        dlg = NotificationCenterDialog(notifier, on_select=lambda _: None)
        qtbot.addWidget(dlg)
        dlg.show()

        rows = dlg.findChildren(_NotifRow)
        qtbot.mouseClick(rows[0], Qt.MouseButton.LeftButton)

        assert not dlg.isVisible()
