"""Tests: Conversation dict fields — last_message_preview and unread_count.
Bead: tincan-tv8  (parent: tincan-em8)

Coverage (additional to tincan-a3n and tincan-f0e):
  - Daemon ListConversations() includes last_message_preview and unread_count in each dict.
  - Daemon ConversationUpdated signal dict includes both new fields.
  - GUI _apply_preview: outbound direction → 'You: ' prefix, 30-char body truncation.
  - GUI ConversationItem.accessibleName includes preview text and unread badge string.
"""
from __future__ import annotations

import html as _html
import re
from unittest.mock import MagicMock, patch

import dbus
import dbus.service
import pytest

from tincan_gui.conversation_list import ConversationData, ConversationItem


def _label_plain(label) -> str:
    """Strip HTML tags, unescape entities, and remove zero-width spaces."""
    t = re.sub(r"<[^>]+>", "", label.text())
    t = _html.unescape(t)
    return t.replace("​", "")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_data(**overrides) -> ConversationData:
    defaults = {
        "id": "c1",
        "name": "Alice",
        "phone": "+1 555-0100",
        "preview": "",
        "timestamp": "10:00",
        "unread": False,
        "unread_count": 0,
    }
    defaults.update(overrides)
    return ConversationData(**defaults)


def _make_service():
    """TincanService with mocked D-Bus bus."""
    from tincand.dbus_service import TincanService

    with patch("dbus.service.BusName", return_value=MagicMock()), \
         patch.object(dbus.service.Object, "__init__", return_value=None):
        svc = TincanService(MagicMock())
    svc.Connected = MagicMock()
    svc.Disconnected = MagicMock()
    svc.CapabilityChanged = MagicMock()
    svc.MessageReceived = MagicMock()
    svc.MessageSent = MagicMock()
    svc.ConversationUpdated = MagicMock()
    return svc


# ---------------------------------------------------------------------------
# §1 Daemon: ListConversations() includes both new fields
# ---------------------------------------------------------------------------

class TestListConversationsFields:
    """ListConversations() dicts always include last_message_preview and unread_count."""

    @pytest.fixture
    def connected_svc_with_conv(self):
        from tincand.dbus_service import Conversation
        svc = _make_service()
        svc._connected = True
        svc._conversations["c1"] = Conversation(
            id="c1",
            display_name="Alice",
            last_message_at="2024-01-01T10:00:00",
            last_message_preview="Hey there",
            unread_count=2,
        )
        return svc

    def test_list_conversations_includes_last_message_preview(self, connected_svc_with_conv):
        convs = connected_svc_with_conv.ListConversations()
        assert len(convs) == 1
        assert "last_message_preview" in convs[0]

    def test_list_conversations_preview_value_matches(self, connected_svc_with_conv):
        convs = connected_svc_with_conv.ListConversations()
        assert str(convs[0]["last_message_preview"]) == "Hey there"

    def test_list_conversations_includes_unread_count(self, connected_svc_with_conv):
        convs = connected_svc_with_conv.ListConversations()
        assert "unread_count" in convs[0]

    def test_list_conversations_unread_count_value_matches(self, connected_svc_with_conv):
        convs = connected_svc_with_conv.ListConversations()
        assert int(convs[0]["unread_count"]) == 2

    def test_list_conversations_unread_count_is_uint32(self, connected_svc_with_conv):
        convs = connected_svc_with_conv.ListConversations()
        assert isinstance(convs[0]["unread_count"], dbus.UInt32)

    def test_list_conversations_preview_is_empty_string_when_no_messages(self):
        from tincand.dbus_service import Conversation
        svc = _make_service()
        svc._connected = True
        svc._conversations["c1"] = Conversation(id="c1", display_name="Alice")
        convs = svc.ListConversations()
        assert str(convs[0]["last_message_preview"]) == ""


# ---------------------------------------------------------------------------
# §2 Daemon: ConversationUpdated signal includes both fields
# ---------------------------------------------------------------------------

