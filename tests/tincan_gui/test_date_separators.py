"""Tests: date separator headers in the message list (tincan-mlkka).

Coverage:
  §1 _date_label_text — converts sort_key to "Today" / "Yesterday" / date string
     - today's sort_key → "Today"
     - yesterday's sort_key → "Yesterday"
     - older date → explicit abbreviated date (e.g. "Mon Jun  2")
     - empty sort_key → empty string (no separator for undated messages)

  §2 ThreadView.load_thread — separator inserted between day-crossing messages
     - no separator widget for a single message
     - no separator when all messages share the same day
     - one separator between two messages from different days
     - two separators for three messages spanning three distinct days

  §3 ThreadView.load_thread — separator text matches expected date label
     - separator text is "Today" for today's messages
     - separator text matches the date label for older messages

  §4 ThreadView.append_message — inserts separator on day boundary
     - no separator when appended message is same day as the last loaded message
     - separator inserted when appended message crosses a day boundary
"""
from __future__ import annotations

import datetime
from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QLabel, QSystemTrayIcon

from tincan_gui.thread_view import (
    BubbleType,
    MessageData,
    ThreadView,
    _date_label_text,
    _get_today,
)

_TODAY = datetime.date(2026, 6, 5)
_YESTERDAY = _TODAY - datetime.timedelta(days=1)
_TWO_DAYS_AGO = _TODAY - datetime.timedelta(days=2)


def _sk(d: datetime.date, hour: int = 10) -> str:
    """Build a sort_key string from a date and optional hour."""
    return d.strftime("%Y%m%d") + f"T{hour:02d}0000"


def _msg(body: str, d: datetime.date, hour: int = 10) -> MessageData:
    return MessageData(
        bubble_type=BubbleType.INBOUND,
        body=body,
        sender="Alice",
        timestamp=f"{hour:02d}:00",
        sort_key=_sk(d, hour),
    )


@pytest.fixture(autouse=True)
def _no_tray_show():
    with patch.object(QSystemTrayIcon, "show"):
        yield


# ---------------------------------------------------------------------------
# §1 _date_label_text
# ---------------------------------------------------------------------------

class TestDateLabelText:
    """_date_label_text converts sort_key to human-readable date labels."""

    def test_today_sort_key_returns_today(self):
        result = _date_label_text(_sk(_TODAY), today=_TODAY)
        assert result == "Today"

    def test_yesterday_sort_key_returns_yesterday(self):
        result = _date_label_text(_sk(_YESTERDAY), today=_TODAY)
        assert result == "Yesterday"

    def test_older_date_returns_explicit_date_string(self):
        result = _date_label_text(_sk(_TWO_DAYS_AGO), today=_TODAY)
        assert result != "Today"
        assert result != "Yesterday"
        assert result != ""

    def test_empty_sort_key_returns_empty_string(self):
        result = _date_label_text("", today=_TODAY)
        assert result == ""

    def test_older_date_string_contains_month(self):
        result = _date_label_text(_sk(datetime.date(2026, 3, 15)), today=_TODAY)
        assert "Mar" in result or "03" in result or "3" in result


# ---------------------------------------------------------------------------
# §2 ThreadView.load_thread — separator insertion
# ---------------------------------------------------------------------------

def _count_date_separator_labels(view: ThreadView) -> list[str]:
    """Return the text of all date separator widgets in the thread view."""
    layout = view._messages_layout
    labels = []
    for i in range(layout.count()):
        w = layout.itemAt(i).widget()
        if w is not None and getattr(w, "_is_date_separator", False):
            labels.append(w.text())
    return labels


