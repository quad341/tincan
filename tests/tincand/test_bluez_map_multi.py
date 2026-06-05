"""Tests: normalize_phone, build_bmsg_multi, _parse_participants_from_bmsg.
Bead: tincan-filoa

Coverage:
  §1 normalize_phone — digit stripping, country-code removal, passthrough
     - +15550101234 → 5550101234 (E.164 with country code)
     - 15550101234 → 5550101234 (11-digit starting with 1)
     - 5550101234 → 5550101234 (10-digit passthrough)
     - punctuation stripped before normalization
     - short number (< 7 digits) passes through unchanged
     - matches contact_store.normalize_phone for common inputs
  §2 build_bmsg_multi — multi-recipient bMessage format
     - 2 recipients → 2 VCARDs inside BENV
     - 5 recipients → 5 VCARDs inside BENV
     - TYPE:MMS present in output
     - FOLDER:telecom/msg/outbox present
     - each recipient has own BEGIN:VCARD/END:VCARD pair
     - body present inside BEGIN:MSG/END:MSG block
     - LENGTH byte-counts the BEGIN:MSG…END:MSG block
     - custom msg_type parameter honored (overrides MMS default)
     - 1:1 build_bmsg unchanged: TYPE:SMS_GSM, single VCARD in BENV
  §3 _parse_participants_from_bmsg — TEL extraction from bMessage
     - well-formed BENV with 2+ TEL lines → all values returned, normalized
     - TEL;TYPE=CELL variant: key split on ';' → still extracted
     - absent BENV section → returns [] without exception
     - malformed input (no structure) → returns [] without raising
     - empty string → returns []

No D-Bus infrastructure needed — all inputs are plain Python.
"""
from __future__ import annotations

import re

import pytest

from tincand.backends.bluez_map import (
    _parse_participants_from_bmsg,
    build_bmsg,
    build_bmsg_multi,
    normalize_phone,
)
from tincand.contact_store import normalize_phone as cs_normalize_phone

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VCARD_COUNT_RE = re.compile(r"BEGIN:VCARD")
_MSG_BLOCK_RE = re.compile(r"(BEGIN:MSG\r\n.*?END:MSG\r\n)", re.DOTALL)
_LENGTH_RE = re.compile(r"^LENGTH:(\d+)\r?$", re.MULTILINE)


def _count_vcards_in_benv(bmsg: str) -> int:
    """Count BEGIN:VCARD occurrences inside the BEGIN:BENV…END:BENV block."""
    benv_start = bmsg.find("BEGIN:BENV")
    benv_end = bmsg.find("END:BENV", benv_start)
    if benv_start < 0 or benv_end < 0:
        return 0
    benv = bmsg[benv_start:benv_end]
    return len(_VCARD_COUNT_RE.findall(benv))


def _parse_length(bmsg: str) -> int:
    m = _LENGTH_RE.search(bmsg)
    return int(m.group(1)) if m else -1


def _msg_block_bytes(bmsg: str) -> int:
    m = _MSG_BLOCK_RE.search(bmsg)
    return len(m.group(1).encode("utf-8")) if m else -1


# ---------------------------------------------------------------------------
# §1 normalize_phone
# ---------------------------------------------------------------------------

class TestNormalizePhoneE164:
    """E.164 and country-code variants reduce to 10-digit canonical form."""

    def test_e164_plus_country_code_strips_to_10(self):
        assert normalize_phone("+15550101234") == "5550101234"

    def test_11_digit_leading_one_strips_to_10(self):
        assert normalize_phone("15550101234") == "5550101234"

    def test_10_digit_passthrough(self):
        assert normalize_phone("5550101234") == "5550101234"

    def test_formatted_e164_strips_punctuation_and_country_code(self):
        assert normalize_phone("+1 (555) 010-1234") == "5550101234"

    def test_dashes_and_spaces_stripped(self):
        assert normalize_phone("555-010-1234") == "5550101234"


class TestNormalizePhoneShortNumbers:
    """Short numbers (below threshold) pass through unchanged."""

    def test_7_digit_number_no_truncation(self):
        result = normalize_phone("1234567")
        assert result == "1234567"

    def test_sub_7_digit_passthrough(self):
        result = normalize_phone("12345")
        assert result == "12345"

    def test_empty_string_passthrough(self):
        assert normalize_phone("") == ""


class TestNormalizePhoneMatchesContactStore:
    """normalize_phone in bluez_map must agree with contact_store.normalize_phone."""

    @pytest.mark.parametrize("raw", [
        "+15550101234",
        "15550101234",
        "5550101234",
        "+1 (555) 010-1234",
        "555-010-1234",
    ])
    def test_matches_contact_store_for_common_inputs(self, raw):
        assert normalize_phone(raw) == cs_normalize_phone(raw)


# ---------------------------------------------------------------------------
# §2 build_bmsg_multi
# ---------------------------------------------------------------------------

class TestBuildBmsgMultiVcardCount:
    """Correct number of recipient VCARDs appear inside the BENV block."""

    def test_two_recipients_produce_two_vcards_in_benv(self):
        bmsg = build_bmsg_multi(["5550101234", "5550105678"], "Hello group")
        assert _count_vcards_in_benv(bmsg) == 2

    def test_five_recipients_produce_five_vcards_in_benv(self):
        numbers = [f"555010000{i}" for i in range(5)]
        bmsg = build_bmsg_multi(numbers, "Group message")
        assert _count_vcards_in_benv(bmsg) == 5

    def test_each_recipient_has_own_begin_end_vcard_pair(self):
        bmsg = build_bmsg_multi(["5550101234", "5550105678"], "Hi")
        benv_start = bmsg.find("BEGIN:BENV")
        benv_end = bmsg.find("END:BENV", benv_start)
        benv = bmsg[benv_start:benv_end]
        assert benv.count("BEGIN:VCARD") == benv.count("END:VCARD") == 2


