"""Tests: _on_send inline Qt D-Bus send path.
Bead: tincan-d7uj  (regression coverage for commit 0cf9b94)

Coverage:
  §1 _on_send — successful send
     - send_message called with correct phone and text
     - mark_last_send_failed NOT called
     - compose error NOT shown

  §2 _on_send — failed send (empty message_id)
     - mark_last_send_failed called
     - show_send_error called with original text

  §3 _on_send — no _current_phone
     - show_send_error called without calling send_message

  §4 _on_send — _pending_sends lifecycle
     - (phone, text) added before QTimer.singleShot(0) fires
     - (phone, text) removed after Qt event loop tick

  §5 ThreadView.mark_last_send_failed
     - no-op when no outbound bubble appended yet
     - updates last OUTBOUND bubble meta to include 'Failed'
     - targets last OUTBOUND, not latest inbound
     - load_thread() resets _last_outbound to None

  §6 MessageBubble.set_send_failed
     - meta label includes timestamp + 'Failed' after call
     - meta label shows 'Sent' before call
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from tincan_gui.dbus_client import TincandClient
from tincan_gui.main import MainWindow
from tincan_gui.thread_view import BubbleType, MessageBubble, MessageData, ThreadView


@pytest.fixture(autouse=True)
def _no_tray_show():
    with patch.object(QSystemTrayIcon, "show"):
        yield


def _make_window_with_phone(qtbot, phone: str = "+15550001111") -> MainWindow:
    """Create a MainWindow with a phone set and compose enabled."""
    window = MainWindow()
    qtbot.addWidget(window)
    window._current_phone = phone
    window._messages_ok = True
    window._sync_compose_state()
    return window


def _last_outbound(view: ThreadView) -> MessageBubble | None:
    """Return the last OUTBOUND MessageBubble in the view layout, or None."""
    layout = view._messages_layout
    for i in range(layout.count() - 1, -1, -1):
        item = layout.itemAt(i)
        if item is None:
            continue
        w = item.widget()
        if isinstance(w, MessageBubble) and w._data.bubble_type == BubbleType.OUTBOUND:
            return w
    return None


# ---------------------------------------------------------------------------
# §1 _on_send — successful send
# ---------------------------------------------------------------------------

class TestOnSendSuccess:
    """send_message returns a non-empty message_id — happy path."""

    def test_send_message_called_with_correct_phone(self, qtbot, monkeypatch):
        calls = []
        monkeypatch.setattr(
            TincandClient, "send_message",
            lambda self, to, body: calls.append((to, body)) or "msg-id-1",
        )
        window = _make_window_with_phone(qtbot, "+15550001111")

        window._on_send("Hello")

        assert calls == [("+15550001111", "Hello")]

    def test_send_message_called_with_correct_text(self, qtbot, monkeypatch):
        calls = []
        monkeypatch.setattr(
            TincandClient, "send_message",
            lambda self, to, body: calls.append((to, body)) or "msg-id-1",
        )
        window = _make_window_with_phone(qtbot)

        window._on_send("Correct text")

        assert calls[0][1] == "Correct text"

    def test_mark_last_send_failed_not_called(self, qtbot, monkeypatch):
        monkeypatch.setattr(TincandClient, "send_message", lambda self, to, body: "msg-id-1")
        window = _make_window_with_phone(qtbot)
        failed = []
        window._thread_view.mark_last_send_failed = lambda: failed.append(True)

        window._on_send("Success")

        assert failed == []

    def test_compose_error_bar_remains_hidden(self, qtbot, monkeypatch):
        monkeypatch.setattr(TincandClient, "send_message", lambda self, to, body: "msg-id-1")
        window = _make_window_with_phone(qtbot)

        window._on_send("Success")

        assert window._compose._error_bar.isHidden()


# ---------------------------------------------------------------------------
# §2 _on_send — failed send
# ---------------------------------------------------------------------------

class TestOnSendFailure:
    """send_message returns '' — bubble marked failed, compose error shown."""

    def test_mark_last_send_failed_called(self, qtbot, monkeypatch):
        monkeypatch.setattr(TincandClient, "send_message", lambda self, to, body: "")
        window = _make_window_with_phone(qtbot)
        failed = []
        window._thread_view.mark_last_send_failed = lambda: failed.append(True)

        window._on_send("Fail")

        assert failed == [True]

    def test_show_send_error_called_with_original_text(self, qtbot, monkeypatch):
        monkeypatch.setattr(TincandClient, "send_message", lambda self, to, body: "")
        window = _make_window_with_phone(qtbot)

        window._on_send("Fail this")

        assert not window._compose._error_bar.isHidden()
        assert window._compose._retry_text == "Fail this"


# ---------------------------------------------------------------------------
# §3 _on_send — no _current_phone
# ---------------------------------------------------------------------------

class TestOnSendNoPhone:
    """_current_phone is empty — show error, never call send_message."""

    def test_send_message_not_called(self, qtbot, monkeypatch):
        calls = []
        monkeypatch.setattr(
            TincandClient, "send_message",
            lambda self, to, body: calls.append((to, body)) or "",
        )
        window = MainWindow()
        qtbot.addWidget(window)
        window._current_phone = ""

        window._on_send("Orphan")

        assert calls == []

    def test_compose_error_shown_with_input_text(self, qtbot, monkeypatch):
        monkeypatch.setattr(TincandClient, "send_message", lambda self, to, body: "")
        window = MainWindow()
        qtbot.addWidget(window)
        window._current_phone = ""

        window._on_send("No phone text")

        assert not window._compose._error_bar.isHidden()
        assert window._compose._retry_text == "No phone text"


# ---------------------------------------------------------------------------
# §4 _on_send — _pending_sends lifecycle
# ---------------------------------------------------------------------------

class TestPendingSendsLifecycle:
    """(phone, text) guard: present immediately, cleared after event loop tick."""

    def test_pending_send_present_before_timer_fires(self, qtbot, monkeypatch):
        monkeypatch.setattr(TincandClient, "send_message", lambda self, to, body: "msg-id-1")
        phone = "+15550002222"
        window = _make_window_with_phone(qtbot, phone)

        window._on_send("guard text")

        assert (phone, "guard text") in window._pending_sends

    def test_pending_send_removed_after_event_loop_tick(self, qtbot, monkeypatch):
        monkeypatch.setattr(TincandClient, "send_message", lambda self, to, body: "msg-id-1")
        phone = "+15550002222"
        window = _make_window_with_phone(qtbot, phone)

        window._on_send("guard text")
        QApplication.processEvents()

        assert (phone, "guard text") not in window._pending_sends


# ---------------------------------------------------------------------------
# §5 ThreadView.mark_last_send_failed
# ---------------------------------------------------------------------------

class TestMarkLastSendFailed:
    """mark_last_send_failed targets the last OUTBOUND bubble."""

    def test_no_op_when_no_outbound_appended(self, qtbot):
        view = ThreadView()
        qtbot.addWidget(view)

        view.mark_last_send_failed()  # must not raise

    def test_updates_last_outbound_bubble_meta(self, qtbot):
        view = ThreadView()
        qtbot.addWidget(view)
        view.append_message(MessageData(BubbleType.OUTBOUND, "Sent", "", "10:00"))

        view.mark_last_send_failed()

        bubble = _last_outbound(view)
        assert bubble is not None
        assert "Failed" in bubble._meta_label.text()

    def test_targets_outbound_not_trailing_inbound(self, qtbot):
        view = ThreadView()
        qtbot.addWidget(view)
        view.append_message(MessageData(BubbleType.OUTBOUND, "Sent", "", "10:00"))
        view.append_message(MessageData(BubbleType.INBOUND, "Reply", "Alice", "10:01"))

        view.mark_last_send_failed()

        bubble = _last_outbound(view)
        assert bubble is not None
        assert "Failed" in bubble._meta_label.text()

    def test_load_thread_resets_last_outbound_to_none(self, qtbot):
        view = ThreadView()
        qtbot.addWidget(view)
        view.append_message(MessageData(BubbleType.OUTBOUND, "Old send", "", "09:59"))

        view.load_thread("Bob", "+15550003333", [], "SMS")

        assert view._last_outbound is None


# ---------------------------------------------------------------------------
# §6 MessageBubble.set_send_failed
# ---------------------------------------------------------------------------

class TestMessageBubbleSetSendFailed:
    """set_send_failed marks the meta label with timestamp + 'Failed'."""

    def test_meta_label_includes_failed_after_call(self, qtbot):
        bubble = MessageBubble(MessageData(BubbleType.OUTBOUND, "Hi", "", "10:32"))
        qtbot.addWidget(bubble)

        bubble.set_send_failed()

        assert "Failed" in bubble._meta_label.text()

    def test_meta_label_includes_original_timestamp(self, qtbot):
        bubble = MessageBubble(MessageData(BubbleType.OUTBOUND, "Hi", "", "10:32"))
        qtbot.addWidget(bubble)

        bubble.set_send_failed()

        assert "10:32" in bubble._meta_label.text()

    def test_meta_label_shows_sent_before_failure(self, qtbot):
        bubble = MessageBubble(MessageData(BubbleType.OUTBOUND, "Hi", "", "10:32"))
        qtbot.addWidget(bubble)

        assert "Sent" in bubble._meta_label.text()
        assert "Failed" not in bubble._meta_label.text()
