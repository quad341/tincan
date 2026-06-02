"""Tests: bMessage builder (LENGTH byte count) and MAP-dict mapping (conversation grouping).
Bead: tincan-0ua

Coverage:
  §1 build_bmessage — LENGTH equals byte count of BEGIN:MSG…END:MSG block
    - ASCII body "Hello": LENGTH = 22 + 5 = 27
    - ASCII body "cafe": LENGTH = 22 + 4 = 26
    - 2-byte UTF-8 char é: LENGTH = 22 + 2 = 24 (NOT 23 for 1 char)
    - 2-byte UTF-8 char ü: LENGTH = 22 + 2 = 24
    - mixed "café" (5 UTF-8 bytes): LENGTH = 22 + 5 = 27 (NOT 26 for 4 chars)
    - 4-byte emoji 😀: LENGTH = 22 + 4 = 26 (NOT 23 for 1 char)
    - 4-byte emoji 🎉: LENGTH = 22 + 4 = 26
    - stated LENGTH matches actual block byte count (all bodies above)
  §2 build_bmessage — required header fields
    - CHARSET:UTF-8 present in BBODY
    - TYPE field present and reflects msg_type argument
    - FOLDER field present and reflects folder argument
    - STATUS field present and reflects status argument
  §3 parse_map_messages — field extraction from a{oa{sv}} fixture
    - Sender extracted for all 10 messages
    - Datetime extracted as timestamp
    - Read flag extracted (bool)
    - Subject extracted
    - Handle extracted
    - Type extracted
    - message count matches fixture length (10)
  §4 map_messages_to_conversations — grouping and unread_count
    - messages from same Sender land in one Conversation (3 senders → 3 entries)
    - messages from different Senders are in different Conversations
    - Alice unread_count == 2 (2 Read=False)
    - Bob unread_count == 1 (1 Read=False)
    - Carol unread_count == 0 (all Read=True)
    - Alice message list length == 3
    - Bob message list length == 4
    - Carol message list length == 3

No D-Bus infrastructure needed — all inputs are plain Python dicts.
"""
from __future__ import annotations

import re

import pytest

