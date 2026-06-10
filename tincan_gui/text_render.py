"""Message body rendering: emoji, URL linkify, word-break, font helpers."""
from __future__ import annotations

import base64
import html as _html
import re as _re

from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QColor, QFont, QFontInfo, QFontMetrics, QImage, QPainter
from PySide6.QtWidgets import QApplication

_URL_RE = _re.compile(r"(https?://[^\s<>\"']+)")
# Bare-domain URLs: www.* (with optional path) or any domain/path with a known TLD.
# Path component required for non-www to avoid false positives on e.g. "version 1.0".
_BARE_URL_RE = _re.compile(
    r"\b(www\.[a-zA-Z0-9][a-zA-Z0-9\-.]*[a-zA-Z0-9](?:/[^\s<>\"']*)?)"
    r"|\b((?:[a-zA-Z0-9][a-zA-Z0-9\-]*\.)+(?:com|net|org|io|co|app|dev|gov|edu|info|me|tv)"
    r"/[^\s<>\"']*)"
)

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


def _emoji_font_families() -> list[str]:
    """Return font family list: app default first, color-emoji fonts as fallback.

    "system-ui" is a CSS generic name that Qt does not recognise on Linux —
    passing it as the primary family caused Qt to fall through to Noto Color
    Emoji, changing the look of all message text (tincan-h9nu).  Instead, we
    read the actual application default family at runtime and prepend it so
    only genuine emoji glyphs use the colour-emoji fallback fonts.

    QFontInfo.family() is used rather than QFont.family() because on some
    systems (e.g. Qt6 on GNOME/KDE with a system-configured sans-serif),
    QFont.family() returns "" while QFontInfo returns the resolved name.
    Without the resolved name, the emoji font becomes the primary family and
    plain-text characters (including digits) may not render (tincan-15xl9).
    """
    app = QApplication.instance()
    primary = ""
    if app is not None:
        primary = QFontInfo(app.font()).family()
    families = []
    if primary:
        families.append(primary)
    families.extend([
        "Noto Color Emoji",   # Linux (fonts-noto-color-emoji)
        "Segoe UI Emoji",     # Windows 8.1+
        "Apple Color Emoji",  # macOS / iOS
    ])
    return families


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


def _linkify_segment(raw: str) -> str:
    """HTML-escape *raw* text and wrap all URLs (protocol or bare domain) in <a> tags."""
    matches: list[tuple[int, int, str, str]] = []  # (start, end, href, display)
    for m in _URL_RE.finditer(raw):
        matches.append((m.start(), m.end(), m.group(1), m.group(1)))
    for m in _BARE_URL_RE.finditer(raw):
        display = m.group(1) or m.group(2)
        matches.append((m.start(), m.end(), "https://" + display, display))
    matches.sort(key=lambda t: t[0])

    parts: list[str] = []
    last = 0
    for start, end, href, display in matches:
        if start < last:  # overlapping — skip (already covered by a prior match)
            continue
        parts.append(_html.escape(raw[last:start]))
        parts.append(f'<a href="{_html.escape(href)}">{_html.escape(display)}</a>')
        last = end
    parts.append(_html.escape(raw[last:]))
    return "".join(parts)


def _linkify(text: str, emoji_size: int = 13) -> str:
    """HTML-escape text, wrap URLs in <a> tags, render emoji, and break long words."""
    parts: list[str] = []
    last = 0
    for m in _EMOJI_RE.finditer(text):
        before = text[last:m.start()]
        if before:
            parts.append(_break_long_words(_linkify_segment(before)))
        parts.append(_emoji_to_img_tag(m.group(), emoji_size))
        last = m.end()
    after = text[last:]
    if after:
        parts.append(_break_long_words(_linkify_segment(after)))
    return "".join(parts)


def _linkify_preview(text: str, emoji_size: int = 11) -> str:
    """HTML-escape text and render emoji as inline images; no URL tags, no word-break insertion."""
    parts: list[str] = []
    last = 0
    for m in _EMOJI_RE.finditer(text):
        before = text[last:m.start()]
        if before:
            parts.append(_html.escape(before))
        parts.append(_emoji_to_img_tag(m.group(), emoji_size))
        last = m.end()
    after = text[last:]
    if after:
        parts.append(_html.escape(after))
    return "".join(parts)


_HIGHLIGHT_START = '<span style="background:#fef08a; color:#1f2937">'
_HIGHLIGHT_END = '</span>'


def _linkify_with_highlight(text: str, term: str, emoji_size: int = 13) -> str:
    """Like _linkify but wraps case-insensitive occurrences of *term* in a highlight span."""
    if not term:
        return _linkify(text, emoji_size)
    segments = _re.split(f'({_re.escape(term)})', text, flags=_re.IGNORECASE)
    out = []
    for i, seg in enumerate(segments):
        if i % 2 == 1:  # matched segment
            out.append(_HIGHLIGHT_START + _linkify(seg, emoji_size) + _HIGHLIGHT_END)
        else:
            out.append(_linkify(seg, emoji_size))
    return "".join(out)
