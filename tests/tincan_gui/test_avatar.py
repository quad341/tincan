"""Tests: AvatarWidget — PBAP photo display and accessibility.
Bead: tincan-li9t

Coverage:
  §2 Photo fetch: AvatarWidget updates to photo; accessible name set correctly
     - set_photo(valid_bytes) → pixmap is non-null
     - set_photo(valid_bytes) → accessibleName() == 'Contact photo for [Name]'
     - Initial render shows initials pixmap (not null)
     - Initial accessible name set to 'Contact photo for [Name]'
  §5 Contact with no PHOTO / invalid data
     - set_photo(b'') → falls back to initials (pixmap is non-null, initials)
     - set_photo(invalid_bytes) → falls back to initials
     - Accessible name is preserved after fallback
  §7 After name resolution, accessible name uses real name
     - AvatarWidget("Alice") → accessibleName() contains "Alice"
     - AvatarWidget("Bob") → accessibleName() contains "Bob"
"""
from __future__ import annotations

import struct

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

from tincan_gui.avatar import AvatarWidget, _initials


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_minimal_png() -> bytes:
    """Return a minimal 1×1 white PNG as raw bytes."""
    # PNG magic + IHDR + IDAT + IEND (minimal valid PNG)
    import zlib
    def _chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    raw_row = b"\x00\xFF\xFF\xFF"  # filter byte + RGB
    idat = _chunk(b"IDAT", zlib.compress(raw_row))
    iend = _chunk(b"IEND", b"")
    return b"\x89PNG\r\n\x1a\n" + ihdr + idat + iend


# ---------------------------------------------------------------------------
# §2 Photo display: set_photo with valid data
# ---------------------------------------------------------------------------

class TestSetPhotoValid:
    """set_photo() with valid image bytes updates pixmap and preserves accessible name."""

    def test_set_photo_makes_pixmap_non_null(self, qtbot):
        widget = AvatarWidget("Alice")
        qtbot.addWidget(widget)
        widget.set_photo(_make_minimal_png())
        assert not widget.pixmap().isNull()

    def test_set_photo_accessible_name_contains_name(self, qtbot):
        widget = AvatarWidget("Alice")
        qtbot.addWidget(widget)
        widget.set_photo(_make_minimal_png())
        assert "Alice" in widget.accessibleName()

    def test_set_photo_accessible_name_format(self, qtbot):
        widget = AvatarWidget("Alice")
        qtbot.addWidget(widget)
        widget.set_photo(_make_minimal_png())
        assert widget.accessibleName() == "Contact photo for Alice"

    def test_set_photo_accessible_name_uses_constructor_name(self, qtbot):
        widget = AvatarWidget("Bob Smith")
        qtbot.addWidget(widget)
        widget.set_photo(_make_minimal_png())
        assert widget.accessibleName() == "Contact photo for Bob Smith"


# ---------------------------------------------------------------------------
# §2 Initial state: initials pixmap + accessible name
# ---------------------------------------------------------------------------

class TestInitialState:
    """AvatarWidget starts with initials pixmap and accessible name set."""

    def test_initial_pixmap_is_not_null(self, qtbot):
        widget = AvatarWidget("Alice")
        qtbot.addWidget(widget)
        assert not widget.pixmap().isNull()

    def test_initial_accessible_name_contains_name(self, qtbot):
        widget = AvatarWidget("Alice")
        qtbot.addWidget(widget)
        assert "Alice" in widget.accessibleName()

    def test_initial_accessible_name_format(self, qtbot):
        widget = AvatarWidget("Carol Doe")
        qtbot.addWidget(widget)
        assert widget.accessibleName() == "Contact photo for Carol Doe"

    def test_size_is_40x40(self, qtbot):
        widget = AvatarWidget("Alice")
        qtbot.addWidget(widget)
        assert widget.width() == 40
        assert widget.height() == 40


# ---------------------------------------------------------------------------
# §5 set_photo with invalid / empty data — fallback to initials
# ---------------------------------------------------------------------------

class TestSetPhotoFallback:
    """set_photo() with bad data falls back to initials; accessible name preserved."""

    def test_set_photo_empty_bytes_falls_back(self, qtbot):
        widget = AvatarWidget("Alice")
        qtbot.addWidget(widget)
        widget.set_photo(b"")
        # Fallback to initials → pixmap still non-null (initials drawn)
        assert not widget.pixmap().isNull()

    def test_set_photo_garbage_falls_back(self, qtbot):
        widget = AvatarWidget("Alice")
        qtbot.addWidget(widget)
        widget.set_photo(b"\xde\xad\xbe\xef garbage not an image")
        assert not widget.pixmap().isNull()

    def test_set_photo_fallback_accessible_name_preserved(self, qtbot):
        widget = AvatarWidget("Alice")
        qtbot.addWidget(widget)
        widget.set_photo(b"garbage")
        assert widget.accessibleName() == "Contact photo for Alice"


# ---------------------------------------------------------------------------
# §7 Accessible name uses real resolved name
# ---------------------------------------------------------------------------

class TestAccessibleNameWithResolvedName:
    """After name resolution, AvatarWidget accessible name uses the real contact name."""

    def test_accessible_name_contains_alice(self, qtbot):
        widget = AvatarWidget("Alice")
        qtbot.addWidget(widget)
        assert "Alice" in widget.accessibleName()

    def test_accessible_name_contains_bob(self, qtbot):
        widget = AvatarWidget("Bob")
        qtbot.addWidget(widget)
        assert "Bob" in widget.accessibleName()

    def test_accessible_name_does_not_contain_phone_number(self, qtbot):
        # When name is resolved, the phone number should not appear in accessible name.
        widget = AvatarWidget("Alice Johnson")
        qtbot.addWidget(widget)
        assert "555" not in widget.accessibleName()


# ---------------------------------------------------------------------------
# _initials helper — unit tests (no Qt needed)
# ---------------------------------------------------------------------------

class TestInitialsHelper:
    """_initials() extracts first+last initial or first two chars."""

    def test_two_word_name_gives_two_initials(self):
        assert _initials("Alice Johnson") == "AJ"

    def test_three_word_name_uses_first_and_last(self):
        assert _initials("Alice Marie Johnson") == "AJ"

    def test_single_word_gives_first_two_chars(self):
        assert _initials("Alice") == "AL"

    def test_single_char_name(self):
        assert _initials("A") == "A"

    def test_empty_name_gives_question_mark(self):
        assert _initials("") == "?"

    def test_lowercase_names_uppercased(self):
        assert _initials("alice johnson") == "AJ"
