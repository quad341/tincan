"""Tests: _is_dialable() pure function + coverage cross-reference.
Bead: tincan-wey7  (reviewer gap — tincan-gw29 + tincan-6b9m)

mark_last_send_failed() / MessageBubble.set_send_failed():
  Already covered in tests/tincan_gui/test_on_send.py §5-§6.
  No additional tests needed here.

_name_to_phone persistence across polls:
  Already covered in tests/tincand/test_name_to_phone.py §1.

Coverage added here:

§1 _is_dialable() — pure function
   - 7-digit number is dialable
   - 6-digit string is NOT dialable
   - phone with formatting (+1 country code) stripped and counted
   - 10-digit US number without formatting is dialable
   - display name "Alice" (no digits) is NOT dialable
   - name-keyed thread sender ("john doe") is NOT dialable
   - empty string is NOT dialable
   - mixed alphanumeric with ≥7 digits is dialable
"""
from __future__ import annotations

from tincan_gui.main import _is_dialable


# ---------------------------------------------------------------------------
# §1 _is_dialable() — pure function
# ---------------------------------------------------------------------------

class TestIsDialable:
    """≥7 digits → True; <7 digits or no digits → False."""

    def test_seven_digit_number_is_dialable(self):
        assert _is_dialable("5550001") is True

    def test_six_digit_number_is_not_dialable(self):
        assert _is_dialable("555000") is False

    def test_ten_digit_us_number_is_dialable(self):
        assert _is_dialable("5550001111") is True

    def test_formatted_us_number_is_dialable(self):
        assert _is_dialable("+15550001111") is True

    def test_formatted_nanp_with_parens_is_dialable(self):
        assert _is_dialable("(555) 000-1111") is True

    def test_display_name_no_digits_is_not_dialable(self):
        assert _is_dialable("Alice") is False

    def test_name_keyed_sender_is_not_dialable(self):
        assert _is_dialable("john doe") is False

    def test_empty_string_is_not_dialable(self):
        assert _is_dialable("") is False

    def test_name_with_some_digits_below_threshold_is_not_dialable(self):
        # "Bob 12" has only 2 digits
        assert _is_dialable("Bob 12") is False

    def test_mixed_alphanum_with_seven_digits_is_dialable(self):
        # "abc1234567" — 7 digits embedded
        assert _is_dialable("abc1234567") is True

    def test_exactly_seven_digits_boundary(self):
        # Boundary: exactly 7 digits
        assert _is_dialable("1234567") is True

    def test_six_digits_boundary(self):
        # One below boundary: 6 digits
        assert _is_dialable("123456") is False
