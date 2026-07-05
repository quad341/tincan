"""Tests: tincand.ancs_util — pure Python ANCS TLV parser and fragmentation buffer.
Bead: tincan-60t

Coverage:
  §1 parse_notification_source — field extraction from 3 LE fixtures
    - event_id extracted from byte 0
    - event_flags extracted from byte 1
    - category_id extracted from byte 2 (Social/SMS=6, IncomingCall=4, Modified=2)
    - category_count extracted from byte 3
    - notification_uid parsed as LITTLE-endian uint32 (struct.unpack('<BBBBL'))
  §2 parse_notification_source — category identification
    - category_id=6 (Social/SMS) correctly returned
    - category_id=4 (IncomingCall) correctly returned
  §3 parse_notification_source — validation
    - ValueError raised when len(data) != 8
    - ValueError raised on 7-byte, 9-byte, and empty inputs
  §4 build_get_attrs_cmd — command construction
    - CommandID byte is 0x00
    - UID encoded as 4 bytes little-endian
    - ATTR_TITLE (1) and ATTR_MESSAGE (3) include a 2-byte length field
    - ATTR_APP_ID (0) has no length field
  §5 parse_data_source — TLV attribute extraction
    - result["attrs"][ATTR_TITLE] (ID=1) extracted as UTF-8 string
    - result["attrs"][ATTR_MESSAGE] (ID=3) extracted as UTF-8 string
    - notification_uid parsed as LITTLE-endian uint32 from offset 1..4
    - ATTR_TITLE and ATTR_MESSAGE keys present in result["attrs"] with both attrs
    - missing attribute → result["attrs"].get(ATTR_MESSAGE, "") == ""
  §6 parse_data_source — error cases
    - ValueError raised when CommandID != 0
    - IncompleteResponseError raised on truncated TLV value
    - IncompleteResponseError raised on truncated TLV header (7 bytes)
  §7 ANCSDataBuffer.accumulate — fragmentation buffer
    - returns None when TLV value is truncated (mid-TLV partial)
    - returns bytes when complete response received in one chunk
    - returns bytes when complete response assembled from two chunks
  §8 ANCSDataBuffer.clear — buffer reset
    - clear(uid) removes the buffer for that UID
    - subsequent accumulate for same UID starts fresh

No hardware or D-Bus required — all tests operate on raw byte fixtures.
Run with: python -m pytest tests/tincand/test_ancs_util.py -v
"""
from __future__ import annotations

import struct

import pytest

from tests.tincand.fixtures.ancs_util_fixtures import (
    GET_ATTRS_TITLE_AND_MESSAGE_LE,
    GET_ATTRS_TITLE_ONLY_LE,
    NOTIF_UTIL_INCOMING,
    NOTIF_UTIL_MODIFIED,
    NOTIF_UTIL_SOCIAL,
)
from tincand.ancs_util import (
    ATTR_APP_ID,
    ATTR_MESSAGE,
    ATTR_TITLE,
    ANCSDataBuffer,
    IncompleteResponseError,
    build_get_attrs_cmd,
    parse_data_source,
    parse_notification_source,
)

# ---------------------------------------------------------------------------
# §1 parse_notification_source — field extraction
# ---------------------------------------------------------------------------

