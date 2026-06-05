"""Tests: _emoji_to_img_tag QBuffer ReadWrite fix (tincan-orp90).

Coverage:
  §1 Return format — <img> tag vs plain-text fallback
     - returns <img> tag for emoji at a standard point size
     - tag contains data:image/png;base64, URI
     - tag contains vertical-align:middle style
     - fallback: HTML-escaped emoji when img.save fails

  §2 PNG content — ReadWrite mode captures bytes before close
     - base64 content decodes to non-empty bytes
     - decoded bytes start with PNG magic (\\x89PNG)

  §3 Canvas floor — max(advance+8, point_size*2, 24) minimum
     - tiny point size yields canvas height >= 24 (absolute floor)
     - large point size yields canvas height >= point_size*2

  §4 Cache — same (emoji, point_size) returns same cached string
     - repeated call returns same string object
     - different point size is a separate cache entry
"""
from __future__ import annotations

import base64
import struct
from unittest.mock import patch

import pytest
from PySide6.QtGui import QImage
from tincan_gui.thread_view import _EMOJI_CACHE, _emoji_to_img_tag


@pytest.fixture(autouse=True)
def _clear_emoji_cache():
    _EMOJI_CACHE.clear()
    yield
    _EMOJI_CACHE.clear()


def _decode_b64_from_tag(tag: str) -> bytes:
    """Extract and decode the base64 PNG from an <img> data URI tag."""
    prefix = 'src="data:image/png;base64,'
    start = tag.index(prefix) + len(prefix)
    end = tag.index('"', start)
    return base64.b64decode(tag[start:end])


def _png_dimensions(png_bytes: bytes) -> tuple[int, int]:
    """Return (width, height) from a PNG IHDR chunk."""
    w = struct.unpack(">I", png_bytes[16:20])[0]
    h = struct.unpack(">I", png_bytes[20:24])[0]
    return w, h


# ---------------------------------------------------------------------------
# §1 Return format
# ---------------------------------------------------------------------------

class TestReturnFormat:
    """_emoji_to_img_tag must produce an <img> tag when PNG save succeeds."""

    def test_returns_img_tag_for_emoji(self, qapp):
        result = _emoji_to_img_tag("😀", 16)
        assert result.startswith("<img "), f"expected <img> tag, got: {result!r}"

    def test_img_tag_contains_png_base64_uri(self, qapp):
        result = _emoji_to_img_tag("😀", 16)
        assert "data:image/png;base64," in result

    def test_img_tag_has_vertical_align_style(self, qapp):
        result = _emoji_to_img_tag("😀", 16)
        assert "vertical-align:middle" in result

    def test_fallback_when_save_fails(self, qapp):
        with patch.object(QImage, "save", return_value=False):
            result = _emoji_to_img_tag("🎉", 16)
        assert "<img" not in result
        assert "🎉" in result


# ---------------------------------------------------------------------------
# §2 PNG content — ReadWrite mode ensures bytes captured before close
# ---------------------------------------------------------------------------

class TestPngContent:
    """Decoded bytes must be a valid PNG — confirms ReadWrite fix is in effect."""

    def test_base64_decodes_to_non_empty_bytes(self, qapp):
        tag = _emoji_to_img_tag("😀", 16)
        png_bytes = _decode_b64_from_tag(tag)
        assert len(png_bytes) > 0

    def test_decoded_bytes_start_with_png_magic(self, qapp):
        tag = _emoji_to_img_tag("😀", 16)
        png_bytes = _decode_b64_from_tag(tag)
        assert png_bytes[:4] == b"\x89PNG"


# ---------------------------------------------------------------------------
# §3 Canvas floor
# ---------------------------------------------------------------------------

class TestCanvasFloor:
    """Canvas must be at least max(advance+8, point_size*2, 24) on each axis."""

    def test_canvas_height_at_least_24_for_tiny_point_size(self, qapp):
        tag = _emoji_to_img_tag("✔", 2)
        png_bytes = _decode_b64_from_tag(tag)
        _, h = _png_dimensions(png_bytes)
        assert h >= 24, f"height {h} < 24 at point_size=2"

    def test_canvas_height_at_least_point_size_times_two_for_large(self, qapp):
        ps = 20
        tag = _emoji_to_img_tag("✔", ps)
        png_bytes = _decode_b64_from_tag(tag)
        _, h = _png_dimensions(png_bytes)
        assert h >= ps * 2, f"height {h} < {ps * 2} at point_size={ps}"

    def test_canvas_width_at_least_24_for_tiny_point_size(self, qapp):
        tag = _emoji_to_img_tag("✔", 2)
        png_bytes = _decode_b64_from_tag(tag)
        w, _ = _png_dimensions(png_bytes)
        assert w >= 24, f"width {w} < 24 at point_size=2"


# ---------------------------------------------------------------------------
# §4 Cache
# ---------------------------------------------------------------------------

class TestCache:
    """_EMOJI_CACHE must return the same string for repeated (emoji, point_size) calls."""

    def test_same_args_returns_same_string_object(self, qapp):
        r1 = _emoji_to_img_tag("😀", 16)
        r2 = _emoji_to_img_tag("😀", 16)
        assert r1 is r2

    def test_different_point_size_is_separate_entry(self, qapp):
        r12 = _emoji_to_img_tag("😀", 12)
        r24 = _emoji_to_img_tag("😀", 24)
        assert r12 != r24
