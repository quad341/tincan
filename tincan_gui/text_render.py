"""Message body rendering utilities: emoji, URL linkify, word-break."""
from __future__ import annotations

import base64
import html as _html
import re as _re

from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter

_URL_RE = _re.compile(r"(https?://[^\s<>\"']+)")

# Matches emoji codepoints and combining characters as a greedy sequence.
# Including ZWJ (U+200D), VS-16 (U+FE0F), skin tones, and regional indicators
# ensures ZWJ sequences and flag pairs are captured as a single unit.
_EMOJI_RE = _re.compile(
    r"[\U0001F1E0-\U0001F1FF\U0001F300-\U0001FAFF"
    r"☀-➿⌚-⌛⏏⏩-⏳⏸-⏺"
    r"▪-▫▶◀◻-◾☔-☕♈-♓"
    r"♿⚓⚡⚪-⚫⚽-⚾⛄-⛅⛎"
    r"⛔⛪⛲-⛳⛵⛺⛽✂✅✈-✍"
    r"✏✒✔✖✝✡✨✳-✴❄❇"
    r"❌❎❓-❕❗❣-❤➕-➗➡➰"
    r"➿⤴-⤵⬅-⬇⬛-⬜⭐⭕"
    r"️‍\U0001F3FB-\U0001F3FF]+",
    _re.UNICODE,
)

# Cache: (emoji_str, point_size) → HTML img tag (or plain HTML-escaped fallback)
_EMOJI_CACHE: dict[tuple[str, int], str] = {}


def _has_visible_pixels(img: QImage) -> bool:
    """Return True if any pixel in img has alpha > 0."""
    for y in range(img.height()):
        for x in range(img.width()):
            if (img.pixel(x, y) >> 24) & 0xFF > 0:
                return True
    return False


def _render_emoji_cairo(emoji: str, point_size: int) -> bytes:
    """Render emoji to PNG via Cairo + Pango (COLRv1-capable via FreeType 2.11.1+).

    Qt's software rasterizer does not render COLRv1 glyphs to QImage (tincan-jyhkd).
    Cairo+PangoCairo uses FreeType directly and handles COLRv1 natively.
    Returns empty bytes if cairo/gi are unavailable or rendering fails.
    """
    try:
        import io

        import cairo
        import gi
        gi.require_version("Pango", "1.0")
        gi.require_version("PangoCairo", "1.0")
        from gi.repository import Pango, PangoCairo  # type: ignore[import-untyped]

        tmp = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)
        layout = PangoCairo.create_layout(cairo.Context(tmp))
        font_desc = Pango.FontDescription(f"Noto Color Emoji {point_size}")
        layout.set_font_description(font_desc)
        layout.set_text(emoji)
        w_px, h_px = layout.get_pixel_size()

        margin = 4
        w = max(w_px + margin * 2, point_size * 2, 24)
        h = max(h_px + margin * 2, point_size * 2, 24)

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        ctx = cairo.Context(surface)
        ctx.set_source_rgba(0, 0, 0, 0)
        ctx.paint()
        layout = PangoCairo.create_layout(ctx)
        layout.set_font_description(font_desc)
        layout.set_text(emoji)
        PangoCairo.show_layout(ctx, layout)

        buf = io.BytesIO()
        surface.write_to_png(buf)
        return buf.getvalue()
    except Exception:  # noqa: BLE001
        return b""


def _emoji_to_img_tag(emoji: str, point_size: int) -> str:
    """Render emoji to PNG and return an <img> data-URI tag.

    Render path (tincan-jyhkd): Qt's software rasterizer cannot render COLRv1
    glyphs (Noto Color Emoji format) — painter.drawText() produces all-transparent
    pixels.  When that happens, fall back to Cairo+PangoCairo which handles COLRv1
    natively via FreeType.  If neither path yields visible pixels, emit plain
    HTML-escaped text so the Qt HTML renderer can show a monochrome glyph.
    """
    key = (emoji, point_size)
    if key in _EMOJI_CACHE:
        return _EMOJI_CACHE[key]

    font = QFont("Noto Color Emoji")
    font.setPointSize(point_size)
    fm = QFontMetrics(font)

    # Minimum size: 2× point size; measured advance may be zero when font isn't found.
    px = max(point_size * 2, 24)
    w = max(fm.horizontalAdvance(emoji) + 8, px)
    h = max(fm.height() + 8, px)

    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))

    painter = QPainter(img)
    painter.setFont(font)
    painter.drawText(img.rect(), Qt.AlignmentFlag.AlignCenter, emoji)
    painter.end()

    # Open ReadWrite so buf.buffer() is accessible before close (buf.data() after
    # close() returns an empty QByteArray in some PySide6 builds — tincan-orp90).
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.ReadWrite)
    saved = img.save(buf, "PNG")
    png_bytes = bytes(buf.buffer()) if saved and _has_visible_pixels(img) else b""
    buf.close()

    # Qt produced transparent pixels — route through Cairo/Pango (COLRv1-capable).
    if not png_bytes:
        png_bytes = _render_emoji_cairo(emoji, point_size)

    if png_bytes:
        b64 = base64.b64encode(png_bytes).decode("ascii")
        tag = f'<img src="data:image/png;base64,{b64}" style="vertical-align:middle" />'
    else:
        tag = _html.escape(emoji)

    _EMOJI_CACHE[key] = tag
    return tag


_MAX_WORD_LEN = 30  # insert <wbr> after this many consecutive non-space chars


def _break_long_words(html: str) -> str:
    """Insert zero-width spaces every _MAX_WORD_LEN chars outside HTML tags.

    Uses &#8203; (U+200B) rather than <wbr>: Qt's text engine respects the
    Unicode ZW (zero-width space) line-break class in its layout algorithm,
    whereas <wbr> was not reliably lowering the label's minimumSizeHint width.
    """
    out = []
    run = 0
    in_tag = False
    for ch in html:
        if ch == "<":
            in_tag = True
            run = 0
        elif ch == ">":
            in_tag = False
        out.append(ch)
        if not in_tag and ch != ">":
            run = 0 if ch.isspace() else run + 1
            if run == _MAX_WORD_LEN:
                out.append("&#8203;")  # U+200B zero-width space — Qt ZW break class
                run = 0
    return "".join(out)


def render_message_body(text: str, emoji_size: int = 13) -> str:
    """HTML-escape text, wrap URLs in <a> tags, render emoji, and break long words."""
    parts: list[str] = []
    last = 0
    for m in _EMOJI_RE.finditer(text):
        before = text[last:m.start()]
        if before:
            parts.append(
                _break_long_words(_URL_RE.sub(r'<a href="\1">\1</a>', _html.escape(before)))
            )
        parts.append(_emoji_to_img_tag(m.group(), emoji_size))
        last = m.end()
    after = text[last:]
    if after:
        parts.append(
            _break_long_words(_URL_RE.sub(r'<a href="\1">\1</a>', _html.escape(after)))
        )
    return "".join(parts)
