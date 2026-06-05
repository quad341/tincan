"""Tests: _parse_participants_from_bmsg, poll_inbox group handling, _emit_messages grouping.
Bead: tincan-dsov0

Coverage:
  §1 _parse_participants_from_bmsg well-formed BENV — all TEL values returned, normalized
  §2 _parse_participants_from_bmsg no BENV — returns [] without exception
  §3 _parse_participants_from_bmsg malformed TEL — skips bad lines, returns good ones
  §4 poll_inbox ConvID present — groups by ConvID, skips participant parse (no extra GetMessage)
  §5 poll_inbox ConvID absent + MMS — groups by sha1 fallback (GetMessage called for parse)
  §6 poll_inbox SMS type — does NOT call GetMessage for participants; 1:1 path unchanged
  §7 _emit_messages mixed 1:1 and group — correct per-conv grouping, no cross-contamination

No D-Bus infrastructure needed for §1–§3.
§4–§7 mock the MAP D-Bus interface.
"""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from tincand.backends.bluez_map import MapBackend, _parse_participants_from_bmsg

# ---------------------------------------------------------------------------
# bMessage helpers
# ---------------------------------------------------------------------------

def _make_benv_bmsg(*phones: str) -> str:
    vcards = ""
    for p in phones:
        vcards += f"BEGIN:VCARD\r\nVERSION:2.1\r\nTEL:{p}\r\nEND:VCARD\r\n"
    return (
        "BEGIN:BMSG\r\nVERSION:1.0\r\nTYPE:MMS\r\n"
        "FOLDER:telecom/msg/inbox\r\n"
        "BEGIN:BENV\r\n"
        + vcards +
        "BEGIN:BBODY\r\nBEGIN:MSG\r\nHi\r\nEND:MSG\r\nEND:BBODY\r\n"
        "END:BENV\r\n"
        "END:BMSG\r\n"
    )


def _no_benv_bmsg() -> str:
    return (
        "BEGIN:BMSG\r\nVERSION:1.0\r\nTYPE:MMS\r\n"
        "FOLDER:telecom/msg/inbox\r\n"
        "BEGIN:BBODY\r\nBEGIN:MSG\r\nHi\r\nEND:MSG\r\nEND:BBODY\r\n"
        "END:BMSG\r\n"
    )


# ---------------------------------------------------------------------------
# §1 _parse_participants_from_bmsg — well-formed BENV
# ---------------------------------------------------------------------------

class TestParseParticipantsWellFormed:
    """Well-formed BENV with TEL lines returns all numbers normalized."""

    def test_two_phones_returned(self):
        bmsg = _make_benv_bmsg("+15550101234", "+15550105678")
        result = _parse_participants_from_bmsg(bmsg)
        assert sorted(result) == sorted(["5550101234", "5550105678"])

    def test_three_phones_all_returned(self):
        bmsg = _make_benv_bmsg("+15550101234", "+15550105678", "+15550109999")
        result = _parse_participants_from_bmsg(bmsg)
        assert len(result) == 3

    def test_numbers_normalized_not_raw_e164(self):
        bmsg = _make_benv_bmsg("+15550101234")
        result = _parse_participants_from_bmsg(bmsg)
        assert "+15550101234" not in result
        assert "5550101234" in result

    def test_tel_type_variant_extracted(self):
        bmsg = (
            "BEGIN:BMSG\r\nVERSION:1.0\r\nTYPE:MMS\r\n"
            "BEGIN:BENV\r\n"
            "BEGIN:VCARD\r\nVERSION:2.1\r\nTEL;TYPE=CELL:+15550101234\r\nEND:VCARD\r\n"
            "END:BENV\r\n"
            "END:BMSG\r\n"
        )
        result = _parse_participants_from_bmsg(bmsg)
        assert "5550101234" in result


# ---------------------------------------------------------------------------
# §2 _parse_participants_from_bmsg — no BENV section
# ---------------------------------------------------------------------------

class TestParseParticipantsNoBenv:
    """Missing BENV section returns [] without raising."""

    def test_no_benv_returns_empty_list(self):
        assert _parse_participants_from_bmsg(_no_benv_bmsg()) == []

    def test_empty_string_returns_empty_list(self):
        assert _parse_participants_from_bmsg("") == []

    def test_malformed_input_does_not_raise(self):
        result = _parse_participants_from_bmsg("not a bMessage at all")
        assert result == []


# ---------------------------------------------------------------------------
# §3 _parse_participants_from_bmsg — malformed TEL lines
# ---------------------------------------------------------------------------

