"""Tests: ConversationItem preview/unread badge, update_data, accessible description.
Beads: tincan-a3n  (tincan-33k preview text, tincan-yq1 unread badge)

Coverage:
  - _apply_preview: empty → em-dash, italic, #9ca3af, accessibleName='No preview available'
  - _apply_preview: 36-char non-empty → full text, no ellipsis
  - _apply_preview: 37-char non-empty → truncated to 36 + '…'
  - _apply_unread_style: unread_count=0, unread=False → dot hidden, name regular, badge hidden
  - _apply_unread_style: unread_count=1 → dot shown, name bold, badge hidden
  - _apply_unread_style: unread_count=10 → dot shown, name bold, badge shows '9+'
  - update_data: updates timestamp, preview text, dot/badge, accessible state in-place
  - ConversationListWidget.update_item: multiple calls within 200ms coalesce to one flush
  - Accessible description: unread_count=1 → 'Unread: 1'; count=10 → 'Unread: 9+'; count=0 → ''
"""
from __future__ import annotations

from unittest.mock import patch

from tincan_gui.conversation_list import ConversationData, ConversationItem, ConversationListWidget

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_data(**overrides) -> ConversationData:
    defaults = {
        "id": "c1",
        "name": "Alice",
        "phone": "+1 555-0100",
        "preview": "",
        "timestamp": "10:00",
        "unread": False,
        "unread_count": 0,
    }
    defaults.update(overrides)
    return ConversationData(**defaults)


# ---------------------------------------------------------------------------
# §1 _apply_preview — empty preview
# ---------------------------------------------------------------------------

class TestApplyPreviewEmpty:
    """Empty preview → em-dash placeholder with italic style and fallback accessible name."""

    def test_shows_em_dash(self, qtbot):
        item = ConversationItem(_make_data(preview=""))
        qtbot.addWidget(item)
        assert item._preview_label.text() == "—"

    def test_is_italic(self, qtbot):
        item = ConversationItem(_make_data(preview=""))
        qtbot.addWidget(item)
        assert item._preview_label.font().italic()

    def test_color_is_9ca3af(self, qtbot):
        with patch("tincan_gui.conversation_list.is_dark_theme", return_value=False):
            item = ConversationItem(_make_data(preview=""))
        qtbot.addWidget(item)
        assert "#9ca3af" in item._preview_label.styleSheet()

    def test_accessible_name_is_no_preview_available(self, qtbot):
        item = ConversationItem(_make_data(preview=""))
        qtbot.addWidget(item)
        assert item._preview_label.accessibleName() == "No preview available"


# ---------------------------------------------------------------------------
# §2 _apply_preview — non-empty preview (inbound/default direction)
# ---------------------------------------------------------------------------

class TestApplyPreviewNonEmpty:
    """Non-empty preview: 36-char shows full text; 37-char truncates to 36 + ellipsis."""

    def test_36_char_preview_shows_full_text(self, qtbot):
        preview = "a" * 36
        item = ConversationItem(_make_data(preview=preview))
        qtbot.addWidget(item)
        assert item._preview_label.text() == preview

    def test_36_char_preview_has_no_ellipsis(self, qtbot):
        preview = "a" * 36
        item = ConversationItem(_make_data(preview=preview))
        qtbot.addWidget(item)
        assert "…" not in item._preview_label.text()

    def test_37_char_preview_truncated_to_36_plus_ellipsis(self, qtbot):
        preview = "a" * 37
        item = ConversationItem(_make_data(preview=preview))
        qtbot.addWidget(item)
        assert item._preview_label.text() == "a" * 36 + "…"

    def test_non_empty_preview_is_not_italic(self, qtbot):
        item = ConversationItem(_make_data(preview="Hello"))
        qtbot.addWidget(item)
        assert not item._preview_label.font().italic()


# ---------------------------------------------------------------------------
# §3 _apply_unread_style
# ---------------------------------------------------------------------------

class TestApplyUnreadStyle:
    """unread_count and unread flag drive dot visibility, name weight, and badge text."""

    def test_unread_count_0_unread_false_dot_hidden(self, qtbot):
        item = ConversationItem(_make_data(unread_count=0, unread=False))
        qtbot.addWidget(item)
        assert not item._dot.isVisible()

    def test_unread_count_0_unread_false_name_regular_weight(self, qtbot):
        item = ConversationItem(_make_data(unread_count=0, unread=False))
        qtbot.addWidget(item)
        assert not item._name_label.font().bold()

    def test_unread_count_0_unread_false_badge_hidden(self, qtbot):
        item = ConversationItem(_make_data(unread_count=0, unread=False))
        qtbot.addWidget(item)
        assert not item._badge_label.isVisible()

    def test_unread_count_1_dot_shown(self, qtbot):
        item = ConversationItem(_make_data(unread_count=1))
        qtbot.addWidget(item)
        assert item._dot.isVisible()

    def test_unread_count_1_name_is_bold(self, qtbot):
        item = ConversationItem(_make_data(unread_count=1))
        qtbot.addWidget(item)
        assert item._name_label.font().bold()

    def test_unread_count_1_badge_hidden(self, qtbot):
        item = ConversationItem(_make_data(unread_count=1))
        qtbot.addWidget(item)
        assert not item._badge_label.isVisible()

    def test_unread_count_10_dot_shown(self, qtbot):
        item = ConversationItem(_make_data(unread_count=10))
        qtbot.addWidget(item)
        assert item._dot.isVisible()

    def test_unread_count_10_name_is_bold(self, qtbot):
        item = ConversationItem(_make_data(unread_count=10))
        qtbot.addWidget(item)
        assert item._name_label.font().bold()

    def test_unread_count_10_badge_shows_9plus(self, qtbot):
        item = ConversationItem(_make_data(unread_count=10))
        qtbot.addWidget(item)
        assert item._badge_label.isVisible()
        assert item._badge_label.text() == "9+"