from tincand.bluez_map import (
    build_bmessage,
    map_messages_to_conversations,
    parse_map_messages,
)
from tests.tincand.fixtures.map_inbox_10msg import (
    EXPECTED_ALICE_UNREAD,
    EXPECTED_BOB_UNREAD,
    EXPECTED_CAROL_UNREAD,
    EXPECTED_SENDER_COUNT,
    MAP_INBOX_10MSG,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LENGTH_RE = re.compile(r"^LENGTH:(\d+)\r?$", re.MULTILINE)
_MSG_BLOCK_RE = re.compile(r"(BEGIN:MSG\r\n.*?END:MSG\r\n)", re.DOTALL)


def _parse_length(bmsg: str) -> int:
    """Return the integer value of the LENGTH: field, or -1 if absent."""
    m = _LENGTH_RE.search(bmsg)
    return int(m.group(1)) if m else -1


def _extract_msg_block_bytes(bmsg: str) -> bytes:
    """Return the raw UTF-8 bytes of the BEGIN:MSG…END:MSG block."""
    m = _MSG_BLOCK_RE.search(bmsg)
    return m.group(1).encode("utf-8") if m else b""


def _expected_length(body: str) -> int:
    """Reference implementation: byte count of BEGIN:MSG\\r\\n<body>\\r\\nEND:MSG\\r\\n."""
    return len(b"BEGIN:MSG\r\n" + body.encode("utf-8") + b"\r\nEND:MSG\r\n")


# ---------------------------------------------------------------------------
# §1 build_bmessage — LENGTH byte count
# ---------------------------------------------------------------------------

class TestBuildBmessageLengthAscii:
    """LENGTH field for pure-ASCII bodies equals character count + 22."""

    def test_ascii_hello_length_is_27(self):
        bmsg = build_bmessage(body="Hello")
        assert _parse_length(bmsg) == 27

    def test_ascii_cafe_length_is_26(self):
        bmsg = build_bmessage(body="cafe")
        assert _parse_length(bmsg) == 26

    def test_ascii_stated_length_matches_actual_block_bytes(self):
        body = "Hello"
        bmsg = build_bmessage(body=body)
        stated = _parse_length(bmsg)
        actual = len(_extract_msg_block_bytes(bmsg))
        assert stated == actual

    def test_ascii_stated_length_matches_reference(self):
        body = "Hello"
        bmsg = build_bmessage(body=body)
        assert _parse_length(bmsg) == _expected_length(body)


class TestBuildBmessageLengthUtf8TwoByte:
    """LENGTH for 2-byte UTF-8 chars reflects byte count, not char count."""

    def test_e_acute_length_is_24(self):
        # é = U+00E9 → 2 bytes; char count is 1, byte count is 2
        bmsg = build_bmessage(body="é")
        assert _parse_length(bmsg) == 24

    def test_u_umlaut_length_is_24(self):
        bmsg = build_bmessage(body="ü")
        assert _parse_length(bmsg) == 24

    def test_cafe_utf8_length_is_27(self):
        # "café": 4 chars but 5 UTF-8 bytes (é=2 bytes)
        bmsg = build_bmessage(body="café")
        assert _parse_length(bmsg) == 27

    def test_cafe_utf8_differs_from_cafe_ascii(self):
        # "café" (5 bytes) != "cafe" (4 bytes)
        assert _parse_length(build_bmessage(body="café")) != _parse_length(
            build_bmessage(body="cafe")
        )

    def test_two_byte_char_stated_length_matches_actual_block(self):
        body = "café"
        bmsg = build_bmessage(body=body)
        assert _parse_length(bmsg) == len(_extract_msg_block_bytes(bmsg))

    def test_two_byte_char_stated_length_matches_reference(self):
        body = "café"
        bmsg = build_bmessage(body=body)
        assert _parse_length(bmsg) == _expected_length(body)


class TestBuildBmessageLengthUtf8FourByte:
    """LENGTH for 4-byte emoji reflects byte count, not char count."""

    def test_grinning_face_emoji_length_is_26(self):
        # 😀 = U+1F600 → 4 bytes
        bmsg = build_bmessage(body="😀")
        assert _parse_length(bmsg) == 26

    def test_party_popper_emoji_length_is_26(self):
        # 🎉 = U+1F389 → 4 bytes
        bmsg = build_bmessage(body="🎉")
        assert _parse_length(bmsg) == 26

    def test_emoji_stated_length_matches_actual_block(self):
        body = "😀"
        bmsg = build_bmessage(body=body)
        assert _parse_length(bmsg) == len(_extract_msg_block_bytes(bmsg))

    def test_emoji_stated_length_matches_reference(self):
        for body in ("😀", "🎉"):
            bmsg = build_bmessage(body=body)
            assert _parse_length(bmsg) == _expected_length(body), f"failed for {body!r}"


# ---------------------------------------------------------------------------
# §2 build_bmessage — required header fields
# ---------------------------------------------------------------------------

class TestBuildBmessageFields:
    """Required bMessage header and body fields are present in the output."""

    def test_charset_utf8_in_bbody(self):
        bmsg = build_bmessage(body="Hello")
        assert "CHARSET:UTF-8" in bmsg

    def test_type_field_reflects_argument(self):
        bmsg = build_bmessage(body="Hello", msg_type="SMS_CDMA")
        assert "TYPE:SMS_CDMA" in bmsg

    def test_type_defaults_to_sms_gsm(self):
        bmsg = build_bmessage(body="Hello")
        assert "TYPE:SMS_GSM" in bmsg

    def test_folder_field_reflects_argument(self):
        bmsg = build_bmessage(body="Hello", folder="telecom/msg/sent")
        assert "FOLDER:telecom/msg/sent" in bmsg

    def test_folder_defaults_to_inbox(self):
        bmsg = build_bmessage(body="Hello")
        assert "FOLDER:telecom/msg/inbox" in bmsg

    def test_status_field_reflects_argument(self):
        bmsg = build_bmessage(body="Hello", status="READ")
        assert "STATUS:READ" in bmsg

    def test_status_defaults_to_unread(self):
        bmsg = build_bmessage(body="Hello")
        assert "STATUS:UNREAD" in bmsg

    def test_begin_bmessage_present(self):
        bmsg = build_bmessage(body="Hello")
        assert "BEGIN:BMESSAGE" in bmsg

    def test_end_bmessage_present(self):
        bmsg = build_bmessage(body="Hello")
        assert "END:BMESSAGE" in bmsg

    def test_begin_msg_present(self):
        bmsg = build_bmessage(body="Hello")
        assert "BEGIN:MSG" in bmsg

    def test_end_msg_present(self):
        bmsg = build_bmessage(body="Hello")
        assert "END:MSG" in bmsg

    def test_body_content_present_in_output(self):
        body = "Test message content"
        bmsg = build_bmessage(body=body)
        assert body in bmsg

    def test_sender_fn_in_vcard_when_provided(self):
        bmsg = build_bmessage(body="Hi", sender="Alice")
        assert "FN:Alice" in bmsg

    def test_sender_tel_in_vcard_when_provided(self):
        bmsg = build_bmessage(body="Hi", sender_tel="+15551234567")
        assert "TEL:+15551234567" in bmsg


# ---------------------------------------------------------------------------
# §3 parse_map_messages — field extraction
# ---------------------------------------------------------------------------

class TestParseMapMessages:
    """parse_map_messages extracts Sender, Datetime, Read, Subject from fixture."""

    @pytest.fixture(scope="class")
    def parsed(self):
        return parse_map_messages(MAP_INBOX_10MSG)

    def test_message_count_is_10(self, parsed):
        assert len(parsed) == 10

    def test_all_messages_have_sender(self, parsed):
        for msg in parsed:
            assert "sender" in msg
            assert msg["sender"] != ""

    def test_alice_sender_present(self, parsed):
        senders = {m["sender"] for m in parsed}
        assert "Alice" in senders

    def test_bob_sender_present(self, parsed):
        senders = {m["sender"] for m in parsed}
        assert "Bob" in senders

    def test_carol_sender_present(self, parsed):
        senders = {m["sender"] for m in parsed}
        assert "Carol" in senders

    def test_all_messages_have_timestamp(self, parsed):
        for msg in parsed:
            assert "timestamp" in msg
            assert msg["timestamp"] != ""

    def test_all_messages_have_is_read_bool(self, parsed):
        for msg in parsed:
            assert "is_read" in msg
            assert isinstance(msg["is_read"], bool)

    def test_read_flag_false_for_unread_messages(self, parsed):
        unread = [m for m in parsed if not m["is_read"]]
        assert len(unread) == 3  # matches EXPECTED_TOTAL_UNREAD

    def test_read_flag_true_for_read_messages(self, parsed):
        read = [m for m in parsed if m["is_read"]]
        assert len(read) == 7

    def test_all_messages_have_subject(self, parsed):
        for msg in parsed:
            assert "subject" in msg

    def test_subject_hey_present(self, parsed):
        subjects = {m["subject"] for m in parsed}
        assert "Hey" in subjects

    def test_all_messages_have_handle(self, parsed):
        for msg in parsed:
            assert "handle" in msg
            assert msg["handle"] != ""

    def test_handles_are_unique(self, parsed):
        handles = [m["handle"] for m in parsed]
        assert len(set(handles)) == 10

    def test_all_messages_have_msg_type(self, parsed):
        for msg in parsed:
            assert "msg_type" in msg

    def test_sms_gsm_type_present(self, parsed):
        types = {m["msg_type"] for m in parsed}
        assert "SMS_GSM" in types

    def test_sms_cdma_type_present(self, parsed):
        types = {m["msg_type"] for m in parsed}
        assert "SMS_CDMA" in types


# ---------------------------------------------------------------------------
# §4 map_messages_to_conversations — grouping and unread_count
# ---------------------------------------------------------------------------

class TestMapMessagesToConversations:
    """map_messages_to_conversations groups by sender with correct unread_count."""

    @pytest.fixture(scope="class")
    def conversations(self):
        messages = parse_map_messages(MAP_INBOX_10MSG)
        return map_messages_to_conversations(messages)

    def test_three_senders_produce_three_conversations(self, conversations):
        assert len(conversations) == EXPECTED_SENDER_COUNT

    def test_alice_conversation_exists(self, conversations):
        assert "Alice" in conversations

    def test_bob_conversation_exists(self, conversations):
        assert "Bob" in conversations

    def test_carol_conversation_exists(self, conversations):
        assert "Carol" in conversations

    def test_alice_message_count_is_3(self, conversations):
        assert len(conversations["Alice"]["messages"]) == 3

    def test_bob_message_count_is_4(self, conversations):
        assert len(conversations["Bob"]["messages"]) == 4

    def test_carol_message_count_is_3(self, conversations):
        assert len(conversations["Carol"]["messages"]) == 3

    def test_alice_unread_count_is_2(self, conversations):
        assert conversations["Alice"]["unread_count"] == EXPECTED_ALICE_UNREAD

    def test_bob_unread_count_is_1(self, conversations):
        assert conversations["Bob"]["unread_count"] == EXPECTED_BOB_UNREAD

    def test_carol_unread_count_is_0(self, conversations):
        assert conversations["Carol"]["unread_count"] == EXPECTED_CAROL_UNREAD

    def test_all_alice_messages_have_alice_sender(self, conversations):
        for msg in conversations["Alice"]["messages"]:
            assert msg["sender"] == "Alice"

    def test_unread_count_equals_is_read_false_count(self, conversations):
        for sender, conv in conversations.items():
            expected = sum(1 for m in conv["messages"] if not m["is_read"])
            assert conv["unread_count"] == expected, (
                f"sender={sender}: unread_count={conv['unread_count']} "
                f"but {expected} messages have is_read=False"
            )

    def test_conversation_dict_has_sender_key(self, conversations):
        for conv in conversations.values():
            assert "sender" in conv

    def test_conversation_dict_has_messages_key(self, conversations):
        for conv in conversations.values():
            assert "messages" in conv

    def test_conversation_dict_has_unread_count_key(self, conversations):
        for conv in conversations.values():
            assert "unread_count" in conv

    def test_read_messages_do_not_increment_unread_count(self, conversations):
        # Carol has 3 messages, all read → unread_count must be 0, not 3
        assert conversations["Carol"]["unread_count"] == 0
        assert len(conversations["Carol"]["messages"]) == 3
