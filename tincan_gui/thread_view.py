"""Thread view: ThreadHeader, MessageBubble (4 types), ThreadView."""
from __future__ import annotations

import base64
import datetime
import html as _html
import re as _re
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QAccessible, QColor, QFont, QFontMetrics, QImage, QPainter
from PySide6.QtWidgets import (
    QAccessibleWidget,
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from tincan_gui.avatar import _color_for_name
from tincan_gui.theme import is_dark_theme

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


def _emoji_font_families() -> list[str]:
    """Return font family list: app default first, color-emoji fonts as fallback.

    "system-ui" is a CSS generic name that Qt does not recognise on Linux —
    passing it as the primary family caused Qt to fall through to Noto Color
    Emoji, changing the look of all message text (tincan-h9nu).  Instead, we
    read the actual application default family at runtime and prepend it so
    only genuine emoji glyphs use the colour-emoji fallback fonts.
    """
    app = QApplication.instance()
    primary = app.font().family() if app is not None else ""
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
    """Insert <wbr> hints every _MAX_WORD_LEN chars outside HTML tags (tincan-5hcyf)."""
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
                out.append("<wbr>")
                run = 0
    return "".join(out)


def _linkify(text: str, emoji_size: int = 13) -> str:
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


def _get_today() -> datetime.date:
    """Return today's date. Isolated for test patching."""
    return datetime.date.today()


def _date_label_text(sort_key: str, today: datetime.date | None = None) -> str:
    """Convert a sort_key (YYYYMMDDTHHMMSS) to a human-readable date label.

    Returns "Today", "Yesterday", or abbreviated date (e.g. "Thu Jun  5").
    Returns "" for empty or malformed sort_key.
    """
    if not sort_key or len(sort_key) < 8:
        return ""
    try:
        msg_date = datetime.date(
            int(sort_key[:4]), int(sort_key[4:6]), int(sort_key[6:8])
        )
    except ValueError:
        return ""
    ref = today if today is not None else _get_today()
    if msg_date == ref:
        return "Today"
    if msg_date == ref - datetime.timedelta(days=1):
        return "Yesterday"
    return msg_date.strftime("%a %b %e").strip()


def _date_label_for_sort_key(sort_key: str, today: "datetime.date | None" = None) -> "str | None":
    """Return 'Today', 'Yesterday', or abbreviated date for a sort_key's date.

    Returns None for empty or malformed sort_key so callers can skip separators cleanly.
    """
    label = _date_label_text(sort_key, today=today)
    return label if label else None


class DateSeparatorWidget(QWidget):
    """Full-width centered date separator row between message bubbles."""

    _is_date_separator = True  # marker for test detection

    def __init__(self, text: str, parent: "Optional[QWidget]" = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)
        self._label = QLabel(text)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("color: #888; font-size: 11px;")
        self._label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        left_line = QFrame()
        left_line.setFrameShape(QFrame.Shape.HLine)
        left_line.setStyleSheet("color: #ddd;")
        right_line = QFrame()
        right_line.setFrameShape(QFrame.Shape.HLine)
        right_line.setStyleSheet("color: #ddd;")
        layout.addWidget(left_line, stretch=1)
        layout.addWidget(self._label)
        layout.addWidget(right_line, stretch=1)
        self.setAccessibleName(text)

    def label_text(self) -> str:
        """Return the date label text (e.g. 'Today', 'Yesterday', 'Jun 2')."""
        return self._label.text()

    def text(self) -> str:
        """Alias for label_text() — satisfies duck-typing in tests."""
        return self._label.text()


class BubbleType(Enum):
    INBOUND = auto()
    OUTBOUND = auto()
    BODY_UNAVAILABLE = auto()
    GROUP_UNKNOWN_SENDER = auto()


@dataclass
class MessageData:
    bubble_type: BubbleType
    body: str
    sender: str
    timestamp: str
    show_attribution: bool = False  # show sender name above inbound bubble in group mode
    sort_key: str = ""  # full YYYYMMDDTHHMMSS for date+second ordering (tincan-93fha)


class MessageBubble(QWidget):
    """Single message bubble — 4 visual types per design spec."""

    _STYLES = {
        BubbleType.INBOUND: {
            "bg": "#f3f4f6", "bg_dark": "#3f3f46",
            "fg": "#111827", "fg_dark": "#f4f4f5",
            "align": Qt.AlignLeft,
            "margin_left": 20,
            "margin_right": 80,
        },
        BubbleType.OUTBOUND: {
            "bg": "#0d9488", "bg_dark": "#0d9488",
            "fg": "#ffffff", "fg_dark": "#ffffff",
            "align": Qt.AlignRight,
            "margin_left": 80,
            "margin_right": 20,
        },
        BubbleType.BODY_UNAVAILABLE: {
            "bg": "#fef9c3", "bg_dark": "#3f3f46",
            "fg": "#92400e", "fg_dark": "#fbbf24",
            "align": Qt.AlignLeft,
            "margin_left": 20,
            "margin_right": 80,
        },
        BubbleType.GROUP_UNKNOWN_SENDER: {
            "bg": "#f3f4f6", "bg_dark": "#3f3f46",
            "fg": "#111827", "fg_dark": "#f4f4f5",
            "align": Qt.AlignLeft,
            "margin_left": 20,
            "margin_right": 80,
        },
    }

    def __init__(self, data: MessageData, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._data = data
        self._bubble_widget: Optional[QWidget] = None
        self._build()
        self._update_accessible()

    def _build(self) -> None:
        style = self._STYLES[self._data.bubble_type]
        dark = is_dark_theme()
        bg = style["bg_dark"] if dark else style["bg"]
        fg = style["fg_dark"] if dark else style["fg"]

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 4, 0, 4)

        if style["align"] == Qt.AlignRight:
            outer.addStretch()

        # Sender attribution label above inbound bubble in group mode
        col = QVBoxLayout()
        col.setSpacing(0)
        if self._data.show_attribution and self._data.sender:
            attr_label = QLabel(self._data.sender)
            attr_font = QFont()
            attr_font.setPointSize(10)
            attr_font.setBold(True)
            attr_label.setFont(attr_font)
            color = _color_for_name(self._data.sender)
            attr_label.setStyleSheet(f"color: {color};")
            attr_label.setContentsMargins(style["margin_left"] + 12, 0, 0, 4)
            col.addWidget(attr_label)

        bubble = QWidget()
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(12, 8, 12, 8)
        bubble_layout.setSpacing(4)

        # Group unknown sender warning sub-label
        if self._data.bubble_type == BubbleType.GROUP_UNKNOWN_SENDER:
            warn = QLabel("⚠ sender unknown (group text attribution)")
            warn_font = QFont()
            warn_font.setPointSize(11)
            warn.setFont(warn_font)
            warn.setStyleSheet("color: #fbbf24;" if dark else "color: #92400e;")
            warn.setWordWrap(True)
            bubble_layout.addWidget(warn)

        # Body unavailable uses canonical plain-language strings (tincan-063z)
        body_label = QLabel()
        body_font = QFont()
        body_font.setFamilies(_emoji_font_families())
        body_font.setPointSize(13)
        body_label.setFont(body_font)
        body_label.setWordWrap(True)
        body_label.setStyleSheet(f"color: {fg};")
        if self._data.bubble_type == BubbleType.BODY_UNAVAILABLE:
            body_label.setText("⚠ Message content unavailable")
        else:
            body_label.setTextFormat(Qt.TextFormat.RichText)
            body_label.setOpenExternalLinks(True)
            body_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextBrowserInteraction
            )
            body_label.setCursor(Qt.CursorShape.IBeamCursor)
            body_label.setText(_linkify(self._data.body))
        self._body_label = body_label
        bubble_layout.addWidget(body_label)

        if self._data.bubble_type == BubbleType.BODY_UNAVAILABLE:
            sub = QLabel("Message body not available from phone")
            sub_font = QFont()
            sub_font.setPointSize(11)
            sub.setFont(sub_font)
            sub.setStyleSheet("color: #fbbf24;" if dark else "color: #92400e;")
            sub.setWordWrap(True)
            bubble_layout.addWidget(sub)

        # Meta label (sender · time or time · Sent ✓)
        if self._data.bubble_type == BubbleType.OUTBOUND:
            meta_text = f"{self._data.timestamp} · Sent ✓"
            meta_align = Qt.AlignRight
        else:
            meta_text = f"{self._data.sender} · {self._data.timestamp}"
            meta_align = Qt.AlignLeft

        meta = QLabel(meta_text)
        meta_font = QFont()
        meta_font.setPointSize(10)
        meta.setFont(meta_font)
        self._meta_color = "#a1a1aa" if dark else "#6b7280"
        meta.setStyleSheet(f"color: {self._meta_color};")
        meta.setAlignment(meta_align)
        bubble_layout.addWidget(meta)
        self._meta_label = meta

        bubble.setStyleSheet(
            f"background-color: {bg}; border-radius: 12px;"
        )

        ml = style["margin_left"]
        mr = style["margin_right"]
        outer.setContentsMargins(ml, 0, mr, 0)
        self._bubble_widget = bubble
        col.addWidget(bubble)
        outer.addLayout(col)

        if style["align"] == Qt.AlignLeft:
            outer.addStretch()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._bubble_widget and self.width() > 0:
            self._bubble_widget.setMaximumWidth(int(self.width() * 0.72))

    def set_send_failed(self) -> None:
        """Update the meta label to reflect a failed send (outbound bubbles only)."""
        self._meta_label.setText(f"{self._data.timestamp} · ⚠ Failed")

    def set_send_delivered(self) -> None:
        """Update the meta label to show confirmed delivery (outbound bubbles only)."""
        self._meta_label.setText(f"{self._data.timestamp} · Delivered ✓")

    def metadata_label_color(self) -> str:
        """Return the hex color applied to the metadata label (used by a11y tests)."""
        return self._meta_color

    def _update_accessible(self) -> None:
        btype = self._data.bubble_type
        if btype == BubbleType.OUTBOUND:
            self.setAccessibleName(
                self.tr("Outbound: {body} — sent at {time}").format(
                    body=self._data.body, time=self._data.timestamp
                )
            )
        elif btype == BubbleType.BODY_UNAVAILABLE:
            self.setAccessibleName(
                self.tr("Inbound: content unavailable — from {sender} at {time}").format(
                    sender=self._data.sender, time=self._data.timestamp
                )
            )
        elif btype == BubbleType.GROUP_UNKNOWN_SENDER:
            self.setAccessibleName(
                self.tr("Inbound: {body} — from {sender} at {time}").format(
                    body=self._data.body, sender=self._data.sender, time=self._data.timestamp
                )
            )
        else:  # INBOUND
            self.setAccessibleName(
                self.tr("Inbound: {body} — from {sender} at {time}").format(
                    body=self._data.body, sender=self._data.sender, time=self._data.timestamp
                )
            )


