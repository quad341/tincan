"""Tests: MAP send — ConversationUpdated, build_bmsg format, no-duplicate-session.
Bead: tincan-klpm

Coverage:
  §1 SendMessage() emits MessageSent with non-empty handle
     - Successful send returns non-empty handle from MessageSent signal
  §2 ConversationUpdated fires after send with direction='outbound'
     - ConversationUpdated called once after SendMessage()
     - direction='outbound' in the updated conversation dict
     - last_message_preview set to message body
     - last_message_at is non-empty after send
  §5 build_bmsg format correctness
     - FOLDER:telecom/msg/outbox present
     - Originator vCard (N:;, TEL: empty) present before BEGIN:BENV
     - Recipient vCard uses VERSION:2.1 and TEL:{number} (not TYPE=CELL)
     - All line endings are CRLF — no bare \\n
  §6 No duplicate MAP session — send_message() does not call CreateSession
"""
from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

import dbus
import dbus.service
import pytest

from tincand.backends.bluez_map import MapBackend, build_bmsg
from tincand.dbus_service import Conversation, TincanService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PHONE = "+15555550123"   # normalizes to "5555550123"
_NORM  = "5555550123"
_BODY  = "Hello from test"


def _make_service() -> TincanService:
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
def send_ready_service():
    """TincanService connected, with a mock backend and a pre-seeded conversation."""
    svc = _make_service()
    svc._connected = True
    mock_backend = MagicMock(name="backend")
    mock_backend.send_message.return_value = "/org/obex/transfer7"
    svc._backend = mock_backend
    svc._conversations[_NORM] = Conversation(
        id=_NORM,
        display_name="Alice",
        last_message_at="",
        last_message_preview="",
        unread_count=0,
    )
    return svc


def _make_map_backend_with_mock_access():
    backend = MapBackend()
    mock_access = MagicMock(name="MessageAccess1")
    mock_access.PushMessage.return_value = ("/org/obex/transfer1", {})
    backend._msg_access = mock_access
    return backend, mock_access


# ---------------------------------------------------------------------------
# §1 SendMessage() emits MessageSent with non-empty handle
# ---------------------------------------------------------------------------

class TestSendMessageSignal:
    """SendMessage() emits MessageSent with the transfer path returned by the backend."""

    def test_message_sent_emitted_on_success(self, send_ready_service):
        send_ready_service.SendMessage(_PHONE, _BODY)
        assert send_ready_service.MessageSent.called

    def test_message_sent_handle_is_non_empty(self, send_ready_service):
        send_ready_service.SendMessage(_PHONE, _BODY)
        handle = send_ready_service.MessageSent.call_args[0][0]
        assert handle != ""

    def test_message_sent_handle_matches_backend_return(self, send_ready_service):
        send_ready_service.SendMessage(_PHONE, _BODY)
        handle = send_ready_service.MessageSent.call_args[0][0]
        assert handle == "/org/obex/transfer7"


# ---------------------------------------------------------------------------
# §2 ConversationUpdated fires after send with direction='outbound'
# ---------------------------------------------------------------------------

class TestConversationUpdatedAfterSend:
    """SendMessage() calls ConversationUpdated with an outbound direction dict."""

    def test_conversation_updated_called_after_send(self, send_ready_service):
        send_ready_service.SendMessage(_PHONE, _BODY)
        assert send_ready_service.ConversationUpdated.called

    def test_conversation_updated_called_exactly_once(self, send_ready_service):
        send_ready_service.SendMessage(_PHONE, _BODY)
        assert send_ready_service.ConversationUpdated.call_count == 1

    def test_conversation_updated_direction_is_outbound(self, send_ready_service):
        send_ready_service.SendMessage(_PHONE, _BODY)
        updated = send_ready_service.ConversationUpdated.call_args[0][0]
        assert str(updated["last_message_direction"]) == "outbound"

    def test_conversation_updated_preview_matches_body(self, send_ready_service):
        send_ready_service.SendMessage(_PHONE, _BODY)
        updated = send_ready_service.ConversationUpdated.call_args[0][0]
        assert str(updated["last_message_preview"]) == _BODY

    def test_conversation_updated_last_message_at_is_non_empty(self, send_ready_service):
        send_ready_service.SendMessage(_PHONE, _BODY)
        updated = send_ready_service.ConversationUpdated.call_args[0][0]
        assert str(updated["last_message_at"]) != ""

    def test_conversation_direction_stored_in_memory(self, send_ready_service):
        send_ready_service.SendMessage(_PHONE, _BODY)
        conv = send_ready_service._conversations[_NORM]
        assert conv.last_message_direction == "outbound"


# ---------------------------------------------------------------------------
# §5 build_bmsg format correctness
# ---------------------------------------------------------------------------

