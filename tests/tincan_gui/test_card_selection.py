"""Tests: unified card selection state — colors, contrast, focus ring, unread regression.
Bead: tincan-nlm6 (parent: tincan-afqk)
Builder beads: tincan-rxmc (core styling), tincan-65av (focus ring)

Coverage:
  §1 Selection state light mode — frame bg, border (2px), name/ts/preview colors,
     deselect restore, outer bg transparent
  §2 Selection state dark mode — frame bg, border (2px), name/ts/preview colors
  §3 WCAG 2.1 AA contrast (pure math) — 4 selected-state color pairs, spec minimums
  §4 Focus ring independence — FOCUS_STYLESHEET spec, StrongFocus policy, no outline:none
  §5 Unread regression — dot and badge unaffected by set_selected() calls

Builder: add preview_label_color() to ConversationItem (same pattern as name_label_color).
"""
from __future__ import annotations

from unittest.mock import patch

from PySide6.QtCore import Qt

from tincan_gui.conversation_list import ConversationData, ConversationItem
from tincan_gui.theme import FOCUS_STYLESHEET

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_data(**overrides) -> ConversationData:
    defaults = {
        "id": "c1",
        "name": "Alice",
        "phone": "+1 555-0100",
        "preview": "Hey there",
        "timestamp": "10:00",
        "unread": False,
        "unread_count": 0,
    }
    defaults.update(overrides)
    return ConversationData(**defaults)


def _linearize(c: int) -> float:
    s = c / 255.0
    return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4


def _relative_luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _linearize(r) + 0.7152 * _linearize(g) + 0.0722 * _linearize(b)


def _contrast_ratio(fg: str, bg: str) -> float:
    l1 = _relative_luminance(fg)
    l2 = _relative_luminance(bg)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


# ---------------------------------------------------------------------------
# §1 Selection state — light mode
# ---------------------------------------------------------------------------

class TestSelectionStateLightMode:
    """set_selected(True/False) in light mode applies correct frame and label colors."""

    def test_frame_bg_is_bfdbfe_when_selected(self, qtbot):
        with patch("tincan_gui.conversation_list.is_dark_theme", return_value=False):
            item = ConversationItem(_make_data())
        qtbot.addWidget(item)
        item.set_selected(True)
        assert "#bfdbfe" in item._frame.styleSheet()

    def test_frame_border_color_is_93c5fd_when_selected(self, qtbot):
        with patch("tincan_gui.conversation_list.is_dark_theme", return_value=False):
            item = ConversationItem(_make_data())
        qtbot.addWidget(item)
        item.set_selected(True)
        assert "#93c5fd" in item._frame.styleSheet()

    def test_frame_border_is_2px_when_selected(self, qtbot):
        with patch("tincan_gui.conversation_list.is_dark_theme", return_value=False):
            item = ConversationItem(_make_data())
        qtbot.addWidget(item)
        item.set_selected(True)
        assert "2px" in item._frame.styleSheet()

    def test_name_label_color_is_1e40af_when_selected(self, qtbot):
        with patch("tincan_gui.conversation_list.is_dark_theme", return_value=False):
            item = ConversationItem(_make_data())
        qtbot.addWidget(item)
        item.set_selected(True)
        assert item.name_label_color().lower() == "#1e40af"

    def test_timestamp_label_color_is_374151_when_selected(self, qtbot):
        with patch("tincan_gui.conversation_list.is_dark_theme", return_value=False):
            item = ConversationItem(_make_data())
        qtbot.addWidget(item)
        item.set_selected(True)
        assert item.timestamp_label_color().lower() == "#374151"

    def test_preview_label_color_is_374151_when_selected(self, qtbot):
        with patch("tincan_gui.conversation_list.is_dark_theme", return_value=False):
            item = ConversationItem(_make_data(preview="See you soon"))
        qtbot.addWidget(item)
        item.set_selected(True)
        assert item.preview_label_color().lower() == "#374151"

    def test_outer_widget_stylesheet_contains_transparent_when_selected(self, qtbot):
        with patch("tincan_gui.conversation_list.is_dark_theme", return_value=False):
            item = ConversationItem(_make_data())
        qtbot.addWidget(item)
        item.set_selected(True)
        assert "transparent" in item.styleSheet()

    def test_deselect_removes_selected_bg_from_frame(self, qtbot):
        with patch("tincan_gui.conversation_list.is_dark_theme", return_value=False):
            item = ConversationItem(_make_data())
        qtbot.addWidget(item)
        item.set_selected(True)
        item.set_selected(False)
        assert "#bfdbfe" not in item._frame.styleSheet()

    def test_deselect_restores_default_card_bg(self, qtbot):
        with patch("tincan_gui.conversation_list.is_dark_theme", return_value=False):
            item = ConversationItem(_make_data())
        qtbot.addWidget(item)
        item.set_selected(True)
        item.set_selected(False)
        assert "#ffffff" in item._frame.styleSheet()

    def test_deselect_restores_1px_border(self, qtbot):
        with patch("tincan_gui.conversation_list.is_dark_theme", return_value=False):
            item = ConversationItem(_make_data())
        qtbot.addWidget(item)
        item.set_selected(True)
        item.set_selected(False)
        assert "2px" not in item._frame.styleSheet()
        assert "1px" in item._frame.styleSheet()


