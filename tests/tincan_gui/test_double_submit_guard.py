"""Tests: _on_send double-submit guard (tincan-x9zu3).

Guard: 'if (phone, text) in self._pending_sends: return' inserted in _on_send
before send_message_async, preventing duplicate outbound messages when the
user submits the same text rapidly while an async MAP send is still in-flight.

Coverage:
  §1 Guard — (phone, text) already pending blocks re-send
     - send_message_async not called again on duplicate submit
     - no second outbound bubble appended to thread_view
     - _pending_sends size unchanged on duplicate

  §2 Guard scope — only exact (phone, text) pair triggers; distinct args proceed
     - different text: send_message_async called for second submit
     - different phone: send_message_async called for second recipient

  §3 Guard released — after _on_send_accepted + event flush, re-send allowed
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QSystemTrayIcon

from tincan_gui.dbus_client import TincandClient
from tincan_gui.main import MainWindow
from tincan_gui.thread_view import BubbleType, MessageBubble, ThreadView


@pytest.fixture(autouse=True)
def _no_tray_show():
    with patch.object(QSystemTrayIcon, "show"):
        yield


def _make_window(qtbot, phone: str = "+15550001111") -> MainWindow:
    window = MainWindow()
    qtbot.addWidget(window)
    window._current_phone = phone
    window._current_phone_dialable = True
    return window


def _count_outbound(view: ThreadView) -> int:
    """Return the number of OUTBOUND MessageBubble widgets in the thread layout."""
    count = 0
    layout = view._messages_layout
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item is None:
            continue
        w = item.widget()
        if isinstance(w, MessageBubble) and w._data.bubble_type == BubbleType.OUTBOUND:
            count += 1
    return count


# ---------------------------------------------------------------------------
# §1 Guard — duplicate (phone, text) blocked while in-flight
# ---------------------------------------------------------------------------

class TestDoubleSubmitGuard:
    """Second _on_send with the same (phone, text) while pending must be a no-op."""

    @pytest.fixture(autouse=True)
    def _no_daemon(self, monkeypatch):
        monkeypatch.setattr(TincandClient, "get_status", lambda self: {})
        monkeypatch.setattr(TincandClient, "get_messages", lambda self, cid: [])
        monkeypatch.setattr(TincandClient, "list_conversations", lambda self: [])

    def test_duplicate_does_not_call_send_message_async_again(self, qtbot, monkeypatch):
        calls = []
        window = _make_window(qtbot)
        monkeypatch.setattr(
            window._dbus_client, "send_message_async",
            lambda to, body: calls.append((to, body)),
        )

        window._on_send("duplicate")
        window._on_send("duplicate")

        assert len(calls) == 1, f"send_message_async called {len(calls)}× — expected 1"

    def test_duplicate_does_not_append_second_bubble(self, qtbot, monkeypatch):
        window = _make_window(qtbot)
        monkeypatch.setattr(window._dbus_client, "send_message_async", lambda to, body: None)

        window._on_send("one bubble only")
        bubbles_after_first = _count_outbound(window._thread_view)
        window._on_send("one bubble only")
        bubbles_after_second = _count_outbound(window._thread_view)

        assert bubbles_after_first == 1
        assert bubbles_after_second == 1

    def test_pending_sends_size_unchanged_on_duplicate(self, qtbot, monkeypatch):
        window = _make_window(qtbot)
        monkeypatch.setattr(window._dbus_client, "send_message_async", lambda to, body: None)

        window._on_send("msg")
        size_after_first = len(window._pending_sends)
        window._on_send("msg")
        size_after_second = len(window._pending_sends)

        assert size_after_first == 1
        assert size_after_second == 1


# ---------------------------------------------------------------------------
# §2 Guard scope — only exact (phone, text) pair is guarded
# ---------------------------------------------------------------------------

class TestGuardScope:
    """Guard must only block sends where BOTH phone and text match."""

    @pytest.fixture(autouse=True)
    def _no_daemon(self, monkeypatch):
        monkeypatch.setattr(TincandClient, "get_status", lambda self: {})
        monkeypatch.setattr(TincandClient, "get_messages", lambda self, cid: [])
        monkeypatch.setattr(TincandClient, "list_conversations", lambda self: [])

    def test_different_text_bypasses_guard(self, qtbot, monkeypatch):
        calls = []
        window = _make_window(qtbot)
        monkeypatch.setattr(
            window._dbus_client, "send_message_async",
            lambda to, body: calls.append((to, body)),
        )

        window._on_send("first message")
        window._on_send("second message")

        assert len(calls) == 2

    def test_different_phone_bypasses_guard(self, qtbot, monkeypatch):
        calls = []
        window = _make_window(qtbot, "+15550001111")
        monkeypatch.setattr(
            window._dbus_client, "send_message_async",
            lambda to, body: calls.append((to, body)),
        )

        window._on_send("hello")
        window._current_phone = "+15550009999"
        window._on_send("hello")

        assert len(calls) == 2
        assert calls[0][0] == "+15550001111"
        assert calls[1][0] == "+15550009999"


# ---------------------------------------------------------------------------
# §3 Guard released after _on_send_accepted
# ---------------------------------------------------------------------------

class TestGuardReleasedAfterAccepted:
    """After _on_send_accepted + event flush, the same (phone, text) may re-send."""

    @pytest.fixture(autouse=True)
    def _no_daemon(self, monkeypatch):
        monkeypatch.setattr(TincandClient, "get_status", lambda self: {})
        monkeypatch.setattr(TincandClient, "get_messages", lambda self, cid: [])
        monkeypatch.setattr(TincandClient, "list_conversations", lambda self: [])

    def test_resend_allowed_after_accepted_and_event_flush(self, qtbot, monkeypatch):
        calls = []
        phone = "+15550001111"
        window = _make_window(qtbot, phone)
        monkeypatch.setattr(
            window._dbus_client, "send_message_async",
            lambda to, body: calls.append((to, body)),
        )

        text = "resend test"
        window._on_send(text)                            # adds (phone, text) to _pending_sends

        window._on_send_accepted(phone, text, "msg-id-1")  # schedules discard via singleShot(0)
        QCoreApplication.processEvents()                 # fires the timer, clears the guard

        window._on_send(text)                            # should proceed now

        assert len(calls) == 2, f"expected 2 send calls, got {len(calls)}"


# ---------------------------------------------------------------------------
# §4 Guard released after _on_send_failed
# ---------------------------------------------------------------------------

class TestGuardReleasedAfterFailed:
    """After _on_send_failed + event flush, the same (phone, text) may re-send."""

    @pytest.fixture(autouse=True)
    def _no_daemon(self, monkeypatch):
        monkeypatch.setattr(TincandClient, "get_status", lambda self: {})
        monkeypatch.setattr(TincandClient, "get_messages", lambda self, cid: [])
        monkeypatch.setattr(TincandClient, "list_conversations", lambda self: [])

    def test_resend_allowed_after_failed_and_event_flush(self, qtbot, monkeypatch):
        calls = []
        phone = "+15550001111"
        window = _make_window(qtbot, phone)
        monkeypatch.setattr(
            window._dbus_client, "send_message_async",
            lambda to, body: calls.append((to, body)),
        )

        text = "retry after fail"
        window._on_send(text)                        # adds (phone, text) to _pending_sends

        window._on_send_failed(phone, text)          # schedules discard via singleShot(0)
        QCoreApplication.processEvents()             # fires the timer, clears the guard

        window._on_send(text)                        # should proceed now

        assert len(calls) == 2, f"expected 2 send calls after failed+retry, got {len(calls)}"