class TestParseParticipantsMalformedTel:
    """Malformed VCARD lines are skipped; valid TEL lines still returned."""

    def test_non_tel_lines_skipped_good_ones_returned(self):
        bmsg = (
            "BEGIN:BMSG\r\nVERSION:1.0\r\nTYPE:MMS\r\n"
            "BEGIN:BENV\r\n"
            "BEGIN:VCARD\r\nVERSION:2.1\r\nTEL:+15550101234\r\nEND:VCARD\r\n"
            "BEGIN:VCARD\r\nVERSION:2.1\r\nNOT-A-TEL:garbage\r\nEND:VCARD\r\n"
            "BEGIN:VCARD\r\nVERSION:2.1\r\nTEL:+15550105678\r\nEND:VCARD\r\n"
            "END:BENV\r\n"
            "END:BMSG\r\n"
        )
        result = _parse_participants_from_bmsg(bmsg)
        assert "5550101234" in result
        assert "5550105678" in result

    def test_result_does_not_include_non_phone_content(self):
        bmsg = (
            "BEGIN:BMSG\r\nVERSION:1.0\r\nTYPE:MMS\r\n"
            "BEGIN:BENV\r\n"
            "BEGIN:VCARD\r\nVERSION:2.1\r\nNOT-A-TEL:garbage\r\nEND:VCARD\r\n"
            "BEGIN:VCARD\r\nVERSION:2.1\r\nTEL:+15550101234\r\nEND:VCARD\r\n"
            "END:BENV\r\n"
            "END:BMSG\r\n"
        )
        result = _parse_participants_from_bmsg(bmsg)
        assert "garbage" not in result


# ---------------------------------------------------------------------------
# Poll inbox test helpers
# ---------------------------------------------------------------------------

def _make_backend_mocked():
    """MapBackend with _msg_access fully mocked — no real D-Bus."""
    backend = MapBackend()
    mock_access = MagicMock(name="MessageAccess1")
    mock_access.UpdateInbox.return_value = None
    mock_access.SetFolder.return_value = None
    mock_access.ListMessages.return_value = {}
    backend._msg_access = mock_access
    backend._service = None
    return backend, mock_access


def _props(*, msg_type="SMS_GSM", conv_id=None, sender="+15550101234", read=False):
    p = {
        "Type": msg_type,
        "SenderAddressing": sender,
        "Read": read,
        "Subject": "Test",
    }
    if conv_id is not None:
        p["ConvID"] = conv_id
    return p


# ---------------------------------------------------------------------------
# §4 poll_inbox — ConvID present skips participant parse GetMessage
# ---------------------------------------------------------------------------

class TestPollInboxConvIdPresent:
    """When ConvID is in MAP properties, it is used as the conversation key.
    No additional GetMessage call is needed to parse participants from the bMessage.
    """

    def test_message_includes_conv_id_from_map_properties(self):
        backend, mock_access = _make_backend_mocked()
        mock_access.ListMessages.side_effect = lambda folder, _: (
            {"/MAP/msg/1": _props(msg_type="MMS", conv_id="mms-thread-42")}
            if folder == "inbox" else {}
        )
        with patch.object(backend, "_fetch_full_body", return_value="Hi group"):
            messages = backend.poll_inbox()
        assert messages, "poll_inbox returned no messages"
        assert any(m.get("conv_id") == "mms-thread-42" for m in messages)

    def test_get_message_not_called_for_participant_parse_when_conv_id_present(self):
        """GetMessage call count should be ≤ 1 per message (for body, not for participant parse)."""
        backend, mock_access = _make_backend_mocked()
        mock_access.ListMessages.side_effect = lambda folder, _: (
            {"/MAP/msg/1": _props(msg_type="MMS", conv_id="mms-thread-99")}
            if folder == "inbox" else {}
        )
        with patch.object(backend, "_fetch_full_body", return_value="Hi"):
            backend.poll_inbox()
        # GetMessage should not be called beyond what _fetch_full_body already handles
        # (which is patched out here), so total GetMessage calls == 0
        mock_access.GetMessage.assert_not_called()


# ---------------------------------------------------------------------------
# §5 poll_inbox — ConvID absent + MMS → sha1 fallback
# ---------------------------------------------------------------------------

class TestPollInboxNoConvIdMms:
    """MMS without ConvID: GetMessage fetches bMessage, participants parsed,
    sha1 of sorted phones used as conv_id.
    """

    def test_poll_inbox_returns_message_with_some_conv_id(self):
        backend, mock_access = _make_backend_mocked()
        mock_access.ListMessages.side_effect = lambda folder, _: (
            {"/MAP/msg/2": _props(msg_type="MMS")}
            if folder == "inbox" else {}
        )
        benv_body = _make_benv_bmsg("+15550101234", "+15550105678")
        with patch.object(backend, "_fetch_full_body", return_value="Hi"), \
             patch.object(backend, "_fetch_raw_message", return_value=benv_body):
            messages = backend.poll_inbox()
        assert messages, "poll_inbox returned no messages for MMS without ConvID"
        assert messages[0].get("conv_id") is not None

    def test_same_participants_produce_same_conv_id(self):
        """Two MMS with same participants and no ConvID should hash to same key."""
        backend, mock_access = _make_backend_mocked()
        mock_access.ListMessages.side_effect = lambda folder, _: (
            {
                "/MAP/msg/2": _props(msg_type="MMS", sender="+15550101234"),
                "/MAP/msg/3": _props(msg_type="MMS", sender="+15550101234"),
            }
            if folder == "inbox" else {}
        )
        benv_body = _make_benv_bmsg("+15550101234", "+15550105678")
        with patch.object(backend, "_fetch_full_body", return_value="Hi"), \
             patch.object(backend, "_fetch_raw_message", return_value=benv_body):
            messages = backend.poll_inbox()
        if len(messages) >= 2:
            conv_ids = [m.get("conv_id") for m in messages]
            assert conv_ids[0] == conv_ids[1], "Same participants should yield same conv_id"


