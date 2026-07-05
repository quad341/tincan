"""Tests: avatar wiring in ThreadHeader and main._on_contact_photo_received.
Bead: tincan-l70aw (feature: tincan-ipv6d)

Coverage:
  §1 AvatarWidget.update_for_name(name)
     - update_for_name('Bob') → pixmap not null
     - update_for_name('Bob') → accessibleName contains 'Bob'
     - update_for_name('Bob') → accessibleName format: 'Contact photo for Bob'
     - update_for_name after initial name: accessible name reflects new name

  §2 ThreadHeader.set_contact_photo(bytes)
     - set_contact_photo(valid_png) → header._avatar.pixmap() not null
     - set_contact_photo(garbage) → falls back to initials, pixmap not null

  §3 ThreadHeader.update_contact() wires avatar name
     - update_contact("Bob", ...) → header._avatar.accessibleName() contains 'Bob'
     - conversation switch: avatar name updates to new contact name

  §4 main._on_contact_photo_received header wiring
     - conv_id matches _current_phone → thread_view.set_header_photo called
     - conv_id does not match → thread_view.set_header_photo NOT called
     - set_conversation_photo always called when photo is non-empty
     - _same_conv normalisation: "+15550001111" matches "5550001111"
"""
from __future__ import annotations

import struct
import zlib
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QSystemTrayIcon

from tincan_gui.avatar import AvatarWidget
from tincan_gui.main import MainWindow
from tincan_gui.thread_view import ThreadHeader

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_minimal_png() -> bytes:
    """Return a minimal 1×1 white PNG as raw bytes."""
    def _chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    raw_row = b"\x00\xFF\xFF\xFF"
    idat = _chunk(b"IDAT", zlib.compress(raw_row))
    iend = _chunk(b"IEND", b"")
    return b"\x89PNG\r\n\x1a\n" + ihdr + idat + iend


@pytest.fixture(autouse=True)
def _no_tray_show():
    with patch.object(QSystemTrayIcon, "show"):
        yield


def _make_window(qtbot, phone: str = "5550001111") -> MainWindow:
    window = MainWindow()
    qtbot.addWidget(window)
    window._current_phone = phone
    return window


# ---------------------------------------------------------------------------
# §1 AvatarWidget.update_for_name(name)
# ---------------------------------------------------------------------------

class TestAvatarUpdateForName:
    """update_for_name() resets the widget to initials for the new name."""

    def test_pixmap_not_null_after_update_for_name(self, qtbot):
        widget = AvatarWidget("Alice")
        qtbot.addWidget(widget)
        widget.update_for_name("Bob")
        assert not widget.pixmap().isNull()

    def test_accessible_name_contains_new_name(self, qtbot):
        widget = AvatarWidget("Alice")
        qtbot.addWidget(widget)
        widget.update_for_name("Bob")
        assert "Bob" in widget.accessibleName()

    def test_accessible_name_format_after_update(self, qtbot):
        widget = AvatarWidget("Alice")
        qtbot.addWidget(widget)
        widget.update_for_name("Bob")
        assert widget.accessibleName() == "Contact photo for Bob"

    def test_accessible_name_no_longer_contains_old_name(self, qtbot):
        widget = AvatarWidget("Alice")
        qtbot.addWidget(widget)
        widget.update_for_name("Bob")
        assert "Alice" not in widget.accessibleName()

    def test_update_for_name_same_name_is_stable(self, qtbot):
        widget = AvatarWidget("Alice")
        qtbot.addWidget(widget)
        widget.update_for_name("Alice")
        assert widget.accessibleName() == "Contact photo for Alice"
        assert not widget.pixmap().isNull()


# ---------------------------------------------------------------------------
# §2 ThreadHeader.set_contact_photo(bytes)
# ---------------------------------------------------------------------------

class TestThreadHeaderSetContactPhoto:
    """set_contact_photo() delegates to avatar.set_photo() — pixmap updates."""

    def test_valid_png_makes_avatar_pixmap_non_null(self, qtbot):
        header = ThreadHeader()
        qtbot.addWidget(header)
        header.update_contact("Alice", "+15550001111")
        header.set_contact_photo(_make_minimal_png())
        assert not header._avatar.pixmap().isNull()

    def test_garbage_bytes_falls_back_to_initials(self, qtbot):
        header = ThreadHeader()
        qtbot.addWidget(header)
        header.update_contact("Alice", "+15550001111")
        header.set_contact_photo(b"\xde\xad\xbe\xef not an image")
        assert not header._avatar.pixmap().isNull()

    def test_empty_bytes_falls_back_to_initials(self, qtbot):
        header = ThreadHeader()
        qtbot.addWidget(header)
        header.update_contact("Alice", "+15550001111")
        header.set_contact_photo(b"")
        assert not header._avatar.pixmap().isNull()


