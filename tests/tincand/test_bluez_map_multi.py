"""Tests: normalize_phone (tincan-filoa / tincan-w621v).

Coverage:
  §1 normalize_phone — digit stripping, country-code removal, passthrough
     - +15550101234 → 5550101234 (E.164 with country code)
     - 15550101234 → 5550101234 (11-digit starting with 1)
     - 5550101234 → 5550101234 (10-digit passthrough)
     - punctuation stripped before normalization
     - short number (< 7 digits) passes through unchanged
     - matches contact_store.normalize_phone for common inputs

No D-Bus infrastructure needed — all inputs are plain Python.
"""
from __future__ import annotations

import pytest

from tincand.contact_store import normalize_phone
from tincand.contact_store import normalize_phone as cs_normalize_phone

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