# ---------------------------------------------------------------------------
# §2 Selection state — dark mode
# ---------------------------------------------------------------------------

class TestSelectionStateDarkMode:
    """set_selected(True) in dark mode applies dark-palette card and label colors."""

    def test_frame_bg_is_1e3a5f_when_selected_dark(self, qtbot):
        with patch("tincan_gui.conversation_list.is_dark_theme", return_value=True):
            item = ConversationItem(_make_data())
        qtbot.addWidget(item)
        item.set_selected(True)
        assert "#1e3a5f" in item._frame.styleSheet()

    def test_frame_border_is_1d4ed8_when_selected_dark(self, qtbot):
        with patch("tincan_gui.conversation_list.is_dark_theme", return_value=True):
            item = ConversationItem(_make_data())
        qtbot.addWidget(item)
        item.set_selected(True)
        assert "#1d4ed8" in item._frame.styleSheet()

    def test_frame_border_is_2px_when_selected_dark(self, qtbot):
        with patch("tincan_gui.conversation_list.is_dark_theme", return_value=True):
            item = ConversationItem(_make_data())
        qtbot.addWidget(item)
        item.set_selected(True)
        assert "2px" in item._frame.styleSheet()

    def test_name_label_color_is_93c5fd_when_selected_dark(self, qtbot):
        with patch("tincan_gui.conversation_list.is_dark_theme", return_value=True):
            item = ConversationItem(_make_data())
        qtbot.addWidget(item)
        item.set_selected(True)
        assert item.name_label_color().lower() == "#93c5fd"

    def test_timestamp_label_color_is_a1a1aa_when_selected_dark(self, qtbot):
        with patch("tincan_gui.conversation_list.is_dark_theme", return_value=True):
            item = ConversationItem(_make_data())
        qtbot.addWidget(item)
        item.set_selected(True)
        assert item.timestamp_label_color().lower() == "#a1a1aa"

    def test_preview_label_color_is_b4c6e0_when_selected_dark(self, qtbot):
        with patch("tincan_gui.conversation_list.is_dark_theme", return_value=True):
            item = ConversationItem(_make_data(preview="Hi"))
        qtbot.addWidget(item)
        item.set_selected(True)
        assert item.preview_label_color().lower() == "#b4c6e0"


# ---------------------------------------------------------------------------
# §3 WCAG 2.1 AA contrast — selected state color pairs (pure math, no PySide6)
# ---------------------------------------------------------------------------

class TestSelectionWcagContrast:
    """Selected-state color pairs satisfy WCAG 2.1 AA (≥4.5:1) and spec-documented minimums."""

    def test_light_name_on_selected_bg_meets_aa(self):
        # #1e40af on #bfdbfe — spec ≥4.7:1
        assert _contrast_ratio("#1e40af", "#bfdbfe") >= 4.5

    def test_light_preview_on_selected_bg_meets_aa(self):
        # #374151 on #bfdbfe — spec ≥5.4:1
        assert _contrast_ratio("#374151", "#bfdbfe") >= 4.5

    def test_dark_name_on_selected_bg_meets_aa(self):
        # #93c5fd on #1e3a5f — spec ≥4.5:1
        assert _contrast_ratio("#93c5fd", "#1e3a5f") >= 4.5

    def test_dark_preview_on_selected_bg_meets_aa(self):
        # #b4c6e0 on #1e3a5f — spec ≥5.0:1
        assert _contrast_ratio("#b4c6e0", "#1e3a5f") >= 4.5

    def test_light_name_on_selected_bg_spec_minimum(self):
        ratio = _contrast_ratio("#1e40af", "#bfdbfe")
        assert ratio >= 4.7, f"Expected ≥4.7 per spec, got {ratio:.2f}"

    def test_light_preview_on_selected_bg_spec_minimum(self):
        ratio = _contrast_ratio("#374151", "#bfdbfe")
        assert ratio >= 5.4, f"Expected ≥5.4 per spec, got {ratio:.2f}"

    def test_dark_preview_on_selected_bg_spec_minimum(self):
        ratio = _contrast_ratio("#b4c6e0", "#1e3a5f")
        assert ratio >= 5.0, f"Expected ≥5.0 per spec, got {ratio:.2f}"