class TestLoadThreadSeparators:
    """load_thread inserts DateSeparator widgets between messages from different days."""

    def test_single_message_has_no_separator(self, qtbot):
        view = ThreadView()
        qtbot.addWidget(view)
        with patch("tincan_gui.thread_view._get_today", return_value=_TODAY):
            view.load_thread("Alice", "+1555", [_msg("hi", _TODAY)])
        seps = _count_date_separator_labels(view)
        assert seps == [], f"Expected no separators, got: {seps}"

    def test_same_day_messages_have_no_separator(self, qtbot):
        view = ThreadView()
        qtbot.addWidget(view)
        msgs = [_msg("a", _TODAY, 9), _msg("b", _TODAY, 10), _msg("c", _TODAY, 11)]
        with patch("tincan_gui.thread_view._get_today", return_value=_TODAY):
            view.load_thread("Alice", "+1555", msgs)
        seps = _count_date_separator_labels(view)
        assert seps == [], f"Expected no separators for same-day messages, got: {seps}"

    def test_two_days_gets_one_separator(self, qtbot):
        view = ThreadView()
        qtbot.addWidget(view)
        msgs = [_msg("old", _YESTERDAY), _msg("new", _TODAY)]
        with patch("tincan_gui.thread_view._get_today", return_value=_TODAY):
            view.load_thread("Alice", "+1555", msgs)
        seps = _count_date_separator_labels(view)
        assert len(seps) == 1, f"Expected 1 separator, got {len(seps)}: {seps}"

    def test_three_days_gets_two_separators(self, qtbot):
        view = ThreadView()
        qtbot.addWidget(view)
        msgs = [
            _msg("old", _TWO_DAYS_AGO),
            _msg("mid", _YESTERDAY),
            _msg("new", _TODAY),
        ]
        with patch("tincan_gui.thread_view._get_today", return_value=_TODAY):
            view.load_thread("Alice", "+1555", msgs)
        seps = _count_date_separator_labels(view)
        assert len(seps) == 2, f"Expected 2 separators, got {len(seps)}: {seps}"


# ---------------------------------------------------------------------------
# §3 ThreadView.load_thread — separator text content
# ---------------------------------------------------------------------------

class TestLoadThreadSeparatorText:
    """Separator labels carry the correct date text from _date_label_text."""

    def test_separator_for_today_reads_today(self, qtbot):
        view = ThreadView()
        qtbot.addWidget(view)
        msgs = [_msg("old", _YESTERDAY), _msg("new", _TODAY)]
        with patch("tincan_gui.thread_view._get_today", return_value=_TODAY):
            view.load_thread("Alice", "+1555", msgs)
        seps = _count_date_separator_labels(view)
        assert "Today" in seps, f"Expected 'Today' among separators, got: {seps}"

    def test_separator_for_yesterday_reads_yesterday(self, qtbot):
        view = ThreadView()
        qtbot.addWidget(view)
        msgs = [_msg("old", _TWO_DAYS_AGO), _msg("mid", _YESTERDAY)]
        with patch("tincan_gui.thread_view._get_today", return_value=_TODAY):
            view.load_thread("Alice", "+1555", msgs)
        seps = _count_date_separator_labels(view)
        assert "Yesterday" in seps, f"Expected 'Yesterday' among separators, got: {seps}"


# ---------------------------------------------------------------------------
# §4 ThreadView.append_message — separator on day boundary
# ---------------------------------------------------------------------------

class TestAppendMessageSeparator:
    """append_message inserts a separator when the date advances past midnight."""

    def test_same_day_append_no_separator(self, qtbot):
        view = ThreadView()
        qtbot.addWidget(view)
        with patch("tincan_gui.thread_view._get_today", return_value=_TODAY):
            view.load_thread("Alice", "+1555", [_msg("morning", _TODAY, 8)])
            view.append_message(_msg("noon", _TODAY, 12))
        seps = _count_date_separator_labels(view)
        assert seps == [], f"Expected no new separator on same-day append, got: {seps}"

    def test_new_day_append_inserts_separator(self, qtbot):
        view = ThreadView()
        qtbot.addWidget(view)
        with patch("tincan_gui.thread_view._get_today", return_value=_TODAY):
            view.load_thread("Alice", "+1555", [_msg("yesterday msg", _YESTERDAY)])
            view.append_message(_msg("today msg", _TODAY))
        seps = _count_date_separator_labels(view)
        assert len(seps) == 1, f"Expected 1 separator on day-boundary append, got: {seps}"
        assert seps[0] == "Today"