class TestParseNotificationSourceFields:
    """All 8-byte header fields extracted correctly from three LE fixtures."""

    def test_event_id_from_social_fixture(self):
        result = parse_notification_source(NOTIF_UTIL_SOCIAL)
        assert result["event_id"] == 0x00

    def test_event_flags_from_social_fixture(self):
        result = parse_notification_source(NOTIF_UTIL_SOCIAL)
        assert result["event_flags"] == 0x00

    def test_category_id_from_social_fixture(self):
        result = parse_notification_source(NOTIF_UTIL_SOCIAL)
        assert result["category_id"] == 6

    def test_category_count_from_social_fixture(self):
        result = parse_notification_source(NOTIF_UTIL_SOCIAL)
        assert result["category_count"] == 1

    def test_notification_uid_little_endian_from_social_fixture(self):
        result = parse_notification_source(NOTIF_UTIL_SOCIAL)
        assert result["notification_uid"] == 0x00000001

    def test_event_id_from_incoming_fixture(self):
        result = parse_notification_source(NOTIF_UTIL_INCOMING)
        assert result["event_id"] == 0x00

    def test_event_flags_from_incoming_fixture(self):
        result = parse_notification_source(NOTIF_UTIL_INCOMING)
        assert result["event_flags"] == 0x00

    def test_category_id_from_incoming_fixture(self):
        result = parse_notification_source(NOTIF_UTIL_INCOMING)
        assert result["category_id"] == 4

    def test_notification_uid_little_endian_from_incoming_fixture(self):
        result = parse_notification_source(NOTIF_UTIL_INCOMING)
        assert result["notification_uid"] == 0x0000ABCD

    def test_event_id_from_modified_fixture(self):
        result = parse_notification_source(NOTIF_UTIL_MODIFIED)
        assert result["event_id"] == 0x01

    def test_event_flags_from_modified_fixture(self):
        result = parse_notification_source(NOTIF_UTIL_MODIFIED)
        assert result["event_flags"] == 0x02

    def test_category_id_from_modified_fixture(self):
        result = parse_notification_source(NOTIF_UTIL_MODIFIED)
        assert result["category_id"] == 2

    def test_category_count_from_modified_fixture(self):
        result = parse_notification_source(NOTIF_UTIL_MODIFIED)
        assert result["category_count"] == 2

    def test_notification_uid_boundary_little_endian_from_modified_fixture(self):
        result = parse_notification_source(NOTIF_UTIL_MODIFIED)
        assert result["notification_uid"] == 0xFFFFFFFE


# ---------------------------------------------------------------------------
# §2 parse_notification_source — category identification
# ---------------------------------------------------------------------------

class TestParseNotificationSourceCategory:
    """category_id field returned correctly for Social/SMS (6) and IncomingCall (4)."""

    def test_category_id_6_social_sms_correctly_identified(self):
        result = parse_notification_source(NOTIF_UTIL_SOCIAL)
        assert result["category_id"] == 6

    def test_category_id_4_incoming_call_correctly_identified(self):
        result = parse_notification_source(NOTIF_UTIL_INCOMING)
        assert result["category_id"] == 4

    def test_category_id_present_in_result(self):
        result = parse_notification_source(NOTIF_UTIL_SOCIAL)
        assert "category_id" in result

    def test_notification_uid_key_present_in_result(self):
        result = parse_notification_source(NOTIF_UTIL_SOCIAL)
        assert "notification_uid" in result


# ---------------------------------------------------------------------------
# §3 parse_notification_source — validation
# ---------------------------------------------------------------------------

class TestParseNotificationSourceValidation:
    """ValueError raised when input is not exactly 8 bytes."""

    def test_raises_value_error_on_7_bytes(self):
        with pytest.raises(ValueError):
            parse_notification_source(bytes(7))

    def test_raises_value_error_on_9_bytes(self):
        with pytest.raises(ValueError):
            parse_notification_source(bytes(9))

    def test_raises_value_error_on_empty_bytes(self):
        with pytest.raises(ValueError):
            parse_notification_source(b"")

    def test_raises_value_error_on_4_bytes(self):
        with pytest.raises(ValueError):
            parse_notification_source(bytes(4))

    def test_does_not_raise_on_exactly_8_bytes(self):
        parse_notification_source(bytes(8))  # should not raise


# ---------------------------------------------------------------------------
# §4 build_get_attrs_cmd — command construction
# ---------------------------------------------------------------------------

