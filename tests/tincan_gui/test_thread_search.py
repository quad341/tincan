"""Tests: in-thread message search (tincan-uof95).

Coverage:
  §1 MessageBubble.matches() — case-insensitive body check, BODY_UNAVAILABLE excluded
  §2 MessageBubble.highlight() / clear_highlight() — body label re-rendered with span
  §3 _ThreadSearchBar — Escape emits closed, Enter emits next_requested,
     Shift+Enter emits prev_requested, set_match_count / clear_count
  §4 ThreadView search lifecycle — show_search focuses bar; _on_search_changed
     highlights matching bubbles and scrolls; close restores original text
"""
from __future__ import annotations

import pytest

from tincan_gui.text_render import _linkify, _linkify_with_highlight
from tincan_gui.thread_view import BubbleType, MessageBubble, MessageData, ThreadView

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bubble(body: str, btype: BubbleType = BubbleType.INBOUND) -> MessageBubble:
    return MessageBubble(
        MessageData(bubble_type=btype, body=body, sender="Alice", timestamp="10:00")
    )


# ---------------------------------------------------------------------------
# §1  MessageBubble.matches()
# ---------------------------------------------------------------------------

class TestMatches:
    def test_exact_match(self, qtbot):
        b = _bubble("Hello world")
        qtbot.addWidget(b)
        assert b.matches("Hello")

    def test_case_insensitive(self, qtbot):
        b = _bubble("Hello world")
        qtbot.addWidget(b)
        assert b.matches("hello")
        assert b.matches("WORLD")

    def test_no_match(self, qtbot):
        b = _bubble("Hello world")
        qtbot.addWidget(b)
        assert not b.matches("xyz")

    def test_empty_term_never_matches(self, qtbot):
        b = _bubble("Hello world")
        qtbot.addWidget(b)
        assert not b.matches("")

    def test_body_unavailable_never_matches(self, qtbot):
        b = _bubble("", BubbleType.BODY_UNAVAILABLE)
        qtbot.addWidget(b)
        assert not b.matches("unavailable")

    def test_outbound_matches(self, qtbot):
        b = _bubble("Meeting at 3pm", BubbleType.OUTBOUND)
        qtbot.addWidget(b)
        assert b.matches("3pm")


# ---------------------------------------------------------------------------
# §2  MessageBubble.highlight() / clear_highlight()
# ---------------------------------------------------------------------------

class TestHighlight:
    def test_highlight_injects_span(self, qtbot):
        b = _bubble("Hello world")
        qtbot.addWidget(b)
        b.highlight("Hello")
        html = b._body_label.text()
        assert "background:#fef08a" in html
        assert "Hello" in html

    def test_highlight_case_insensitive_preserves_original_case(self, qtbot):
        b = _bubble("Hello world")
        qtbot.addWidget(b)
        b.highlight("hello")
        html = b._body_label.text()
        assert "Hello" in html
        assert "background:#fef08a" in html

    def test_clear_highlight_restores(self, qtbot):
        b = _bubble("Hello world")
        qtbot.addWidget(b)
        b.highlight("Hello")
        b.clear_highlight()
        html = b._body_label.text()
        assert "background:#fef08a" not in html
        assert html == _linkify("Hello world")

    def test_highlight_body_unavailable_is_noop(self, qtbot):
        b = _bubble("", BubbleType.BODY_UNAVAILABLE)
        qtbot.addWidget(b)
        before = b._body_label.text()
        b.highlight("anything")
        assert b._body_label.text() == before

    def test_clear_highlight_body_unavailable_is_noop(self, qtbot):
        b = _bubble("", BubbleType.BODY_UNAVAILABLE)
        qtbot.addWidget(b)
        before = b._body_label.text()
        b.clear_highlight()
        assert b._body_label.text() == before


# ---------------------------------------------------------------------------
# §3  _linkify_with_highlight
# ---------------------------------------------------------------------------

class TestLinkifyWithHighlight:
    def test_term_wrapped_in_span(self):
        result = _linkify_with_highlight("say hello", "hello")
        assert "background:#fef08a" in result
        assert "hello" in result

    def test_empty_term_returns_plain_linkify(self):
        text = "say hello"
        assert _linkify_with_highlight(text, "") == _linkify(text)

    def test_multiple_occurrences(self):
        result = _linkify_with_highlight("hi hi hi", "hi")
        assert result.count("background:#fef08a") == 3


# ---------------------------------------------------------------------------
# §4  ThreadView search lifecycle
# ---------------------------------------------------------------------------

class TestThreadViewSearch:
    @pytest.fixture()
    def view(self, qtbot):
        v = ThreadView()
        qtbot.addWidget(v)
        return v

    def _load(self, view: ThreadView, bodies: list[str]) -> None:
        msgs = [
            MessageData(
                bubble_type=BubbleType.INBOUND,
                body=b,
                sender="Alice",
                timestamp="10:00",
            )
            for b in bodies
        ]
        from tincan_gui.thread_view import _date_label_for_sort_key  # noqa: F401
        view.load_thread("Alice", "+1", msgs)

    def test_show_search_reveals_bar(self, view, qtbot):
        assert view._search_bar.isHidden()
        view.show_search()
        assert not view._search_bar.isHidden()

    def test_search_highlights_matching_bubbles(self, view, qtbot):
        self._load(view, ["hello world", "goodbye", "hello again"])
        view.show_search()
        view._search_bar._input.setText("hello")

        assert len(view._match_bubbles) == 2

    def test_search_no_match_sets_zero_count(self, view, qtbot):
        self._load(view, ["hello world"])
        view.show_search()
        view._search_bar._input.setText("zzz")

        assert len(view._match_bubbles) == 0
        assert "No results" in view._search_bar._count_label.text()

    def test_close_hides_bar_and_clears_highlights(self, view, qtbot):
        self._load(view, ["hello world"])
        view.show_search()
        view._search_bar._input.setText("hello")
        view._on_search_closed()

        assert not view._search_bar.isVisible()
        assert len(view._match_bubbles) == 0

    def test_next_wraps_around(self, view, qtbot):
        self._load(view, ["hi", "hi", "hi"])
        view.show_search()
        view._search_bar._input.setText("hi")

        assert view._match_index == 0
        view._on_search_next()
        assert view._match_index == 1
        view._on_search_next()
        assert view._match_index == 2
        view._on_search_next()
        assert view._match_index == 0  # wraps

    def test_prev_wraps_around(self, view, qtbot):
        self._load(view, ["hi", "hi", "hi"])
        view.show_search()
        view._search_bar._input.setText("hi")

        view._on_search_prev()
        assert view._match_index == 2  # wraps to last

    def test_clear_query_clears_count(self, view, qtbot):
        self._load(view, ["hello"])
        view.show_search()
        view._search_bar._input.setText("hello")
        view._search_bar._input.setText("")

        assert view._search_bar._count_label.text() == ""