# ---------------------------------------------------------------------------
# Accessible role factory — MessageBubble → StaticText
# ---------------------------------------------------------------------------

def _thread_view_factory(classname: str, obj) -> Optional[QAccessibleWidget]:
    if isinstance(obj, MessageBubble):
        return QAccessibleWidget(obj, QAccessible.Role.StaticText)
    return None


QAccessible.installFactory(_thread_view_factory)


class ThreadHeader(QWidget):
    """Thread header bar (h=56): contact name + phone + type badge."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(56)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        if is_dark_theme():
            self.setStyleSheet("background: #27272a; border-bottom: 1px solid #3f3f46;")
        else:
            self.setStyleSheet("background: #ffffff; border-bottom: 1px solid #e5e7eb;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(2)

        _dark = is_dark_theme()
        self._name_label = QLabel("")
        name_font = QFont()
        name_font.setPointSize(18)
        self._name_label.setFont(name_font)
        self._name_label.setStyleSheet(
            "color: #f4f4f5;" if _dark else "color: #111827;"
        )
        layout.addWidget(self._name_label)

        self._phone_label = QLabel("")
        phone_font = QFont()
        phone_font.setPointSize(12)
        self._phone_label.setFont(phone_font)
        self._phone_label.setStyleSheet(
            "color: #a1a1aa;" if _dark else "color: #6b7280;"
        )
        layout.addWidget(self._phone_label)

    def name_label_color(self) -> str:
        """Return the hex color applied to the name label (used by a11y tests)."""
        style = self._name_label.styleSheet()
        for part in style.split(";"):
            if "color" in part:
                return part.split(":")[1].strip()
        return "#111827"

    def phone_label_color(self) -> str:
        """Return the hex color applied to the phone label (used by a11y tests)."""
        style = self._phone_label.styleSheet()
        for part in style.split(";"):
            if "color" in part:
                return part.split(":")[1].strip()
        return "#6b7280"

    def update_contact(self, name: str, phone: str, message_type: str = "SMS") -> None:  # noqa: ARG002
        self._name_label.setText(name)
        # Show the phone line only when it adds information (differs from name).
        # Suppress the message-type label — SMS vs iMessage is undetectable via MAP.
        if phone and phone != name:
            self._phone_label.setText(phone)
            self._phone_label.setVisible(True)
        else:
            self._phone_label.setText("")
            self._phone_label.setVisible(False)
        self.setAccessibleName(f"{name}, {phone}")

    def set_group_info(self, participants: list[str]) -> None:
        """Update header for a group conversation."""
        title = ", ".join(participants)
        if len(title) > 60:
            title = title[:57] + "..."
        n = len(participants)
        self._name_label.setText(title)
        name_font = self._name_label.font()
        name_font.setPointSize(15)
        self._name_label.setFont(name_font)
        self._name_label.setStyleSheet("color: #f4f4f5;")
        self._phone_label.setText(f"Group · {n} participants")
        phone_font = self._phone_label.font()
        phone_font.setPointSize(11)
        self._phone_label.setFont(phone_font)
        self._phone_label.setStyleSheet("color: #71717a;")
        self.setAccessibleName(f"Group conversation with {n} participants")


class ThreadView(QWidget):
    """Right pane (minus compose): thread header + scrollable message bubbles."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._last_outbound: Optional[MessageBubble] = None
        self._last_date_key: str = ""  # YYYYMMDD of the most recently rendered message
        self._is_group = False
        self._participants: list[str] = []
        self._build()

    def set_group_mode(self, is_group: bool, participants: list[str] | None = None) -> None:
        """Toggle group-thread rendering for the current conversation."""
        self._is_group = is_group
        self._participants = list(participants or [])
        if is_group and self._participants:
            self._header.set_group_info(self._participants)

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._header = ThreadHeader()
        layout.addWidget(self._header)

        # Scrollable message area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.NoFrame)

        self._messages_container = QWidget()
        self._messages_layout = QVBoxLayout(self._messages_container)
        self._messages_layout.setContentsMargins(8, 8, 8, 8)
        self._messages_layout.setSpacing(4)

        # Empty state label
        self._empty_label = QLabel("Select a conversation to read messages")
        empty_font = QFont()
        empty_font.setPointSize(14)
        self._empty_label.setFont(empty_font)
        self._empty_label.setStyleSheet("color: #9ca3af;")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setAccessibleName(self.tr("No conversation selected"))
        self._messages_layout.addStretch()
        self._messages_layout.addWidget(self._empty_label, alignment=Qt.AlignCenter)
        self._messages_layout.addStretch()

        self._scroll.setWidget(self._messages_container)
        self.setAccessibleName(self.tr("No conversation selected"))
        layout.addWidget(self._scroll, stretch=1)

    def load_thread(
        self,
        name: str,
        phone: str,
        messages: list[MessageData],
        message_type: str = "SMS",
    ) -> None:
        self._header.update_contact(name, phone, message_type)
        self._last_outbound = None  # new thread — prior bubble ref is stale

        # Clear existing bubbles; never deleteLater the empty label (keep Python ref valid)
        while self._messages_layout.count():
            item = self._messages_layout.takeAt(0)
            w = item.widget()
            if w and w is not self._empty_label:
                w.deleteLater()
        self._empty_label.hide()

        if not messages:
            self._empty_label.show()
            self._messages_layout.addStretch()
            self._messages_layout.addWidget(self._empty_label, alignment=Qt.AlignCenter)
            self._messages_layout.addStretch()
            return

        self._messages_layout.addStretch()
        self._last_date_key = ""
        for msg in messages:
            date_key = msg.sort_key[:8] if msg.sort_key else ""
            if date_key and self._last_date_key and date_key != self._last_date_key:
                label_text = _date_label_text(msg.sort_key)
                self._messages_layout.addWidget(DateSeparatorWidget(label_text))
            if date_key:
                self._last_date_key = date_key
            bubble = MessageBubble(msg)
            self._messages_layout.addWidget(bubble)

        # Scroll to bottom once Qt recomputes the content height.
        # singleShot(0) fires before QScrollArea processes QEvent::LayoutRequest
        # and updates the scroll range, so the old scroll value was set against
        # a stale maximum.  rangeChanged fires exactly when the range is updated
        # (guaranteed post-layout), and we disconnect immediately after the first
        # fire to act as a one-shot.
        sb = self._scroll.verticalScrollBar()

        def _on_range_changed(min_val: int, max_val: int) -> None:
            try:
                sb.rangeChanged.disconnect(_on_range_changed)
            except RuntimeError:
                pass
            try:
                sb.setValue(max_val)
            except RuntimeError:
                pass  # widget deleted before deferred call ran

        sb.rangeChanged.connect(_on_range_changed)

    def append_message(self, msg: MessageData) -> None:
        """Append a single bubble to the live thread and scroll to bottom.

        Only scrolls to bottom if the view was already pinned at the bottom
        (user hasn't scrolled up) — prevents bouncing when messages page in.
        """
        if self._messages_layout.indexOf(self._empty_label) >= 0:
            # Remove the "no messages" placeholder (keep ref — never deleteLater it)
            while self._messages_layout.count():
                item = self._messages_layout.takeAt(0)
                w = item.widget()
                if w and w is not self._empty_label:
                    w.deleteLater()
            self._empty_label.hide()
            self._messages_layout.addStretch()

        date_key = msg.sort_key[:8] if msg.sort_key else ""
        if date_key and date_key != self._last_date_key:
            label_text = _date_label_text(msg.sort_key)
            self._messages_layout.addWidget(DateSeparatorWidget(label_text))
            self._last_date_key = date_key

        bubble = MessageBubble(msg)
        self._messages_layout.addWidget(bubble)
        if msg.bubble_type == BubbleType.OUTBOUND:
            self._last_outbound = bubble

        scroll_ref = self._scroll
        sb = scroll_ref.verticalScrollBar()
        at_bottom = sb.value() >= sb.maximum() - 4  # 4px tolerance

        if at_bottom:
            def _on_append_range_changed(min_val: int, max_val: int) -> None:
                try:
                    sb.rangeChanged.disconnect(_on_append_range_changed)
                except RuntimeError:
                    pass
                try:
                    sb.setValue(max_val)
                except RuntimeError:
                    pass
            sb.rangeChanged.connect(_on_append_range_changed)

    def mark_last_send_failed(self) -> None:
        """Update the most recently appended outbound bubble to show '⚠ Failed'."""
        if self._last_outbound is not None:
            self._last_outbound.set_send_failed()

    def mark_last_send_delivered(self) -> None:
        """Update the most recently appended outbound bubble to show 'Delivered ✓'."""
        if self._last_outbound is not None:
            self._last_outbound.set_send_delivered()

    def show_empty(self) -> None:
        while self._messages_layout.count():
            item = self._messages_layout.takeAt(0)
            w = item.widget()
            if w and w is not self._empty_label:
                w.deleteLater()
        self._empty_label.show()
        self._messages_layout.addStretch()
        self._messages_layout.addWidget(self._empty_label, alignment=Qt.AlignCenter)
        self._messages_layout.addStretch()
        self._header.update_contact("", "", "")
