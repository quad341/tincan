"""
Tests for ConversationListWidget search/filter and AvatarWidget set_photo.
Bead: tincan-uvc.

Written BEFORE integration with the builder (TDD). Tests import from tincan_gui
and will pass once the builder's branch is merged.

Coverage map
============
ConversationListWidget._on_filter_changed (tincan_gui/conversation_list.py)
  - Items whose name/preview matches the query prefix are visible.
  - Items that do not match are hidden.
  - Filter is case-insensitive.
  - No-results label shown when no items match a non-empty query.
  - No-results label hidden when filter is cleared.
  - Clearing the filter restores all items.

_SearchLineEdit.keyPressEvent (tincan_gui/conversation_list.py)
  - Escape clears the text field.
  - Escape on an already-empty field is a no-op.
  - Non-Escape keys still produce text.
  - Escape inside a ConversationListWidget clears the filter via the search field.

AvatarWidget.set_photo (tincan_gui/avatar.py)
  - Valid JPEG/PNG bytes → pixmap is non-null.
  - Valid bytes → pixmap differs from the initial initials pixmap.
  - Empty bytes → falls back to initials pixmap.
  - Corrupt bytes → falls back to initials pixmap.
  - Corrupt-then-valid sequence shows the photo, not initials.

_make_photo_pixmap (tincan_gui/avatar.py)
  - Valid bytes → returns non-null QPixmap at the requested size.
  - Empty bytes → returns null QPixmap.
  - Corrupt bytes → returns null QPixmap.
"""
from __future__ import annotations

import struct
import zlib

import pytest
from PySide6.QtCore import Qt