class TestBuildGetAttrsCmd:
    """build_get_attrs_cmd produces correctly-encoded ANCS command bytes."""

    def test_first_byte_is_command_id_zero(self):
        cmd = build_get_attrs_cmd(1, [ATTR_TITLE])
        assert cmd[0] == 0x00

    def test_uid_encoded_as_little_endian_four_bytes(self):
        cmd = build_get_attrs_cmd(0x0000ABCD, [ATTR_TITLE])
        uid_bytes = cmd[1:5]
        assert struct.unpack("<I", uid_bytes)[0] == 0x0000ABCD

    def test_uid_1_encodes_correctly(self):
        cmd = build_get_attrs_cmd(1, [ATTR_TITLE])
        uid_bytes = cmd[1:5]
        assert struct.unpack("<I", uid_bytes)[0] == 1

    def test_attr_title_followed_by_length_field(self):
        cmd = build_get_attrs_cmd(1, [ATTR_TITLE])
        # bytes 5+ should contain AttrID=ATTR_TITLE and a 2-byte length field
        attr_section = cmd[5:]
        assert attr_section[0] == ATTR_TITLE
        assert len(attr_section) >= 3  # attr_id(1) + length(2)

    def test_attr_message_followed_by_length_field(self):
        cmd = build_get_attrs_cmd(1, [ATTR_MESSAGE])
        attr_section = cmd[5:]
        assert attr_section[0] == ATTR_MESSAGE
        assert len(attr_section) >= 3

    def test_attr_app_id_has_no_length_field(self):
        # ATTR_APP_ID (0) does not have a length field per spec
        cmd_app = build_get_attrs_cmd(1, [ATTR_APP_ID])
        cmd_title = build_get_attrs_cmd(1, [ATTR_TITLE])
        # app_id command should be 3 bytes shorter than title (no 2-byte length)
        assert len(cmd_app) == len(cmd_title) - 2

    def test_multiple_attrs_all_present_in_output(self):
        cmd = build_get_attrs_cmd(1, [ATTR_TITLE, ATTR_MESSAGE])
        attr_section = cmd[5:]
        attr_ids = []
        i = 0
        while i < len(attr_section):
            attr_id = attr_section[i]
            attr_ids.append(attr_id)
            i += 3  # attr_id(1) + length(2) — assumes all requested have length field
        assert ATTR_TITLE in attr_ids
        assert ATTR_MESSAGE in attr_ids

    def test_constants_have_expected_values(self):
        assert ATTR_APP_ID == 0
        assert ATTR_TITLE == 1
        assert ATTR_MESSAGE == 3


# ---------------------------------------------------------------------------
# §5 parse_data_source — TLV attribute extraction
# ---------------------------------------------------------------------------

class TestParseDataSourceAttributes:
    """TLV attributes extracted correctly from Data Source characteristic payload."""

    def test_title_extracted_as_utf8_string(self):
        result = parse_data_source(GET_ATTRS_TITLE_AND_MESSAGE_LE)
        assert result["attrs"][ATTR_TITLE] == "Hello"

    def test_message_extracted_as_utf8_string(self):
        result = parse_data_source(GET_ATTRS_TITLE_AND_MESSAGE_LE)
        assert result["attrs"][ATTR_MESSAGE] == "World"

    def test_notification_uid_parsed_as_little_endian_uint32(self):
        result = parse_data_source(GET_ATTRS_TITLE_AND_MESSAGE_LE)
        assert result["notification_uid"] == 1

    def test_both_title_and_message_keys_present(self):
        result = parse_data_source(GET_ATTRS_TITLE_AND_MESSAGE_LE)
        assert ATTR_TITLE in result["attrs"]
        assert ATTR_MESSAGE in result["attrs"]

    def test_missing_message_attr_returns_empty_string(self):
        result = parse_data_source(GET_ATTRS_TITLE_ONLY_LE)
        assert result["attrs"].get(ATTR_MESSAGE, "") == ""

    def test_title_only_fixture_uid_parsed_correctly(self):
        result = parse_data_source(GET_ATTRS_TITLE_ONLY_LE)
        assert result["notification_uid"] == 0x0000ABCD

    def test_title_from_title_only_fixture(self):
        result = parse_data_source(GET_ATTRS_TITLE_ONLY_LE)
        assert result["attrs"][ATTR_TITLE] == "Test"


# ---------------------------------------------------------------------------
# §6 parse_data_source — error cases
# ---------------------------------------------------------------------------

class TestParseDataSourceErrors:
    """ValueError on bad CommandID; IncompleteResponseError on truncated buffer."""

    def test_raises_value_error_when_command_id_is_not_zero(self):
        bad_cmd = bytes([0x01, 0x01, 0x00, 0x00, 0x00])  # CommandID=1
        with pytest.raises(ValueError):
            parse_data_source(bad_cmd)

    def test_raises_incomplete_response_error_on_truncated_buffer(self):
        # Payload claims length=10 for an attr but only 2 bytes follow
        truncated = bytes([
            0x00,                  # CommandID
            0x01, 0x00, 0x00, 0x00,  # UID=1 LE
            0x01, 0x0A, 0x00,      # AttrID=Title, Length=10 LE
            0x48, 0x65,            # Only 2 bytes of data instead of 10
        ])
        with pytest.raises(IncompleteResponseError):
            parse_data_source(truncated)

    def test_raises_incomplete_response_error_on_truncated_tlv_header(self):
        # 7 bytes: header(5) + AttrID(1) + 1 byte of Length — TLV header needs 3, only 2 here
        truncated_tlv_hdr = bytes([0x00, 0x01, 0x00, 0x00, 0x00, 0x01, 0x05])
        with pytest.raises(IncompleteResponseError):
            parse_data_source(truncated_tlv_hdr)