class TestBuildBmsgFolder:
    """FOLDER line is present and points to the outbox."""

    def test_folder_line_present(self):
        bmsg = build_bmsg(_PHONE, _BODY)
        assert "FOLDER:" in bmsg

    def test_folder_is_outbox(self):
        bmsg = build_bmsg(_PHONE, _BODY)
        assert "FOLDER:telecom/msg/outbox\r\n" in bmsg


class TestBuildBmsgOriginatorVcard:
    """Originator vCard block appears before BEGIN:BENV."""

    def test_originator_vcard_present_before_benv(self):
        bmsg = build_bmsg(_PHONE, _BODY)
        originator_pos = bmsg.index("BEGIN:VCARD")
        benv_pos = bmsg.index("BEGIN:BENV")
        assert originator_pos < benv_pos

    def test_originator_vcard_has_version_2_1(self):
        bmsg = build_bmsg(_PHONE, _BODY)
        # The very first VCARD block is the originator — slice before BENV.
        before_benv = bmsg[: bmsg.index("BEGIN:BENV")]
        assert "VERSION:2.1\r\n" in before_benv

    def test_originator_vcard_has_empty_tel(self):
        bmsg = build_bmsg(_PHONE, _BODY)
        before_benv = bmsg[: bmsg.index("BEGIN:BENV")]
        assert "TEL:\r\n" in before_benv

    def test_originator_vcard_has_n_field(self):
        bmsg = build_bmsg(_PHONE, _BODY)
        before_benv = bmsg[: bmsg.index("BEGIN:BENV")]
        assert "N:;\r\n" in before_benv


class TestBuildBmsgRecipientVcard:
    """Recipient vCard inside BENV uses VERSION:2.1 and bare TEL (not TYPE=CELL)."""

    def test_recipient_vcard_has_version_2_1(self):
        bmsg = build_bmsg(_PHONE, _BODY)
        after_benv = bmsg[bmsg.index("BEGIN:BENV"):]
        assert "VERSION:2.1\r\n" in after_benv

    def test_recipient_tel_contains_number(self):
        bmsg = build_bmsg("+15550199", _BODY)
        after_benv = bmsg[bmsg.index("BEGIN:BENV"):]
        assert "TEL:+15550199\r\n" in after_benv

    def test_recipient_tel_does_not_use_type_cell(self):
        bmsg = build_bmsg(_PHONE, _BODY)
        assert "TYPE=CELL" not in bmsg

    def test_recipient_n_field_contains_number(self):
        bmsg = build_bmsg("+15550199", _BODY)
        after_benv = bmsg[bmsg.index("BEGIN:BENV"):]
        assert "N:;+15550199\r\n" in after_benv


class TestBuildBmsgCrlf:
    """All line endings in a bMessage are CRLF — no bare \\n."""

    def test_no_bare_newline(self):
        bmsg = build_bmsg(_PHONE, _BODY)
        # A bare \n is any \n not immediately preceded by \r.
        bare_lf_positions = [i for i, ch in enumerate(bmsg)
                             if ch == "\n" and (i == 0 or bmsg[i - 1] != "\r")]
        assert bare_lf_positions == []

    def test_all_lines_end_with_crlf(self):
        bmsg = build_bmsg(_PHONE, "line test")
        for line in bmsg.split("\r\n"):
            if line:
                assert "\n" not in line, f"Found bare newline inside line: {line!r}"


# ---------------------------------------------------------------------------
# §6 No duplicate MAP session — send_message() does not call CreateSession
# ---------------------------------------------------------------------------

class TestNoCreateSessionOnSend:
    """send_message() uses the already-established session; never calls CreateSession."""

    def _send(self):
        backend, mock_access = _make_map_backend_with_mock_access()
        with patch.object(backend, "_wait_transfer_send", return_value=None):
            backend.send_message(_PHONE, _BODY)
        return backend, mock_access

    def test_create_session_not_called_on_msg_access(self):
        _, mock_access = self._send()
        assert not mock_access.CreateSession.called

    def test_set_folder_called_not_create_session(self):
        _, mock_access = self._send()
        assert mock_access.SetFolder.called

    def test_push_message_called_not_create_session(self):
        _, mock_access = self._send()
        assert mock_access.PushMessage.called

    def test_no_dbus_session_bus_call(self):
        """send_message() does not open a new D-Bus SessionBus (that is connect()'s job)."""
        backend, _ = _make_map_backend_with_mock_access()
        with patch("tincand.backends.bluez_map.dbus.SessionBus") as mock_bus, \
             patch.object(backend, "_wait_transfer_send", return_value=None):
            backend.send_message(_PHONE, _BODY)
        mock_bus.assert_not_called()
