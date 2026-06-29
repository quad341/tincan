"""Tests: FakeMapBackend — iOS-faithful test double (tincan-n5wwx).

Coverage:
  §1 Sent folder returns 0 — poll_inbox only returns inbound (iOS quirk a)
  §2 Inbox message shapes — SMS and MMS with attachments (iOS quirk b)
  §3 Lazy PBAP contact resolution — display_name starts as phone (iOS quirk c)
  §4 Group send and failure paths (iOS quirk d)
  §5 Send-failure responses (iOS quirk e)
  §6 get_message / handle tracking
  §7 reset() clears all state
"""
from __future__ import annotations

import json

import pytest

from tincand.backends.fake_map import FakeMapBackend


class TestSentFolderAlwaysEmpty:
    """iOS MAP quirk (a): no outbound history in poll_inbox."""

    def test_poll_inbox_empty_by_default(self):
        b = FakeMapBackend()
        assert b.poll_inbox() == []

    def test_poll_inbox_returns_only_inbound(self):
        b = FakeMapBackend()
        b.add_inbound("+15550001", "Hi", conv_id="5550001")
        msgs = b.poll_inbox()
        assert all(m["direction"] == "inbound" for m in msgs)

    def test_send_message_does_not_pollute_inbox(self):
        b = FakeMapBackend()
        b.send_message("+15550001", "Hello")
        assert b.poll_inbox() == []


class TestInboxMessageShapes:
    """iOS MAP quirk (b): inbox messages must carry all required fields."""

    def test_sms_message_has_required_fields(self):
        b = FakeMapBackend()
        b.add_inbound("+15550001", "Hey!", conv_id="5550001")
        msg = b.poll_inbox()[0]
        for field in ("sender", "body", "direction", "msg_type", "read",
                      "timestamp", "conv_id", "attachments"):  # no 'participants' — group surface removed
            assert field in msg, f"Missing field: {field}"

    def test_sms_message_has_correct_defaults(self):
        b = FakeMapBackend()
        b.add_inbound("+15550001", "Hey!")
        msg = b.poll_inbox()[0]
        assert msg["direction"] == "inbound"
        assert msg["msg_type"] == "SMS_GSM"
        assert msg["read"] is False
        assert json.loads(msg["attachments"]) == []

    def test_mms_message_with_attachment(self):
        b = FakeMapBackend()
        attachments = [{"mime_type": "image/jpeg", "data": "abc123"}]
        b.add_inbound(
            "+15550002", "Check this", msg_type="MMS", attachments=attachments
        )
        msg = b.poll_inbox()[0]
        assert msg["msg_type"] == "MMS"
        parsed = json.loads(msg["attachments"])
        assert parsed == attachments

    def test_multiple_messages_in_inbox(self):
        b = FakeMapBackend()
        b.add_inbound("+15550001", "A")
        b.add_inbound("+15550001", "B")
        b.add_inbound("+15550002", "C")
        assert len(b.poll_inbox()) == 3

    def test_conv_id_used_when_provided(self):
        b = FakeMapBackend()
        b.add_inbound("+15550001", "Hi", conv_id="conv-abc")
        msg = b.poll_inbox()[0]
        assert msg["conv_id"] == "conv-abc"

    def test_conv_id_defaults_to_sender_when_absent(self):
        b = FakeMapBackend()
        b.add_inbound("+15550001", "Hi")
        msg = b.poll_inbox()[0]
        assert msg["conv_id"] == "+15550001"


class TestLazyPBAPContactResolution:
    """iOS MAP quirk (c): display_name starts as phone number."""

    def test_display_name_defaults_to_sender_phone(self):
        b = FakeMapBackend()
        b.add_inbound("+15550001", "Hi")
        msg = b.poll_inbox()[0]
        assert msg["display_name"] == "+15550001"

    def test_display_name_explicit_override(self):
        b = FakeMapBackend()
        b.add_inbound("+15550001", "Hi", display_name="Alice")
        msg = b.poll_inbox()[0]
        assert msg["display_name"] == "Alice"

    def test_resolve_contact_name_updates_inbox(self):
        b = FakeMapBackend()
        b.add_inbound("+15550001", "First message")
        b.add_inbound("+15550001", "Second message")
        b.resolve_contact_name("+15550001", "Alice")
        for msg in b.poll_inbox():
            assert msg["display_name"] == "Alice"

    def test_resolve_contact_name_does_not_affect_other_sender(self):
        b = FakeMapBackend()
        b.add_inbound("+15550001", "From Alice")
        b.add_inbound("+15550002", "From Bob")
        b.resolve_contact_name("+15550001", "Alice")
        for msg in b.poll_inbox():
            if msg["sender"] == "+15550002":
                assert msg["display_name"] == "+15550002"


class TestSendFailures:
    """iOS MAP quirk (e): send_message can raise on MAP error."""

    def test_send_message_success_returns_handle(self):
        b = FakeMapBackend()
        handle = b.send_message("+15550001", "Hi")
        assert handle and isinstance(handle, str)

    def test_send_message_raises_on_configured_failure(self):
        b = FakeMapBackend()
        b.set_send_failure("+15550001", RuntimeError("MAP rejected"))
        with pytest.raises(RuntimeError, match="MAP rejected"):
            b.send_message("+15550001", "Hi")

    def test_send_message_succeeds_for_other_targets(self):
        b = FakeMapBackend()
        b.set_send_failure("+15550001", RuntimeError("fail"))
        handle = b.send_message("+15550002", "Hi")
        assert handle and isinstance(handle, str)


class TestHandleTracking:
    def test_add_inbound_returns_handle(self):
        b = FakeMapBackend()
        handle = b.add_inbound("+15550001", "Hi")
        assert handle and isinstance(handle, str)

    def test_get_message_returns_stored_inbound(self):
        b = FakeMapBackend()
        handle = b.add_inbound("+15550001", "Hi")
        msg = b.get_message(handle)
        assert msg is not None
        assert msg["body"] == "Hi"

    def test_get_message_returns_none_for_unknown_handle(self):
        b = FakeMapBackend()
        assert b.get_message("unknown-handle") is None

    def test_send_message_handle_is_retrievable(self):
        b = FakeMapBackend()
        handle = b.send_message("+15550001", "Sent text")
        msg = b.get_message(handle)
        assert msg is not None
        assert msg["direction"] == "outbound"


class TestReset:
    def test_reset_clears_inbox(self):
        b = FakeMapBackend()
        b.add_inbound("+15550001", "Hi")
        b.reset()
        assert b.poll_inbox() == []

    def test_reset_clears_handles(self):
        b = FakeMapBackend()
        handle = b.add_inbound("+15550001", "Hi")
        b.reset()
        assert b.get_message(handle) is None

    def test_reset_clears_send_failures(self):
        b = FakeMapBackend()
        b.set_send_failure("+15550001", RuntimeError("fail"))
        b.reset()
        handle = b.send_message("+15550001", "now ok")
        assert handle and isinstance(handle, str)
