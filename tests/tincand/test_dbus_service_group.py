"""Tests: TincanService group D-Bus methods and Conversation group fields.
Bead: tincan-bnody

Coverage:
  §1 SendMessageToRecipients — 0 or 1 recipients → InvalidArgs
  §2 SendMessageToRecipients — invalid phone → InvalidArgs
  §3 SendMessageToRecipients valid, flag disabled — stores conv, returns conv_id, no send_group_message
  §4 SendMessageToRecipients valid, flag enabled — calls send_group_message with normalized phones
  §5 SendMessage — conv_id in _group_participants → routes to send_group_message
  §6 SendMessage — phone not in group map → falls through to 1:1 send_message path
  §7 GetConversationParticipants — known conv_id → returns stored list
  §8 GetConversationParticipants — unknown conv_id → returns [] without error
  §9 Conversation.to_dbus() — is_group and group_name present, correct dbus types

No D-Bus infrastructure needed — TincanService is instantiated with a mocked bus.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import dbus
import dbus.service
import pytest

from tincand.dbus_service import Conversation, TincanService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def service():
    """TincanService with mocked D-Bus registration — no real bus required."""
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


@pytest.fixture
def connected_service(service):
    """Service in connected state with a mock backend that can send_group_message."""
    service._connected = True
    mock_backend = MagicMock()
    mock_backend.send_group_message.return_value = "/obex/transfer/1"
    service._backend = mock_backend
    return service


# ---------------------------------------------------------------------------
# §1 SendMessageToRecipients — insufficient recipients
# ---------------------------------------------------------------------------

class TestSendMessageToRecipientsInsufficientRecipients:
    """0 or 1 phone numbers → dbus InvalidArgs exception."""

    def test_zero_recipients_raises_invalid_args(self, connected_service):
        with pytest.raises(dbus.exceptions.DBusException) as exc_info:
            connected_service.SendMessageToRecipients([], "")
        assert "InvalidArg" in str(exc_info.value)

    def test_one_recipient_raises_invalid_args(self, connected_service):
        with pytest.raises(dbus.exceptions.DBusException) as exc_info:
            connected_service.SendMessageToRecipients(["+15550101234"], "")
        assert "InvalidArg" in str(exc_info.value)


# ---------------------------------------------------------------------------
# §2 SendMessageToRecipients — invalid phone
# ---------------------------------------------------------------------------

class TestSendMessageToRecipientsInvalidPhone:
    """Non-phone strings in the recipients list → InvalidArgs."""

    def test_empty_phone_string_raises_invalid_args(self, connected_service):
        with pytest.raises(dbus.exceptions.DBusException) as exc_info:
            connected_service.SendMessageToRecipients(["not-a-phone", "+15550101234"], "")
        assert "InvalidArg" in str(exc_info.value)


# ---------------------------------------------------------------------------
# §3 SendMessageToRecipients valid, flag disabled
# ---------------------------------------------------------------------------

class TestSendMessageToRecipientsGroupSendDisabled:
    """Flag disabled: conv stored and conv_id returned, send_group_message NOT called."""

    def test_returns_conv_id_string(self, connected_service):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("TINCAN_GROUP_SEND_ENABLED", None)
            result = connected_service.SendMessageToRecipients(
                ["+15550101234", "+15550105678"], ""
            )
        assert isinstance(result, str)
        assert result != ""

    def test_conversation_stored(self, connected_service):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("TINCAN_GROUP_SEND_ENABLED", None)
            conv_id = connected_service.SendMessageToRecipients(
                ["+15550101234", "+15550105678"], ""
            )
        assert conv_id in connected_service._conversations

    def test_send_group_message_not_called(self, connected_service):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("TINCAN_GROUP_SEND_ENABLED", None)
            connected_service.SendMessageToRecipients(
                ["+15550101234", "+15550105678"], ""
            )
        connected_service._backend.send_group_message.assert_not_called()


# ---------------------------------------------------------------------------
# §4 SendMessageToRecipients valid, flag enabled
# ---------------------------------------------------------------------------

class TestSendMessageToRecipientsGroupSendEnabled:
    """Flag enabled: send_group_message called with normalized phone list."""

    def test_send_group_message_called_with_two_phones(self, connected_service):
        with patch.dict(os.environ, {"TINCAN_GROUP_SEND_ENABLED": "1"}):
            connected_service.SendMessageToRecipients(
                ["+15550101234", "+15550105678"], ""
            )
        connected_service._backend.send_group_message.assert_called_once()
        phones_arg = connected_service._backend.send_group_message.call_args[0][0]
        assert len(phones_arg) == 2

    def test_phones_are_normalized_in_call(self, connected_service):
        with patch.dict(os.environ, {"TINCAN_GROUP_SEND_ENABLED": "1"}):
            connected_service.SendMessageToRecipients(
                ["+15550101234", "+15550105678"], ""
            )
        phones_arg = connected_service._backend.send_group_message.call_args[0][0]
        # +15550101234 → 5550101234 (normalized)
        assert "+15550101234" not in phones_arg
        assert "5550101234" in phones_arg


# ---------------------------------------------------------------------------
# §5 SendMessage — group conv_id routes to send_group_message
# ---------------------------------------------------------------------------

class TestSendMessageGroupRouting:
    """SendMessage(conv_id, body) where conv_id is in _group_participants
    delegates to backend.send_group_message, not backend.send_message.
    """

    def test_send_message_calls_send_group_message_for_group_conv(self, connected_service):
        connected_service._group_participants = {
            "group-abc": ["5550101234", "5550105678"],
        }
        connected_service._conversations["group-abc"] = Conversation(
            id="group-abc",
            display_name="Group",
        )
        connected_service.SendMessage("group-abc", "hello group")
        connected_service._backend.send_group_message.assert_called()

    def test_send_group_message_not_called_for_1to1(self, connected_service):
        """Regular 1:1 conv_id falls through to send_message."""
        connected_service._group_participants = {}
        connected_service.SendMessage("+15550101234", "hello")
        connected_service._backend.send_group_message.assert_not_called()
        connected_service._backend.send_message.assert_called()


# ---------------------------------------------------------------------------
# §6 SendMessage — phone not in group map falls through to 1:1 path
# ---------------------------------------------------------------------------

class TestSendMessageOneToOneFallthrough:
    """Unknown conv_id or phone not in _group_participants: use send_message."""

    def test_unknown_phone_calls_send_message(self, connected_service):
        connected_service._group_participants = {}
        connected_service.SendMessage("+15550101234", "hey")
        connected_service._backend.send_message.assert_called()

    def test_send_group_message_not_called_for_unknown_phone(self, connected_service):
        connected_service._group_participants = {}
        connected_service.SendMessage("+15550101234", "hey")
        connected_service._backend.send_group_message.assert_not_called()


# ---------------------------------------------------------------------------
# §7 GetConversationParticipants — known conv_id
# ---------------------------------------------------------------------------

class TestGetConversationParticipantsKnown:
    """Known conv_id returns the stored participant list."""

    def test_returns_stored_participants(self, connected_service):
        connected_service._group_participants = {
            "group-xyz": ["5550101234", "5550105678"],
        }
        result = connected_service.GetConversationParticipants("group-xyz")
        assert sorted(result) == sorted(["5550101234", "5550105678"])

    def test_returns_list_type(self, connected_service):
        connected_service._group_participants = {
            "group-xyz": ["5550101234"],
        }
        result = connected_service.GetConversationParticipants("group-xyz")
        assert isinstance(result, (list, dbus.Array))


# ---------------------------------------------------------------------------
# §8 GetConversationParticipants — unknown conv_id
# ---------------------------------------------------------------------------

class TestGetConversationParticipantsUnknown:
    """Unknown conv_id returns [] without raising."""

    def test_unknown_conv_id_returns_empty_list(self, connected_service):
        connected_service._group_participants = {}
        result = connected_service.GetConversationParticipants("no-such-id")
        assert list(result) == []

    def test_does_not_raise_for_unknown_id(self, connected_service):
        connected_service._group_participants = {}
        connected_service.GetConversationParticipants("missing")  # must not raise


# ---------------------------------------------------------------------------
# §9 Conversation.to_dbus() — is_group and group_name fields
# ---------------------------------------------------------------------------

class TestConversationToDbuGroupFields:
    """to_dbus() exposes is_group (bool/dbus.Boolean) and group_name (str/dbus.String)."""

    def test_to_dbus_has_is_group_key(self):
        conv = Conversation(id="g1", display_name="Group", is_group=True)
        d = conv.to_dbus()
        assert "is_group" in d

    def test_is_group_true_preserved_in_to_dbus(self):
        conv = Conversation(id="g1", display_name="Group", is_group=True)
        d = conv.to_dbus()
        assert bool(d["is_group"]) is True

    def test_is_group_false_by_default(self):
        conv = Conversation(id="c1", display_name="Alice")
        d = conv.to_dbus()
        assert bool(d.get("is_group", False)) is False

    def test_to_dbus_has_group_name_key(self):
        conv = Conversation(id="g1", display_name="Group", group_name="Family")
        d = conv.to_dbus()
        assert "group_name" in d

    def test_group_name_value_preserved(self):
        conv = Conversation(id="g1", display_name="Group", group_name="Family")
        d = conv.to_dbus()
        assert str(d["group_name"]) == "Family"

    def test_is_group_dbus_type_is_boolean_or_bool(self):
        conv = Conversation(id="g1", display_name="Group", is_group=True)
        d = conv.to_dbus()
        # dbus.Boolean is a subclass of int; bool is also acceptable
        assert isinstance(d["is_group"], (dbus.Boolean, bool))
