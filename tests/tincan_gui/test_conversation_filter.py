"""Tests: conversation list filter by name or phone number (tincan-u1be1).

Coverage:
  - Typing filters conversations by name (case-insensitive substring).
  - Typing a digit string filters conversations by phone number (normalize_phone).
  - Typing a formatted phone "(415) 555" matches the canonical digits.
  - Clearing the query shows all conversations.
  - No-results label shown when nothing matches; hidden when results present.
  - Filter applied immediately on text change (real-time).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QSystemTrayIcon

from tincan_gui.conversation_list import ConversationData, ConversationListWidget


@pytest.fixture(autouse=True)
def _no_tray_show():
    with patch.object(QSystemTrayIcon, "show"):
        yield


def _make_data(name: str, phone: str, preview: str = "hi") -> ConversationData:
    return ConversationData(
        id=phone, name=name, phone=phone, preview=preview, timestamp="10:00"
    )


def _visible_names(widget: ConversationListWidget) -> list[str]:
    """Return names of currently visible conversation items."""
    return [
        item.accessible_name()
        for item in widget._items
        if item.isVisible()
    ]


def _load(widget: ConversationListWidget, conversations: list[ConversationData]) -> None:
    widget.load_conversations(conversations)


# ---------------------------------------------------------------------------
# §1  Name filtering
# ---------------------------------------------------------------------------

class TestFilterByName:
    def test_name_substring_shows_match(self, qtbot):
        w = ConversationListWidget()
        qtbot.addWidget(w)
        _load(w, [_make_data("Alice", "+14155550001"), _make_data("Bob", "+14155550002")])

        w._search.setText("ali")

        visible = [item for item in w._items if item.isVisible()]
        assert len(visible) == 1
        assert visible[0]._data.name == "Alice"

    def test_name_filter_is_case_insensitive(self, qtbot):
        w = ConversationListWidget()
        qtbot.addWidget(w)
        _load(w, [_make_data("Alice", "+1"), _make_data("Bob", "+2")])

        w._search.setText("ALI")

        visible = [item for item in w._items if item.isVisible()]
        assert len(visible) == 1
        assert visible[0]._data.name == "Alice"

    def test_empty_query_shows_all(self, qtbot):
        w = ConversationListWidget()
        qtbot.addWidget(w)
        _load(w, [_make_data("Alice", "+1"), _make_data("Bob", "+2")])

        w._search.setText("ali")
        w._search.clear()

        assert len([i for i in w._items if i.isVisible()]) == 2

    def test_no_match_shows_all_hidden(self, qtbot):
        w = ConversationListWidget()
        qtbot.addWidget(w)
        _load(w, [_make_data("Alice", "+1"), _make_data("Bob", "+2")])

        w._search.setText("zzz")

        assert all(not item.isVisible() for item in w._items)

    def test_no_results_label_visible_on_no_match(self, qtbot):
        w = ConversationListWidget()
        qtbot.addWidget(w)
        _load(w, [_make_data("Alice", "+1")])

        w._search.setText("zzz")

        assert w._no_results.isVisible()

    def test_no_results_label_hidden_on_match(self, qtbot):
        w = ConversationListWidget()
        qtbot.addWidget(w)
        _load(w, [_make_data("Alice", "+1")])

        w._search.setText("ali")

        assert not w._no_results.isVisible()

    def test_no_results_label_hidden_on_empty_query(self, qtbot):
        w = ConversationListWidget()
        qtbot.addWidget(w)
        _load(w, [_make_data("Alice", "+1")])

        w._search.setText("")

        assert not w._no_results.isVisible()


# ---------------------------------------------------------------------------
# §2  Phone number filtering
# ---------------------------------------------------------------------------

class TestFilterByPhone:
    def test_digit_query_matches_phone(self, qtbot):
        w = ConversationListWidget()
        qtbot.addWidget(w)
        _load(w, [
            _make_data("Alice", "+14155550001"),
            _make_data("Bob",   "+19175550002"),
        ])

        w._search.setText("415")

        visible = [item for item in w._items if item.isVisible()]
        assert len(visible) == 1
        assert visible[0]._data.name == "Alice"

    def test_formatted_phone_query_matches(self, qtbot):
        """'(415) 555' should match +14155550001 after digit-only normalization."""
        w = ConversationListWidget()
        qtbot.addWidget(w)
        _load(w, [
            _make_data("Alice", "+14155550001"),
            _make_data("Bob",   "+19175550002"),
        ])

        w._search.setText("(415) 555")

        visible = [item for item in w._items if item.isVisible()]
        assert len(visible) == 1
        assert visible[0]._data.name == "Alice"

    def test_full_phone_number_matches(self, qtbot):
        w = ConversationListWidget()
        qtbot.addWidget(w)
        _load(w, [
            _make_data("Alice", "+14155550001"),
            _make_data("Bob",   "+19175550002"),
        ])

        w._search.setText("14155550001")

        visible = [item for item in w._items if item.isVisible()]
        assert len(visible) == 1
        assert visible[0]._data.name == "Alice"

    def test_short_code_phone_matches(self, qtbot):
        w = ConversationListWidget()
        qtbot.addWidget(w)
        _load(w, [
            _make_data("Bank Alerts", "12345"),
            _make_data("Alice", "+14155550001"),
        ])

        w._search.setText("123")

        visible = [item for item in w._items if item.isVisible()]
        assert len(visible) == 1
        assert visible[0]._data.name == "Bank Alerts"

    def test_phone_match_independent_of_name(self, qtbot):
        """A conversation with no name match but a phone match should appear."""
        w = ConversationListWidget()
        qtbot.addWidget(w)
        _load(w, [
            _make_data("Zoe Unknown", "+14085550099"),
        ])

        # "408" doesn't match "Zoe Unknown" by name but matches by phone
        w._search.setText("408")

        visible = [item for item in w._items if item.isVisible()]
        assert len(visible) == 1