# ---------------------------------------------------------------------------
# §4 Focus ring independence (tincan-65av)
# ---------------------------------------------------------------------------

class TestFocusRingIndependence:
    """Focus ring spec is correct and is independent of card selection state."""

    def test_focus_stylesheet_specifies_2px_dashed_blue(self):
        assert "2px dashed #3b82f6" in FOCUS_STYLESHEET

    def test_focus_stylesheet_targets_qwidget_focus(self):
        assert "QWidget:focus" in FOCUS_STYLESHEET

    def test_focus_stylesheet_includes_outline_offset(self):
        assert "outline-offset" in FOCUS_STYLESHEET

    def test_conversation_item_has_strong_focus_policy_by_default(self, qtbot):
        item = ConversationItem(_make_data())
        qtbot.addWidget(item)
        assert item.focusPolicy() == Qt.StrongFocus

    def test_strong_focus_policy_preserved_after_select(self, qtbot):
        item = ConversationItem(_make_data())
        qtbot.addWidget(item)
        item.set_selected(True)
        assert item.focusPolicy() == Qt.StrongFocus

    def test_strong_focus_policy_preserved_after_deselect(self, qtbot):
        item = ConversationItem(_make_data())
        qtbot.addWidget(item)
        item.set_selected(True)
        item.set_selected(False)
        assert item.focusPolicy() == Qt.StrongFocus

    def test_selection_stylesheet_does_not_suppress_focus_outline(self, qtbot):
        # set_selected() must not inject 'outline: none' which would kill the focus ring.
        item = ConversationItem(_make_data())
        qtbot.addWidget(item)
        item.set_selected(True)
        combined = item.styleSheet() + item._frame.styleSheet()
        assert "outline: none" not in combined
        assert "outline:none" not in combined


# ---------------------------------------------------------------------------
# §5 Unread regression — badge and dot unaffected by card selection change
# ---------------------------------------------------------------------------

class TestUnreadRegressionOnSelection:
    """Unread dot and badge survive set_selected() calls in both directions."""

    def test_unread_dot_remains_visible_after_select(self, qtbot):
        item = ConversationItem(_make_data(unread_count=1))
        qtbot.addWidget(item)
        assert item._dot.isVisible()
        item.set_selected(True)
        assert item._dot.isVisible()

    def test_unread_dot_remains_visible_after_deselect(self, qtbot):
        item = ConversationItem(_make_data(unread_count=1))
        qtbot.addWidget(item)
        item.set_selected(True)
        item.set_selected(False)
        assert item._dot.isVisible()

    def test_unread_dot_remains_hidden_for_read_after_select(self, qtbot):
        item = ConversationItem(_make_data(unread_count=0, unread=False))
        qtbot.addWidget(item)
        item.set_selected(True)
        assert not item._dot.isVisible()

    def test_badge_text_preserved_after_select(self, qtbot):
        item = ConversationItem(_make_data(unread_count=10))
        qtbot.addWidget(item)
        item.set_selected(True)
        assert item._badge_label.isVisible()
        assert item._badge_label.text() == "9+"

    def test_badge_hidden_for_low_count_after_select(self, qtbot):
        item = ConversationItem(_make_data(unread_count=1))
        qtbot.addWidget(item)
        item.set_selected(True)
        assert not item._badge_label.isVisible()

    def test_badge_visible_after_select_then_deselect(self, qtbot):
        item = ConversationItem(_make_data(unread_count=10))
        qtbot.addWidget(item)
        item.set_selected(True)
        item.set_selected(False)
        assert item._badge_label.isVisible()
        assert item._badge_label.text() == "9+"
