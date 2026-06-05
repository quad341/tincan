"""Behavior tests: conversation-list preview updates on send (tincan-h9t9k).

After the user sends a message, the conversation-list preview must immediately
reflect that message (direction=outbound, body=text sent) rather than staying
on the last received message.  iOS MAP sent folder is always empty so the daemon
never pushes a ConversationUpdated signal for outbound messages; the GUI must
update the preview locally on send.

Coverage:
  - Sending a message updates the preview text to the sent body.
  - Preview direction is set to 'outbound' (shows 'You: …' prefix in UI).
  - Preview update fires even when the daemon hasn't acked the send yet.
  - Preview reflects the most-recent send when sending multiple messages.
  - Preview is not updated for a non-existent conversation (no crash).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QSystemTrayIcon

from tincan_gui.conversation_list import ConversationData
from tincan_gui.dbus_client import TincandClient
from tincan_gui.main import MainWindow


@pytest.fixture(autouse=True)
def _no_tray_show():
    with patch.object(QSystemTrayIcon, "show"):
        yield


@pytest.fixture(autouse=True)
def _no_live_daemon(monkeypatch):
    monkeypatch.setattr(TincandClient, "get_status", lambda self: {})
    monkeypatch.setattr(TincandClient, "get_messages", lambda self, cid: [])
    monkeypatch.setattr(TincandClient, "list_conversations", lambda self: [])


def _window_with_conversation(qtbot, conv_id="+15550001111", preview="hey") -> MainWindow:
    """Create a MainWindow with one conversation loaded and selected."""
    window = MainWindow()
    qtbot.addWidget(window)
    # Inject a conversation directly (bypasses daemon)
    data = ConversationData(
        id=conv_id, name="Alice", phone=conv_id,
        preview=preview, timestamp="09:00", preview_direction="inbound",
    )
    window._conversations_by_id[conv_id] = data
    window._conv_list.load_conversations([data])
    window._current_phone = conv_id
    window._current_phone_dialable = True
    # Silence async send — we're not testing D-Bus here
    window._dbus_client.send_message_async = MagicMock()
    return window


class TestPreviewUpdatesOnSend:
    """Conversation-list preview reflects sent message immediately (tincan-h9t9k)."""

    def test_preview_text_updated_to_sent_body(self, qtbot):
        window = _window_with_conversation(qtbot)

        window._on_send("Are you free?")

        updated = window._conversations_by_id["+15550001111"]
        assert updated.preview == "Are you free?"

    def test_preview_direction_set_to_outbound(self, qtbot):
        window = _window_with_conversation(qtbot, preview="original inbound")

        window._on_send("my reply")

        updated = window._conversations_by_id["+15550001111"]
        assert updated.preview_direction == "outbound"

    def test_preview_updated_before_daemon_ack(self, qtbot):
        """Preview fires immediately on send, not waiting for send_accepted signal."""
        window = _window_with_conversation(qtbot)
        # Make async send a no-op (no ack fired in this test)
        updates_seen = []
        original_update_item = window._conv_list.update_item
        window._conv_list.update_item = lambda cid, data: (
            updates_seen.append((cid, data)),
            original_update_item(cid, data),
        )

        window._on_send("hello before ack")

        assert any(d.preview == "hello before ack" for _, d in updates_seen), (
            "update_item must be called with the sent body before daemon acks"
        )

    def test_most_recent_send_is_the_preview(self, qtbot):
        window = _window_with_conversation(qtbot)

        window._on_send("first message")
        window._on_send("second message")

        updated = window._conversations_by_id["+15550001111"]
        assert updated.preview == "second message"

    def test_unread_cleared_on_send(self, qtbot):
        window = _window_with_conversation(qtbot)
        window._conversations_by_id["+15550001111"] = ConversationData(
            id="+15550001111", name="Alice", phone="+15550001111",
            preview="hey", timestamp="09:00", unread=True, unread_count=2,
        )

        window._on_send("reply")

        updated = window._conversations_by_id["+15550001111"]
        assert updated.unread is False
        assert updated.unread_count == 0

    def test_no_crash_when_conversation_not_in_dict(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window._current_phone = "+15550009999"
        window._current_phone_dialable = True
        window._dbus_client.send_message_async = MagicMock()
        # _conversations_by_id is empty — should not crash
        window._on_send("orphan send")

    def test_conv_list_update_item_called_with_correct_id(self, qtbot):
        window = _window_with_conversation(qtbot, conv_id="+18005551234")
        calls = []
        window._conv_list.update_item = lambda cid, data: calls.append((cid, data))

        window._on_send("testing preview")

        assert len(calls) == 1
        cid, data = calls[0]
        assert cid == "+18005551234"
        assert data.preview == "testing preview"