# ---------------------------------------------------------------------------
# §7 ANCSDataBuffer.accumulate
# ---------------------------------------------------------------------------

class TestANCSDataBufferAccumulate:
    """accumulate returns None on incomplete chunk, bytes when response is complete."""

    def _complete_payload(self, uid: int = 1) -> bytes:
        uid_le = struct.pack("<I", uid)
        title = b"Hi"
        return bytes([0x00]) + uid_le + bytes([0x01, len(title), 0x00]) + title

    def test_returns_none_for_partial_chunk(self):
        buf = ANCSDataBuffer()
        # Feed header + TLV header + 1 of 2 claimed value bytes — TLV value incomplete
        payload = self._complete_payload(uid=1)
        partial = payload[:-1]  # drop last byte: TLV value is 1 byte short
        result = buf.accumulate(1, partial)
        assert result is None

    def test_returns_bytes_when_complete_response_in_one_chunk(self):
        buf = ANCSDataBuffer()
        payload = self._complete_payload(uid=1)
        result = buf.accumulate(1, payload)
        assert isinstance(result, bytes)

    def test_returns_bytes_assembled_from_two_chunks(self):
        buf = ANCSDataBuffer()
        payload = self._complete_payload(uid=2)
        mid = len(payload) - 1  # first chunk has all but last byte: TLV value incomplete
        first = buf.accumulate(2, payload[:mid])
        assert first is None
        second = buf.accumulate(2, payload[mid:])
        assert isinstance(second, bytes)
        assert second == payload

    def test_complete_payload_content_matches_original(self):
        buf = ANCSDataBuffer()
        payload = self._complete_payload(uid=3)
        result = buf.accumulate(3, payload)
        assert result == payload

    def test_different_uids_buffered_independently(self):
        buf = ANCSDataBuffer()
        payload_a = self._complete_payload(uid=10)
        payload_b = self._complete_payload(uid=20)
        mid_a = len(payload_a) // 2
        buf.accumulate(10, payload_a[:mid_a])
        result_b = buf.accumulate(20, payload_b)  # uid=20 completes in one chunk
        result_a = buf.accumulate(10, payload_a[mid_a:])
        assert isinstance(result_b, bytes)
        assert isinstance(result_a, bytes)


# ---------------------------------------------------------------------------
# §8 ANCSDataBuffer.clear
# ---------------------------------------------------------------------------

class TestANCSDataBufferClear:
    """clear(uid) resets the buffer for that UID; subsequent accumulate starts fresh."""

    def _partial_payload(self, uid: int = 1) -> bytes:
        """5-byte header only — incomplete, so accumulate returns None."""
        return bytes([0x00]) + struct.pack("<I", uid)

    def _complete_payload(self, uid: int = 1) -> bytes:
        uid_le = struct.pack("<I", uid)
        title = b"Ok"
        return bytes([0x00]) + uid_le + bytes([0x01, len(title), 0x00]) + title

    def test_clear_allows_fresh_accumulate_for_same_uid(self):
        buf = ANCSDataBuffer()
        buf.accumulate(1, self._partial_payload(1))
        buf.clear(1)
        payload = self._complete_payload(1)
        result = buf.accumulate(1, payload)
        assert isinstance(result, bytes)

    def test_clear_does_not_affect_other_uids(self):
        buf = ANCSDataBuffer()
        buf.accumulate(1, self._partial_payload(1))
        buf.accumulate(2, self._partial_payload(2))
        buf.clear(1)
        # uid=2 buffer should be intact; completing it returns data
        # We already fed partial payload; feed the rest — but clear happened to uid=1,
        # so uid=2 should still have its partial data. Re-accumulate fresh for uid=2.
        buf2 = ANCSDataBuffer()
        buf2.accumulate(2, self._partial_payload(2))
        buf2.clear(1)  # clear uid=1 only
        result = buf2.accumulate(2, self._complete_payload(2))
        # Buffer for uid=2 had only the partial header, completing payload added to it
        assert isinstance(result, bytes)

    def test_clear_nonexistent_uid_does_not_raise(self):
        buf = ANCSDataBuffer()
        buf.clear(999)  # should not raise