class TestBuildBmsgMultiFields:
    """Required header fields are present and correct."""

    def test_type_mms_present(self):
        bmsg = build_bmsg_multi(["5550101234", "5550105678"], "Hello")
        assert "TYPE:MMS" in bmsg

    def test_folder_is_outbox(self):
        bmsg = build_bmsg_multi(["5550101234", "5550105678"], "Hello")
        assert "FOLDER:telecom/msg/outbox" in bmsg

    def test_body_present_in_msg_block(self):
        body = "Group MMS body text"
        bmsg = build_bmsg_multi(["5550101234", "5550105678"], body)
        assert body in bmsg

    def test_begin_benv_present(self):
        bmsg = build_bmsg_multi(["5550101234", "5550105678"], "Hello")
        assert "BEGIN:BENV" in bmsg

    def test_end_benv_present(self):
        bmsg = build_bmsg_multi(["5550101234", "5550105678"], "Hello")
        assert "END:BENV" in bmsg

    def test_custom_msg_type_honored(self):
        bmsg = build_bmsg_multi(["5550101234", "5550105678"], "Hello", msg_type="SMS_GSM")
        assert "TYPE:SMS_GSM" in bmsg
        assert "TYPE:MMS" not in bmsg


class TestBuildBmsgMultiLength:
    """LENGTH field byte-counts the BEGIN:MSG…END:MSG block."""

    def test_length_matches_msg_block_byte_count(self):
        bmsg = build_bmsg_multi(["5550101234", "5550105678"], "Hello")
        assert _parse_length(bmsg) == _msg_block_bytes(bmsg)

    def test_length_correct_for_utf8_body(self):
        body = "café 🎉"
        bmsg = build_bmsg_multi(["5550101234", "5550105678"], body)
        assert _parse_length(bmsg) == _msg_block_bytes(bmsg)


class TestBuildBmsgRegressionOneToOne:
    """1:1 build_bmsg is not affected by the multi-recipient change."""

    def test_1to1_type_is_sms_gsm(self):
        bmsg = build_bmsg("5550101234", "Hello")
        assert "TYPE:SMS_GSM" in bmsg

    def test_1to1_has_single_vcard_in_benv(self):
        bmsg = build_bmsg("5550101234", "Hello")
        assert _count_vcards_in_benv(bmsg) == 1

    def test_1to1_no_mms_type(self):
        bmsg = build_bmsg("5550101234", "Hello")
        assert "TYPE:MMS" not in bmsg


# ---------------------------------------------------------------------------
# §3 _parse_participants_from_bmsg
# ---------------------------------------------------------------------------

def _make_bmsg_with_tels(*numbers: str, tel_variant: str = "TEL") -> str:
    """Minimal bMessage with the given phone numbers as TEL lines inside BENV."""
    vcards = ""
    for n in numbers:
        vcards += (
            "BEGIN:VCARD\r\n"
            "VERSION:2.1\r\n"
            f"{tel_variant}:{n}\r\n"
            "END:VCARD\r\n"
        )
    return (
        "BEGIN:BMSG\r\n"
        "VERSION:1.0\r\n"
        "TYPE:MMS\r\n"
        "FOLDER:telecom/msg/outbox\r\n"
        "BEGIN:BENV\r\n"
        + vcards +
        "BEGIN:BBODY\r\n"
        "BEGIN:MSG\r\nHi\r\nEND:MSG\r\n"
        "END:BBODY\r\n"
        "END:BENV\r\n"
        "END:BMSG\r\n"
    )


class TestParseParticipantsFromBmsg:
    """_parse_participants_from_bmsg extracts and normalizes TEL values from BENV."""

    def test_two_numbers_returned_normalized(self):
        bmsg = _make_bmsg_with_tels("+15550101234", "+15550105678")
        result = _parse_participants_from_bmsg(bmsg)
        assert sorted(result) == sorted(["5550101234", "5550105678"])

    def test_three_numbers_all_returned(self):
        bmsg = _make_bmsg_with_tels("+15550101234", "+15550105678", "+15550109999")
        result = _parse_participants_from_bmsg(bmsg)
        assert len(result) == 3

    def test_tel_type_variant_extracted(self):
        # TEL;TYPE=CELL:+15550101234 — key split on ';' so still extracted
        bmsg = _make_bmsg_with_tels("+15550101234", tel_variant="TEL;TYPE=CELL")
        result = _parse_participants_from_bmsg(bmsg)
        assert "5550101234" in result

    def test_absent_benv_returns_empty_list(self):
        bmsg = (
            "BEGIN:BMSG\r\n"
            "VERSION:1.0\r\n"
            "TYPE:MMS\r\n"
            "END:BMSG\r\n"
        )
        result = _parse_participants_from_bmsg(bmsg)
        assert result == []

    def test_malformed_input_returns_empty_list_without_raising(self):
        result = _parse_participants_from_bmsg("not a bMessage at all")
        assert result == []

    def test_empty_string_returns_empty_list(self):
        result = _parse_participants_from_bmsg("")
        assert result == []

    def test_numbers_are_normalized_via_normalize_phone(self):
        # +15550101234 should normalize to 5550101234, not the raw string
        bmsg = _make_bmsg_with_tels("+15550101234")
        result = _parse_participants_from_bmsg(bmsg)
        assert "+15550101234" not in result
        assert "5550101234" in result