# ---------------------------------------------------------------------------
# §3 ThreadHeader.update_contact() wires avatar name
# ---------------------------------------------------------------------------

class TestThreadHeaderAvatarNameTracksContact:
    """update_contact() calls avatar.update_for_name so avatar tracks the contact."""

    def test_avatar_accessible_name_set_on_update_contact(self, qtbot):
        header = ThreadHeader()
        qtbot.addWidget(header)
        header.update_contact("Bob", "+15550001111")
        assert "Bob" in header._avatar.accessibleName()

    def test_avatar_accessible_name_updates_on_conversation_switch(self, qtbot):
        header = ThreadHeader()
        qtbot.addWidget(header)
        header.update_contact("Alice", "+15550001111")
        header.update_contact("Bob", "+15550002222")
        assert "Bob" in header._avatar.accessibleName()
        assert "Alice" not in header._avatar.accessibleName()

    def test_avatar_accessible_name_format_after_update_contact(self, qtbot):
        header = ThreadHeader()
        qtbot.addWidget(header)
        header.update_contact("Carol", "+15550003333")
        assert header._avatar.accessibleName() == "Contact photo for Carol"


# ---------------------------------------------------------------------------
# §4 main._on_contact_photo_received header wiring
# ---------------------------------------------------------------------------

class TestOnContactPhotoReceivedHeaderWiring:
    """_on_contact_photo_received calls set_header_photo when conv matches current."""

    def test_matching_conv_calls_set_header_photo(self, qtbot):
        window = _make_window(qtbot, phone="5550001111")
        window._thread_view.set_header_photo = MagicMock()
        window._on_contact_photo_received("5550001111", _make_minimal_png())
        window._thread_view.set_header_photo.assert_called_once()

    def test_different_conv_does_not_call_set_header_photo(self, qtbot):
        window = _make_window(qtbot, phone="5550001111")
        window._thread_view.set_header_photo = MagicMock()
        window._on_contact_photo_received("5550002222", _make_minimal_png())
        window._thread_view.set_header_photo.assert_not_called()

    def test_set_header_photo_called_with_photo_bytes(self, qtbot):
        window = _make_window(qtbot, phone="5550001111")
        window._thread_view.set_header_photo = MagicMock()
        photo = _make_minimal_png()
        window._on_contact_photo_received("5550001111", photo)
        window._thread_view.set_header_photo.assert_called_once_with(photo)

    def test_same_conv_normalisation_plus_prefix(self, qtbot):
        """'+15550001111' and '5550001111' are the same conversation."""
        window = _make_window(qtbot, phone="5550001111")
        window._thread_view.set_header_photo = MagicMock()
        window._on_contact_photo_received("+15550001111", _make_minimal_png())
        window._thread_view.set_header_photo.assert_called_once()

    def test_no_current_phone_does_not_call_set_header_photo(self, qtbot):
        window = _make_window(qtbot, phone="")
        window._thread_view.set_header_photo = MagicMock()
        window._on_contact_photo_received("5550001111", _make_minimal_png())
        window._thread_view.set_header_photo.assert_not_called()

    def test_set_conversation_photo_always_called_when_photo_nonempty(self, qtbot):
        """Existing conv-list behavior preserved regardless of which conv is open."""
        window = _make_window(qtbot, phone="5550001111")
        window._conv_list.set_conversation_photo = MagicMock()
        window._on_contact_photo_received("5550002222", _make_minimal_png())
        window._conv_list.set_conversation_photo.assert_called_once()

    def test_empty_photo_skips_set_header_photo(self, qtbot):
        """Empty photo bytes: guard passes over header update (no-op)."""
        window = _make_window(qtbot, phone="5550001111")
        window._thread_view.set_header_photo = MagicMock()
        window._on_contact_photo_received("5550001111", b"")
        window._thread_view.set_header_photo.assert_not_called()
