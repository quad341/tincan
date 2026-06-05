"""Tests: long unbroken words get <wbr> break hints in message bubbles (tincan-5hcyf).

Coverage:
  - _break_long_words inserts <wbr> every 30 chars in a long plain token.
  - _break_long_words leaves short words unchanged.
  - _break_long_words resets count at whitespace boundaries.
  - _break_long_words does not insert <wbr> inside HTML tag attributes (href=).
  - _linkify output contains <wbr> for a body with a 60-char unbroken word.
  - _linkify short text is unchanged (no spurious <wbr>).
  - MessageBubble body label text contains <wbr> for a long-word message.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QSystemTrayIcon

from tincan_gui.thread_view import (
    BubbleType,
    MessageBubble,
    MessageData,
    _break_long_words,
    _linkify,
)


@pytest.fixture(autouse=True)
def _no_tray_show():
    with patch.object(QSystemTrayIcon, "show"):
        yield


# ---------------------------------------------------------------------------
# §1 _break_long_words — core helper
# ---------------------------------------------------------------------------

class TestBreakLongWords:
    """_break_long_words inserts <wbr> every 30 chars in long continuous sequences."""

    def test_long_word_gets_wbr_at_30_chars(self):
        word = "a" * 31
        result = _break_long_words(word)
        assert "<wbr>" in result

    def test_wbr_inserted_after_exactly_30_chars(self):
        word = "a" * 30 + "b"
        result = _break_long_words(word)
        assert result == "a" * 30 + "<wbr>" + "b"

    def test_short_word_unchanged(self):
        word = "hello"
        result = _break_long_words(word)
        assert result == "hello"
        assert "<wbr>" not in result

    def test_29_chars_no_wbr(self):
        word = "a" * 29
        result = _break_long_words(word)
        assert "<wbr>" not in result

    def test_whitespace_resets_counter(self):
        # 29 a's, space, 29 b's — neither run reaches 30, so no <wbr>
        text = "a" * 29 + " " + "b" * 29
        result = _break_long_words(text)
        assert "<wbr>" not in result

    def test_two_wbr_in_very_long_word(self):
        word = "x" * 61
        result = _break_long_words(word)
        assert result.count("<wbr>") == 2

    def test_does_not_insert_wbr_inside_href_attribute(self):
        long_url = "https://example.com/" + "a" * 40
        html = f'<a href="{long_url}">{long_url}</a>'
        result = _break_long_words(html)
        # href attribute must remain intact
        assert f'href="{long_url}"' in result

    def test_inserts_wbr_in_link_display_text(self):
        long_url = "https://example.com/" + "a" * 40
        html = f'<a href="{long_url}">{long_url}</a>'
        result = _break_long_words(html)
        # Display text (between > and <) should have <wbr> inserted
        display_start = result.index(">") + 1
        display_end = result.rindex("<")
        display = result[display_start:display_end]
        assert "<wbr>" in display

    def test_empty_string_unchanged(self):
        assert _break_long_words("") == ""


# ---------------------------------------------------------------------------
# §2 _linkify — long words in output get <wbr>
# ---------------------------------------------------------------------------

class TestLinkifyBreaksLongWords:
    """_linkify must include <wbr> hints for long unbroken words."""

    def test_60char_word_has_wbr(self):
        word = "z" * 60
        result = _linkify(word)
        assert "<wbr>" in result

    def test_short_message_no_wbr(self):
        result = _linkify("Hello, world!")
        assert "<wbr>" not in result

    def test_url_href_not_broken(self):
        long_url = "https://example.com/" + "x" * 40
        result = _linkify(f"Check {long_url}")
        assert f'href="{long_url}"' in result


# ---------------------------------------------------------------------------
# §3 MessageBubble — body label text has <wbr> for long-word body
# ---------------------------------------------------------------------------

class TestMessageBubbleLongWordWrap:
    """MessageBubble body label must contain <wbr> for a body with a 60-char word."""

    def test_long_word_bubble_body_contains_wbr(self, qtbot):
        long_word = "q" * 60
        data = MessageData(BubbleType.INBOUND, long_word, "Alice", "10:00")
        bubble = MessageBubble(data)
        qtbot.addWidget(bubble)

        body_label = bubble._body_label
        assert "<wbr>" in body_label.text()

    def test_normal_message_body_has_no_wbr(self, qtbot):
        data = MessageData(BubbleType.OUTBOUND, "Hello, world!", "", "10:00")
        bubble = MessageBubble(data)
        qtbot.addWidget(bubble)

        body_label = bubble._body_label
        assert "<wbr>" not in body_label.text()
