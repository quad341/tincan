"""Tests: _emoji_to_img_tag QBuffer ReadWrite fix (tincan-orp90) + pixel visibility (tincan-jyhkd).

Coverage:
  §1 Return format — <img> tag vs plain-text fallback
     - returns <img> tag for emoji at a standard point size
     - tag contains data:image/png;base64, URI
     - tag contains vertical-align:middle style
     - fallback: HTML-escaped emoji when all render paths fail

  §2 PNG content — ReadWrite mode captures bytes before close
     - base64 content decodes to non-empty bytes
     - decoded bytes start with PNG magic (\\x89PNG)

  §3 Canvas floor — max(advance+8, point_size*2, 24) minimum
     - tiny point size yields canvas height >= 24 (absolute floor)
     - large point size yields canvas height >= point_size*2

  §4 Cache — same (emoji, point_size) returns same cached string
     - repeated call returns same string object
     - different point size is a separate cache entry

  §5 Pixel visibility — embedded PNG must have at least one non-transparent pixel
     - smiley (U+1F600) PNG has visible pixels (tincan-jyhkd)
     - thumbs-up (U+1F44D) PNG has visible pixels
     - heart (U+2764) PNG has visible pixels
     - <img> tag is never backed by an all-transparent PNG
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

    def test_fallback_when_all_render_paths_fail(self, qapp):
        with patch.object(QImage, "save", return_value=False):
            with patch("tincan_gui.text_render._render_emoji_cairo", return_value=b""):
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


# ---------------------------------------------------------------------------
# §5 Pixel visibility — PNG must contain at least one non-transparent pixel
# ---------------------------------------------------------------------------

def _visible_pixel_count_from_tag(tag: str) -> int:
    """Return count of non-transparent pixels in the PNG embedded in an <img> tag."""
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from PySide6.QtGui import QImage
    prefix = 'src="data:image/png;base64,'
    start = tag.index(prefix) + len(prefix)
    end = tag.index('"', start)
    png_bytes = base64.b64decode(tag[start:end])
    ba = QByteArray(png_bytes)
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.ReadOnly)
    img = QImage()
    img.load(buf, "PNG")
    buf.close()
    return sum(
        1 for y in range(img.height())
        for x in range(img.width())
        if (img.pixel(x, y) >> 24) & 0xFF > 0
    )


class TestPixelVisibility:
    """An <img> tag must never embed an all-transparent PNG (tincan-jyhkd).

    Qt's software rasterizer cannot render COLRv1 glyphs (Noto Color Emoji
    format) — painter.drawText() produces all-transparent QImage pixels.
    The fix must route through Cairo/Pango (COLRv1-capable) or fall back to
    plain text.  This section verifies that every <img> path produces visible
    (non-transparent) pixels.
    """

    @pytest.mark.parametrize("emoji", ["😀", "👍", "❤️"])
    def test_img_tag_png_has_visible_pixels(self, qapp, emoji):
        """<img> tags must embed a PNG with at least one non-transparent pixel."""
        tag = _emoji_to_img_tag(emoji, 16)
        if not tag.startswith("<img"):
            return  # plain-text fallback is acceptable
        visible = _visible_pixel_count_from_tag(tag)
        assert visible > 0, (
            f"emoji {emoji!r}: <img> embeds all-transparent PNG — "
            "Qt COLRv1 render failed and Cairo fallback was not invoked"
        )

    def test_transparent_qt_render_triggers_cairo_fallback(self, qapp):
        """When Qt produces a transparent image, _render_emoji_cairo must be called."""
        from tincan_gui.text_render import _render_emoji_cairo as real_cairo

        calls = []

        def tracking_cairo(emoji, ps):
            calls.append((emoji, ps))
            return real_cairo(emoji, ps)

        _EMOJI_CACHE.clear()
        with patch("tincan_gui.text_render._has_visible_pixels", return_value=False):
            with patch("tincan_gui.text_render._render_emoji_cairo", side_effect=tracking_cairo):
                _emoji_to_img_tag("😀", 16)

        assert len(calls) == 1, (
            "Expected _render_emoji_cairo to be called once when Qt render is transparent"
        )
        assert calls[0] == ("😀", 16)
