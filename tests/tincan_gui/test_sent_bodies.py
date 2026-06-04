"""Tests: _sent_bodies duplicate outbound suppression.
Bead: tincan-1nt7  (commit e8291ea)

Coverage:
  §1 _sent_bodies population
     - successful send: body added to _sent_bodies[phone]
     - failed send (empty message_id): body NOT added to _sent_bodies

  §2 _on_message_received suppression
     - outbound message with body in _sent_bodies[conv_id] -> NOT appended to thread
     - outbound message with body NOT in _sent_bodies -> appended normally
     - inbound message with body matching _sent_bodies -> NOT suppressed (direction guard)
     - _sent_bodies check only fires when _pending_sends check already passed

  §3 _on_daemon_disconnected
     - _sent_bodies cleared on disconnect
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QSystemTrayIcon

from tincan_gui.dbus_client import TincandClient
from tincan_gui.main import MainWindow
from tincan_gui.thread_view import BubbleType, MessageBubble, ThreadView


@pytest.fixture(autouse=True)
def _no_tray_show():
    with patch.object(QSystemTrayIcon, "show"):
        yield


def _make_window_with_phone(qtbot, phone: str = "+15550001111") -> MainWindow:
    window = MainWindow()
    qtbot.addWidget(window)
    window._current_phone = phone
    window._messages_ok = True
    window._sync_compose_state()
    return window


def _bubble_count(view: ThreadView) -> int:
    layout = view._messages_layout
    return sum(
        1 for i in range(layout.count())
        if isinstance(layout.itemAt(i).widget(), MessageBubble)
    )


# ---------------------------------------------------------------------------
# §1 _sent_bodies population
# ---------------------------------------------------------------------------

class TestSentBodiesPopulation:
    """_on_send populates _sent_bodies on success, not on failure."""

    def test_successful_send_adds_body_to_sent_bodies(self, qtbot, monkeypatch):
        monkeypatch.setattr(TincandClient, "send_message", lambda self, to, body: "msg-id-1")
        phone = "+15550001111"
        window = _make_window_with_phone(qtbot, phone)

        window._on_send("Hello there")

        assert "Hello there" in window._sent_bodies.get(phone, set())

    def test_successful_send_uses_phone_as_key(self, qtbot, monkeypatch):
        monkeypatch.setattr(TincandClient, "send_message", lambda self, to, body: "msg-id-1")
        phone = "+15550002222"
        window = _make_window_with_phone(qtbot, phone)

        window._on_send("Keyed message")

        assert phone in window._sent_bodies

    def test_multiple_sends_accumulate_in_same_key(self, qtbot, monkeypatch):
        monkeypatch.setattr(TincandClient, "send_message", lambda self, to, body: "msg-id-1")
        phone = "+15550001111"
        window = _make_window_with_phone(qtbot, phone)

        window._on_send("First")
        window._on_send("Second")

        assert window._sent_bodies[phone] == {"First", "Second"}

    def test_failed_send_does_not_add_body(self, qtbot, monkeypatch):
        monkeypatch.setattr(TincandClient, "send_message", lambda self, to, body: "")
        window = _make_window_with_phone(qtbot)

        window._on_send("Failed message")

        assert not any("Failed message" in v for v in window._sent_bodies.values())

    def test_sent_bodies_empty_initially(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)

        assert window._sent_bodies == {}


# ---------------------------------------------------------------------------
# §2 _on_message_received suppression
# ---------------------------------------------------------------------------

class TestOnMessageReceivedSuppression:
    """_on_message_received skips outbound echoes already in _sent_bodies."""

    def _inject_message(self, window: MainWindow, **fields) -> None:
        defaults = {
            "direction": "outbound",
            "body": "Echo",
            "sender": "",
            "timestamp": "10:00",
            "conversation_id": window._current_phone,
        }
        defaults.update(fields)
        window._on_message_received(defaults)

    def test_outbound_body_in_sent_bodies_not_appended(self, qtbot, monkeypatch):
        monkeypatch.setattr(TincandClient, "send_message", lambda self, to, body: "msg-id-1")
        phone = "+15550001111"
        window = _make_window_with_phone(qtbot, phone)
        window._on_send("Suppress me")
        window._pending_sends.clear()  # simulate timer fire; isolate _sent_bodies path
        count_before = _bubble_count(window._thread_view)

        self._inject_message(window, body="Suppress me", conversation_id=phone)

        assert _bubble_count(window._thread_view) == count_before

    def test_outbound_body_not_in_sent_bodies_appended(self, qtbot, monkeypatch):
        monkeypatch.setattr(TincandClient, "send_message", lambda self, to, body: "msg-id-1")
        phone = "+15550001111"
        window = _make_window_with_phone(qtbot, phone)
        window._on_send("Some text")
        # Clear _pending_sends directly instead of processEvents() to avoid
        # live D-Bus callbacks mutating window state during event drain.
        window._pending_sends.clear()
        count_before = _bubble_count(window._thread_view)

        self._inject_message(window, body="Different text", conversation_id=phone)

        assert _bubble_count(window._thread_view) == count_before + 1

    def test_inbound_body_matching_sent_bodies_still_appended(self, qtbot, monkeypatch):
        monkeypatch.setattr(TincandClient, "send_message", lambda self, to, body: "msg-id-1")
        phone = "+15550001111"
        window = _make_window_with_phone(qtbot, phone)
        window._on_send("Same text")
        window._pending_sends.clear()
        count_before = _bubble_count(window._thread_view)

        self._inject_message(
            window, direction="inbound", body="Same text",
            sender="Alice", conversation_id=phone,
        )

        assert _bubble_count(window._thread_view) == count_before + 1

    def test_outbound_in_sent_bodies_suppression_uses_conv_id_not_phone(self, qtbot, monkeypatch):
        """_sent_bodies keyed by phone; conv_id in message must match."""
        monkeypatch.setattr(TincandClient, "send_message", lambda self, to, body: "msg-id-1")
        phone = "+15550001111"
        other_conv = "+15559990000"
        window = _make_window_with_phone(qtbot, phone)
        window._on_send("Cross conv")
        window._pending_sends.clear()
        # Inject with a DIFFERENT conv_id — should NOT be suppressed
        window._current_phone = other_conv
        count_before = _bubble_count(window._thread_view)

        self._inject_message(window, body="Cross conv", conversation_id=other_conv)

        assert _bubble_count(window._thread_view) == count_before + 1

    def test_pending_sends_check_fires_before_sent_bodies(self, qtbot, monkeypatch):
        """A body in _pending_sends is suppressed even if also absent from _sent_bodies."""
        monkeypatch.setattr(TincandClient, "send_message", lambda self, to, body: "msg-id-1")
        phone = "+15550001111"
        window = _make_window_with_phone(qtbot, phone)
        # Manually inject into _pending_sends without _sent_bodies
        window._pending_sends.add((phone, "Guard text"))
        count_before = _bubble_count(window._thread_view)

        self._inject_message(window, body="Guard text", conversation_id=phone)

        assert _bubble_count(window._thread_view) == count_before


# ---------------------------------------------------------------------------
# §3 _on_daemon_disconnected
# ---------------------------------------------------------------------------

class TestSentBodiesDisconnect:
    """_on_daemon_disconnected clears _sent_bodies."""

    def test_sent_bodies_cleared_on_disconnect(self, qtbot, monkeypatch):
        monkeypatch.setattr(TincandClient, "send_message", lambda self, to, body: "msg-id-1")
        phone = "+15550001111"
        window = _make_window_with_phone(qtbot, phone)
        window._on_send("Will be cleared")
        assert window._sent_bodies  # sanity: non-empty before disconnect

        window._on_daemon_disconnected()

        assert window._sent_bodies == {}

    def test_sent_bodies_starts_empty_after_reconnect(self, qtbot, monkeypatch):
        monkeypatch.setattr(TincandClient, "send_message", lambda self, to, body: "msg-id-1")
        monkeypatch.setattr(TincandClient, "get_status", lambda self: {})
        phone = "+15550001111"
        window = _make_window_with_phone(qtbot, phone)
        window._on_send("Pre-disconnect")
        window._on_daemon_disconnected()

        window._on_daemon_connected("AA:BB:CC:DD:EE:FF")

        assert window._sent_bodies == {}
