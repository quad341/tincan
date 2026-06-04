"""Tests: ThreadHeader.update_contact name/phone dedup.
Bead: tincan-maec  (commit ded7ad9)

Coverage:
  update_contact behavior:
  - name != phone: phone_label shows phone only, visible
  - name == phone: phone_label hidden (duplicate suppressed)
  - phone is empty string: phone_label hidden
  - name change preserves phone visibility correctly
"""
from __future__ import annotations

import pytest

from tincan_gui.thread_view import ThreadHeader


# ---------------------------------------------------------------------------
# §1 update_contact name/phone dedup
# ---------------------------------------------------------------------------

class TestThreadHeaderUpdateContact:
    """update_contact hides phone_label when it would duplicate the name."""

    def test_name_differs_from_phone_phone_label_visible(self, qtbot):
        header = ThreadHeader()
        qtbot.addWidget(header)

        header.update_contact("Alice", "+15550001111")

        assert not header._phone_label.isHidden()

    def test_name_differs_from_phone_phone_label_shows_phone(self, qtbot):
        header = ThreadHeader()
        qtbot.addWidget(header)

        header.update_contact("Alice", "+15550001111")

        assert header._phone_label.text() == "+15550001111"

    def test_name_equals_phone_phone_label_hidden(self, qtbot):
        header = ThreadHeader()
        qtbot.addWidget(header)
        phone = "+15550001111"

        header.update_contact(phone, phone)

        assert header._phone_label.isHidden()

    def test_name_equals_phone_phone_label_text_cleared(self, qtbot):
        header = ThreadHeader()
        qtbot.addWidget(header)
        phone = "+15550001111"

        header.update_contact(phone, phone)

        assert header._phone_label.text() == ""

    def test_empty_phone_hides_phone_label(self, qtbot):
        header = ThreadHeader()
        qtbot.addWidget(header)

        header.update_contact("Alice", "")

        assert header._phone_label.isHidden()

    def test_empty_phone_clears_label_text(self, qtbot):
        header = ThreadHeader()
        qtbot.addWidget(header)
        # First set a non-hidden phone, then clear it
        header.update_contact("Alice", "+15550001111")
        assert not header._phone_label.isHidden()

        header.update_contact("Alice", "")

        assert header._phone_label.text() == ""

    def test_name_change_to_match_phone_hides_label(self, qtbot):
        phone = "+15550001111"
        header = ThreadHeader()
        qtbot.addWidget(header)
        # Start with name != phone (not hidden)
        header.update_contact("Alice", phone)
        assert not header._phone_label.isHidden()

        # Now name == phone
        header.update_contact(phone, phone)

        assert header._phone_label.isHidden()

    def test_name_change_from_match_to_differ_shows_label(self, qtbot):
        phone = "+15550001111"
        header = ThreadHeader()
        qtbot.addWidget(header)
        # Start with name == phone (hidden)
        header.update_contact(phone, phone)
        assert header._phone_label.isHidden()

        # Now name differs from phone
        header.update_contact("Alice", phone)

        assert not header._phone_label.isHidden()