from tincan_gui.avatar import AvatarWidget, _make_photo_pixmap
from tincan_gui.conversation_list import (
    ConversationData,
    ConversationListWidget,
    _SearchLineEdit,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_1x1_png() -> bytes:
    """Return bytes for a valid 1×1 white RGB PNG (minimal but standards-compliant)."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)  # 1×1, 8-bit, RGB
    raw_scanline = b"\x00\xff\xff\xff"  # filter=None, R=255, G=255, B=255
    idat_data = zlib.compress(raw_scanline)
    return sig + chunk(b"IHDR", ihdr_data) + chunk(b"IDAT", idat_data) + chunk(b"IEND", b"")


def _conversations() -> list[ConversationData]:
    return [
        ConversationData(
            id="c1", name="Alice Smith", phone="+1 555-0101",
            preview="Hey there", timestamp="10:00",
        ),
        ConversationData(
            id="c2", name="Bob Jones", phone="+1 555-0102",
            preview="What's up", timestamp="10:01",
        ),
        ConversationData(
            id="c3", name="Carol Brown", phone="+1 555-0103",
            preview="See you soon", timestamp="10:02",
        ),
    ]


# ---------------------------------------------------------------------------
# ConversationListWidget filter — visibility
# ---------------------------------------------------------------------------

class TestConversationListFilterVisibility:
    """_on_filter_changed: items matching the query are visible; others are hidden."""

    def test_matching_item_is_visible(self, qtbot):
        w = ConversationListWidget()
        qtbot.addWidget(w)
        w.load_conversations(_conversations())
        w._search.setText("Ali")
        assert w._items[0].isVisible()  # Alice matches

    def test_non_matching_items_are_hidden(self, qtbot):
        w = ConversationListWidget()
        qtbot.addWidget(w)
        w.load_conversations(_conversations())
        w._search.setText("Ali")
        assert not w._items[1].isVisible()  # Bob
        assert not w._items[2].isVisible()  # Carol

    def test_filter_is_case_insensitive(self, qtbot):
        w = ConversationListWidget()
        qtbot.addWidget(w)
        w.load_conversations(_conversations())
        w._search.setText("ALICE")
        assert w._items[0].isVisible()

    def test_filter_matches_on_preview_text(self, qtbot):
        w = ConversationListWidget()
        qtbot.addWidget(w)
        w.load_conversations(_conversations())
        w._search.setText("see you")
        assert w._items[2].isVisible()  # Carol's preview contains "see you soon"

    def test_filter_on_preview_hides_non_matching_items(self, qtbot):
        w = ConversationListWidget()
        qtbot.addWidget(w)
        w.load_conversations(_conversations())
        w._search.setText("see you")
        assert not w._items[0].isVisible()
        assert not w._items[1].isVisible()

    def test_empty_filter_shows_all_items(self, qtbot):
        w = ConversationListWidget()
        qtbot.addWidget(w)
        w.load_conversations(_conversations())
        w._search.setText("Ali")
        w._search.setText("")
        for item in w._items:
            assert item.isVisible()

    def test_all_items_visible_before_any_filter_applied(self, qtbot):
        w = ConversationListWidget()
        qtbot.addWidget(w)
        w.load_conversations(_conversations())
        for item in w._items:
            assert item.isVisible()


# ---------------------------------------------------------------------------
# ConversationListWidget filter — no-results label
# ---------------------------------------------------------------------------

class TestConversationListNoResultsLabel:
    """_on_filter_changed: no-results label tracks whether any item matches."""

    def test_no_results_label_shown_when_filter_has_no_matches(self, qtbot):
        w = ConversationListWidget()
        qtbot.addWidget(w)
        w.load_conversations(_conversations())
        w._search.setText("zzznomatch")
        assert w._no_results.isVisible()

    def test_no_results_label_hidden_when_filter_cleared(self, qtbot):
        w = ConversationListWidget()
        qtbot.addWidget(w)
        w.load_conversations(_conversations())
        w._search.setText("zzznomatch")
        w._search.setText("")
        assert not w._no_results.isVisible()

    def test_no_results_label_hidden_initially(self, qtbot):
        w = ConversationListWidget()
        qtbot.addWidget(w)
        w.load_conversations(_conversations())
        assert not w._no_results.isVisible()

    def test_no_results_label_hidden_when_some_items_match(self, qtbot):
        w = ConversationListWidget()
        qtbot.addWidget(w)
        w.load_conversations(_conversations())
        w._search.setText("Ali")  # Alice matches
        assert not w._no_results.isVisible()


# ---------------------------------------------------------------------------
# _SearchLineEdit — Escape key
# ---------------------------------------------------------------------------

class TestSearchLineEditEscape:
    """_SearchLineEdit.keyPressEvent: Escape clears the field; other keys pass through."""

    def test_escape_clears_text(self, qtbot):
        edit = _SearchLineEdit()
        qtbot.addWidget(edit)
        edit.setText("hello")
        qtbot.keyClick(edit, Qt.Key.Key_Escape)
        assert edit.text() == ""

    def test_escape_on_empty_input_stays_empty(self, qtbot):
        edit = _SearchLineEdit()
        qtbot.addWidget(edit)
        qtbot.keyClick(edit, Qt.Key.Key_Escape)
        assert edit.text() == ""

    def test_regular_keys_produce_text(self, qtbot):
        edit = _SearchLineEdit()
        qtbot.addWidget(edit)
        qtbot.keyClicks(edit, "abc")
        assert edit.text() == "abc"

    def test_escape_in_conversation_list_clears_filter(self, qtbot):
        w = ConversationListWidget()
        qtbot.addWidget(w)
        w.load_conversations(_conversations())
        w._search.setText("Ali")
        qtbot.keyClick(w._search, Qt.Key.Key_Escape)
        assert w._search.text() == ""


# ---------------------------------------------------------------------------
# AvatarWidget.set_photo
# ---------------------------------------------------------------------------

class TestAvatarSetPhoto:
    """set_photo: valid bytes → photo shown; corrupt/empty → initials fallback."""

    def test_set_photo_valid_png_pixmap_is_not_null(self, qtbot):
        avatar = AvatarWidget("Alice")
        qtbot.addWidget(avatar)
        avatar.set_photo(_make_1x1_png())
        assert not avatar.pixmap().isNull()

    def test_set_photo_valid_png_changes_pixmap(self, qtbot):
        avatar = AvatarWidget("Alice")
        qtbot.addWidget(avatar)
        initials_image = avatar.pixmap().toImage()
        avatar.set_photo(_make_1x1_png())
        assert avatar.pixmap().toImage() != initials_image

    def test_set_photo_empty_bytes_falls_back_to_initials(self, qtbot):
        avatar = AvatarWidget("Bob")
        qtbot.addWidget(avatar)
        expected = avatar.pixmap().toImage()
        avatar.set_photo(b"")
        assert avatar.pixmap().toImage() == expected

    def test_set_photo_corrupt_bytes_falls_back_to_initials(self, qtbot):
        avatar = AvatarWidget("Carol")
        qtbot.addWidget(avatar)
        expected = avatar.pixmap().toImage()
        avatar.set_photo(b"not an image \x00\x01\x02\xff")
        assert avatar.pixmap().toImage() == expected

    def test_set_photo_corrupt_then_valid_shows_photo(self, qtbot):
        avatar = AvatarWidget("Dave")
        qtbot.addWidget(avatar)
        initials_image = avatar.pixmap().toImage()
        avatar.set_photo(b"garbage")         # falls back to initials
        avatar.set_photo(_make_1x1_png())    # now shows photo
        assert avatar.pixmap().toImage() != initials_image


# ---------------------------------------------------------------------------
# _make_photo_pixmap — DestinationIn circle-clip
# ---------------------------------------------------------------------------

class TestMakePhotoPixmap:
    """_make_photo_pixmap: DestinationIn clip returns correct non-null QPixmap."""

    def test_valid_bytes_returns_non_null(self, qtbot):
        px = _make_photo_pixmap(_make_1x1_png(), 40)
        assert not px.isNull()

    def test_result_has_requested_size(self, qtbot):
        px = _make_photo_pixmap(_make_1x1_png(), 40)
        assert px.width() == 40
        assert px.height() == 40

    def test_custom_size_is_honored(self, qtbot):
        px = _make_photo_pixmap(_make_1x1_png(), 24)
        assert px.width() == 24
        assert px.height() == 24

    def test_empty_bytes_returns_null(self, qtbot):
        px = _make_photo_pixmap(b"", 40)
        assert px.isNull()

    def test_corrupt_bytes_returns_null(self, qtbot):
        px = _make_photo_pixmap(b"not an image", 40)
        assert px.isNull()