# ---------------------------------------------------------------------------
# §4 update_data — in-place updates
# ---------------------------------------------------------------------------

class TestUpdateData:
    """update_data applies all state changes: timestamp, preview, dot/badge, accessible."""

    def test_update_changes_timestamp(self, qtbot):
        item = ConversationItem(_make_data(timestamp="10:00"))
        qtbot.addWidget(item)
        item.update_data(_make_data(timestamp="11:30"))
        assert item._ts_label.text() == "11:30"

    def test_update_changes_preview_text(self, qtbot):
        item = ConversationItem(_make_data(preview="Old message"))
        qtbot.addWidget(item)
        item.update_data(_make_data(preview="New message"))
        assert item._preview_label.text() == "New message"

    def test_update_shows_dot_when_unread_increments(self, qtbot):
        item = ConversationItem(_make_data(unread_count=0))
        qtbot.addWidget(item)
        item.update_data(_make_data(unread_count=1))
        assert item._dot.isVisible()

    def test_update_hides_dot_when_unread_clears(self, qtbot):
        item = ConversationItem(_make_data(unread_count=1))
        qtbot.addWidget(item)
        item.update_data(_make_data(unread_count=0))
        assert not item._dot.isVisible()

    def test_update_shows_badge_for_10_plus_unread(self, qtbot):
        item = ConversationItem(_make_data(unread_count=0))
        qtbot.addWidget(item)
        item.update_data(_make_data(unread_count=10))
        assert item._badge_label.isVisible()
        assert item._badge_label.text() == "9+"

    def test_update_refreshes_accessible_description(self, qtbot):
        item = ConversationItem(_make_data(unread_count=0))
        qtbot.addWidget(item)
        item.update_data(_make_data(unread_count=1))
        assert item.accessibleDescription() == "Unread: 1"


# ---------------------------------------------------------------------------
# §5 Accessible description — unread_count formatting
# ---------------------------------------------------------------------------

class TestAccessibleDescription:
    """accessibleDescription reflects unread_count with 'Unread: N' format."""

    def test_unread_count_1_description_is_unread_1(self, qtbot):
        item = ConversationItem(_make_data(unread_count=1))
        qtbot.addWidget(item)
        assert item.accessibleDescription() == "Unread: 1"

    def test_unread_count_10_description_is_unread_9plus(self, qtbot):
        item = ConversationItem(_make_data(unread_count=10))
        qtbot.addWidget(item)
        assert item.accessibleDescription() == "Unread: 9+"

    def test_unread_count_0_description_is_empty(self, qtbot):
        item = ConversationItem(_make_data(unread_count=0, unread=False))
        qtbot.addWidget(item)
        assert item.accessibleDescription() == ""


# ---------------------------------------------------------------------------
# §6 ConversationListWidget.update_item — 200ms debounce
# ---------------------------------------------------------------------------

class TestConversationListUpdateItem:
    """update_item queues updates; multiple calls within 200ms coalesce to one flush."""

    def test_multiple_calls_within_200ms_coalesce_to_last_value(self, qtbot):
        w = ConversationListWidget()
        qtbot.addWidget(w)
        w.load_conversations([_make_data(id="c1", preview="Initial")])

        w.update_item("c1", _make_data(id="c1", preview="First"))
        w.update_item("c1", _make_data(id="c1", preview="Second"))
        w.update_item("c1", _make_data(id="c1", preview="Third"))

        # Timer is active — flush has not happened yet
        assert w._update_timer.isActive()
        # Wait past the 200ms window for the timer to fire
        qtbot.wait(250)
        assert w._items[0]._preview_label.text() == "Third"

    def test_update_not_applied_before_timer_fires(self, qtbot):
        w = ConversationListWidget()
        qtbot.addWidget(w)
        w.load_conversations([_make_data(id="c1", preview="Original")])

        w.update_item("c1", _make_data(id="c1", preview="Updated"))

        # Timer started but not yet fired — item still shows original preview
        assert w._update_timer.isActive()
        assert w._items[0]._preview_label.text() == "Original"