class TestConversationUpdatedSignalContent:
    """on_message_received emits ConversationUpdated with preview and unread_count."""

    @pytest.fixture
    def svc(self):
        from tincand.dbus_service import Conversation
        s = _make_service()
        s._connected = True
        s._conversations["conv-1"] = Conversation(
            id="conv-1",
            display_name="Alice",
            last_message_at="2024-01-01T10:00:00",
            last_message_preview="",
            unread_count=0,
        )
        return s

    def test_conversation_updated_dict_includes_last_message_preview(self, svc):
        svc.on_message_received({
            "conversation_id": "conv-1",
            "direction": "inbound",
            "status": "unread",
            "body": "New message",
            "timestamp": "2024-01-01T11:00:00",
        })
        args = svc.ConversationUpdated.call_args[0][0]
        assert "last_message_preview" in args

    def test_conversation_updated_dict_includes_unread_count(self, svc):
        svc.on_message_received({
            "conversation_id": "conv-1",
            "direction": "inbound",
            "status": "unread",
            "body": "New message",
            "timestamp": "2024-01-01T11:00:00",
        })
        args = svc.ConversationUpdated.call_args[0][0]
        assert "unread_count" in args


# ---------------------------------------------------------------------------
# §3 GUI: outbound preview — 'You: ' prefix and 30-char body truncation
# ---------------------------------------------------------------------------

class TestOutboundPreview:
    """_apply_preview with preview_direction='outbound' uses 'You: ' prefix."""

    def _make_outbound(self, preview: str) -> ConversationItem:
        data = _make_data(preview=preview)
        data.preview_direction = "outbound"  # type: ignore[attr-defined]
        return ConversationItem(data)

    def test_outbound_30_char_preview_shows_full_text_with_prefix(self, qtbot):
        preview = "a" * 30
        item = self._make_outbound(preview)
        qtbot.addWidget(item)
        assert _label_plain(item._preview_label) == f"You: {preview}"

    def test_outbound_30_char_preview_has_no_ellipsis(self, qtbot):
        preview = "a" * 30
        item = self._make_outbound(preview)
        qtbot.addWidget(item)
        assert "…" not in item._preview_label.text()

    def test_outbound_31_char_preview_truncated_with_you_prefix(self, qtbot):
        preview = "a" * 31
        item = self._make_outbound(preview)
        qtbot.addWidget(item)
        assert _label_plain(item._preview_label) == "You: " + "a" * 30 + "…"

    def test_outbound_empty_preview_shows_em_dash_not_you_prefix(self, qtbot):
        # Empty preview falls through to the placeholder branch regardless of direction
        data = _make_data(preview="")
        data.preview_direction = "outbound"  # type: ignore[attr-defined]
        item = ConversationItem(data)
        qtbot.addWidget(item)
        assert item._preview_label.text() == "—"


# ---------------------------------------------------------------------------
# §4 GUI: ConversationItem accessibleName includes preview and unread text
# ---------------------------------------------------------------------------

class TestConversationItemAccessibleName:
    """accessibleName includes the conversation name, preview text, and unread count."""

    def test_accessible_name_includes_conversation_name(self, qtbot):
        item = ConversationItem(_make_data(name="Alice", preview="Hello", timestamp="10:00"))
        qtbot.addWidget(item)
        assert "Alice" in item.accessibleName()

    def test_accessible_name_includes_preview_text(self, qtbot):
        item = ConversationItem(_make_data(name="Alice", preview="Hey there", timestamp="10:00"))
        qtbot.addWidget(item)
        assert "Hey there" in item.accessibleName()

    def test_accessible_name_includes_unread_count_for_unread_conversation(self, qtbot):
        item = ConversationItem(_make_data(name="Alice", preview="Hi", unread_count=3))
        qtbot.addWidget(item)
        assert "Unread: 3" in item.accessibleName()

    def test_accessible_name_includes_unread_9plus_for_large_count(self, qtbot):
        item = ConversationItem(_make_data(name="Alice", preview="Hi", unread_count=10))
        qtbot.addWidget(item)
        assert "Unread: 9+" in item.accessibleName()

    def test_accessible_name_no_unread_text_when_count_zero(self, qtbot):
        item = ConversationItem(_make_data(name="Alice", preview="Hi", unread_count=0))
        qtbot.addWidget(item)
        assert "Unread" not in item.accessibleName()