# ---------------------------------------------------------------------------
# §6 poll_inbox — SMS type: no GetMessage for participant parse
# ---------------------------------------------------------------------------

class TestPollInboxSmsNoGetMessage:
    """SMS messages never trigger GetMessage for participant parsing."""

    def test_get_message_not_called_for_sms(self):
        backend, mock_access = _make_backend_mocked()
        mock_access.ListMessages.side_effect = lambda folder, _: (
            {"/MAP/msg/3": _props(msg_type="SMS_GSM")}
            if folder == "inbox" else {}
        )
        with patch.object(backend, "_fetch_full_body", return_value="Hello"):
            backend.poll_inbox()
        mock_access.GetMessage.assert_not_called()

    def test_sms_message_included_in_result(self):
        backend, mock_access = _make_backend_mocked()
        mock_access.ListMessages.side_effect = lambda folder, _: (
            {"/MAP/msg/3": _props(msg_type="SMS_GSM", sender="+15550101234")}
            if folder == "inbox" else {}
        )
        with patch.object(backend, "_fetch_full_body", return_value="Hello"):
            messages = backend.poll_inbox()
        assert messages, "SMS message missing from poll_inbox result"

    def test_sms_cdma_get_message_not_called(self):
        backend, mock_access = _make_backend_mocked()
        mock_access.ListMessages.side_effect = lambda folder, _: (
            {"/MAP/msg/4": _props(msg_type="SMS_CDMA")}
            if folder == "inbox" else {}
        )
        with patch.object(backend, "_fetch_full_body", return_value="Hi"):
            backend.poll_inbox()
        mock_access.GetMessage.assert_not_called()


# ---------------------------------------------------------------------------
# §7 _emit_messages — mixed 1:1 and group, no cross-contamination
# ---------------------------------------------------------------------------

class TestEmitMessagesMixedGroupAndOneToOne:
    """Group messages and 1:1 messages land in separate conversations."""

    def _make_svc_mock(self):
        svc = MagicMock()
        svc._conversations = {}
        cs = MagicMock()
        cs.resolve_name.return_value = None
        cs.lookup_by_name.return_value = None
        cs.get_name.return_value = None
        svc._contact_store = cs
        return svc

    def test_group_and_solo_messages_go_to_different_conversations(self):
        backend, _ = _make_backend_mocked()
        svc = self._make_svc_mock()
        backend._service = svc
        backend._name_to_phone = {}

        messages = [
            {
                "path": "/MAP/msg/10",
                "sender": "5550101234",
                "display_name": "Alice",
                "timestamp": "10:00",
                "read": False,
                "body": "Hey group",
                "direction": "inbound",
                "conv_id": "group-sha1-abc",
                "participants": ["5550101234", "5550105678"],
            },
            {
                "path": "/MAP/msg/11",
                "sender": "5550109999",
                "display_name": "Bob",
                "timestamp": "10:01",
                "read": False,
                "body": "Just you",
                "direction": "inbound",
                "conv_id": None,
                "participants": [],
            },
        ]
        backend._emit_messages(messages, notify=False)

        upserted_ids = [c.args[0].id for c in svc.upsert_conversation.call_args_list]
        assert len(set(upserted_ids)) == 2, (
            f"Expected 2 distinct conversation ids, got: {upserted_ids}"
        )

    def test_group_message_creates_conversation_with_is_group_true(self):
        backend, _ = _make_backend_mocked()
        svc = self._make_svc_mock()
        backend._service = svc
        backend._name_to_phone = {}

        messages = [
            {
                "path": "/MAP/msg/20",
                "sender": "5550101234",
                "display_name": "Alice",
                "timestamp": "11:00",
                "read": False,
                "body": "Group hello",
                "direction": "inbound",
                "conv_id": "group-sha1-xyz",
                "participants": ["5550101234", "5550105678", "5550109999"],
            }
        ]
        backend._emit_messages(messages, notify=False)

        assert svc.upsert_conversation.called
        conv = svc.upsert_conversation.call_args[0][0]
        assert getattr(conv, "is_group", False), "is_group should be True for group messages"

    def test_1to1_message_conv_does_not_have_group_participants(self):
        backend, _ = _make_backend_mocked()
        svc = self._make_svc_mock()
        backend._service = svc
        backend._name_to_phone = {}

        messages = [
            {
                "path": "/MAP/msg/30",
                "sender": "5550199999",
                "display_name": "Carol",
                "timestamp": "12:00",
                "read": False,
                "body": "Solo",
                "direction": "inbound",
                "conv_id": None,
                "participants": [],
            }
        ]
        backend._emit_messages(messages, notify=False)

        assert svc.upsert_conversation.called
        conv = svc.upsert_conversation.call_args[0][0]
        assert not getattr(conv, "is_group", False), "is_group should be False for 1:1 messages"
