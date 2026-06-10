"""Thread view: ThreadHeader, MessageBubble (4 types), ThreadView."""
from __future__ import annotations

import base64
import datetime
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QAccessible,
    QFont,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAccessibleWidget,
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from tincan_gui import trace as _trace
from tincan_gui.avatar import AvatarWidget, _color_for_name
from tincan_gui.text_render import (
    _BARE_URL_RE,
    _URL_RE,
    _break_long_words,
    _emoji_font_families,
    _linkify,
    _linkify_preview,
    _linkify_with_highlight,
)
from tincan_gui.theme import is_dark_theme


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


def _sort_key_to_hover_text(sort_key: str) -> str:
    """Convert YYYYMMDDTHHMMSS sort_key to a readable date/time for bubble hover tooltip."""
    if not sort_key or len(sort_key) < 15:
        return ""
    try:
        dt = datetime.datetime(
            int(sort_key[:4]), int(sort_key[4:6]), int(sort_key[6:8]),
            int(sort_key[9:11]), int(sort_key[11:13]),
        )
    except (ValueError, IndexError):
        return ""
    hour = dt.hour % 12 or 12
    ampm = "AM" if dt.hour < 12 else "PM"
    return f"{dt.strftime('%A, %B')} {dt.day}, {dt.year} at {hour}:{dt.minute:02d} {ampm}"


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
    attachments: list[dict] = field(default_factory=list)


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
        body_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        body_label.setMinimumWidth(0)  # override natural-text minimumSizeHint so layout can shrink/wrap
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
            # Suppress the QLabel built-in context menu — MessageBubble.contextMenuEvent
            # handles it with hover-highlight styling and proper disabled states.
            body_label.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self._body_label = body_label
        bubble_layout.addWidget(body_label)

        for att in self._data.attachments:
            mime = att.get("mime_type", "")
            data = att.get("data", "")
            if mime.startswith("image/") and data:
                try:
                    img_bytes = base64.b64decode(data)
                    pixmap = QPixmap()
                    pixmap.loadFromData(img_bytes)
                    if not pixmap.isNull():
                        max_w = 300
                        if pixmap.width() > max_w:
                            pixmap = pixmap.scaledToWidth(
                                max_w, Qt.TransformationMode.SmoothTransformation
                            )
                        img_label = QLabel()
                        img_label.setPixmap(pixmap)
                        img_label.setAlignment(Qt.AlignCenter)
                        bubble_layout.addWidget(img_label)
                        continue
                except Exception:
                    pass
            btn = QPushButton(f"↓ Save attachment ({mime or 'unknown type'})")
            bubble_layout.addWidget(btn)

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
        hover = _sort_key_to_hover_text(self._data.sort_key)
        if hover:
            bubble.setToolTip(hover)

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


    def contextMenuEvent(self, event) -> None:
        """Right-click menu: Copy, Copy Message, Copy Link, Select All.

        Actions are disabled when unavailable so the user gets clear feedback
        rather than a silent no-op. QMenu is styled with an explicit hover
        highlight and grey-out for disabled items.
        """
        if self._data.bubble_type == BubbleType.BODY_UNAVAILABLE:
            return
        dark = is_dark_theme()
        menu = QMenu(self)
        if dark:
            menu.setStyleSheet(
                "QMenu { background: #27272a; color: #f4f4f5;"
                " border: 1px solid #3f3f46; padding: 2px; }"
                "QMenu::item { padding: 5px 24px 5px 12px; border-radius: 3px; }"
                "QMenu::item:selected, QMenu::item:hover"
                " { background: #3f3f46; color: #f4f4f5; }"
                "QMenu::item:disabled { color: #52525b; }"
            )
        else:
            menu.setStyleSheet(
                "QMenu { background: #ffffff; color: #111827;"
                " border: 1px solid #e5e7eb; padding: 2px; }"
                "QMenu::item { padding: 5px 24px 5px 12px; border-radius: 3px; }"
                "QMenu::item:selected, QMenu::item:hover"
                " { background: #f3f4f6; color: #111827; }"
                "QMenu::item:disabled { color: #9ca3af; }"
            )

        # Snapshot before exec() — menu.exec() clears any text selection.
        selected_text = self._body_label.selectedText()

        copy_act = menu.addAction("Copy")
        copy_act.setEnabled(bool(selected_text))

        copy_msg_act = menu.addAction("Copy Message")
        copy_msg_act.setEnabled(bool(self._data.body))

        body = self._data.body or ""
        urls = _URL_RE.findall(body)
        for m in _BARE_URL_RE.finditer(body):
            bare = m.group(1) or m.group(2)
            urls.append("https://" + bare)
        copy_link_act = menu.addAction("Copy Link")
        copy_link_act.setEnabled(bool(urls))

        menu.addSeparator()
        select_all_act = menu.addAction("Select All")

        chosen = menu.exec(event.globalPos())
        if chosen is None:
            return
        if chosen is copy_act:
            if selected_text:
                QApplication.clipboard().setText(selected_text)
        elif chosen is copy_msg_act:
            QApplication.clipboard().setText(self._data.body or "")
        elif chosen is copy_link_act and urls:
            QApplication.clipboard().setText(urls[0])
        elif chosen is select_all_act:
            self._body_label.selectAll()

    def matches(self, term: str) -> bool:
        """Return True if this bubble's body contains *term* (case-insensitive)."""
        if self._data.bubble_type == BubbleType.BODY_UNAVAILABLE:
            return False
        return bool(term) and term.lower() in self._data.body.lower()

    def highlight(self, term: str) -> None:
        """Re-render body label with highlighted occurrences of *term*."""
        if self._data.bubble_type == BubbleType.BODY_UNAVAILABLE:
            return
        self._body_label.setText(_linkify_with_highlight(self._data.body, term))

    def clear_highlight(self) -> None:
        """Restore body label to normal (no highlight)."""
        if self._data.bubble_type != BubbleType.BODY_UNAVAILABLE:
            self._body_label.setText(_linkify(self._data.body))


# ---------------------------------------------------------------------------
# Accessible role factory — MessageBubble → StaticText
# ---------------------------------------------------------------------------

def _thread_view_factory(classname: str, obj) -> Optional[QAccessibleWidget]:
    if isinstance(obj, MessageBubble):
        return QAccessibleWidget(obj, QAccessible.Role.StaticText)
    return None


QAccessible.installFactory(_thread_view_factory)


class ThreadHeader(QWidget):
    """Thread header bar (h=56): avatar + contact name + phone."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(56)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        _dark = is_dark_theme()
        if _dark:
            self.setStyleSheet("background: #27272a; border-bottom: 1px solid #3f3f46;")
        else:
            self.setStyleSheet("background: #ffffff; border-bottom: 1px solid #e5e7eb;")

        outer = QHBoxLayout(self)
        outer.setContentsMargins(12, 8, 16, 8)
        outer.setSpacing(10)

        self._avatar = AvatarWidget("")
        outer.addWidget(self._avatar, alignment=Qt.AlignVCenter)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        text_col.setContentsMargins(0, 0, 0, 0)

        self._name_label = QLabel("")
        name_font = QFont()
        name_font.setPointSize(15)
        self._name_label.setFont(name_font)
        self._name_label.setStyleSheet(
            "color: #f4f4f5;" if _dark else "color: #111827;"
        )
        text_col.addWidget(self._name_label)

        self._phone_label = QLabel("")
        phone_font = QFont()
        phone_font.setPointSize(11)
        self._phone_label.setFont(phone_font)
        self._phone_label.setStyleSheet(
            "color: #a1a1aa;" if _dark else "color: #6b7280;"
        )
        text_col.addWidget(self._phone_label)

        outer.addLayout(text_col, stretch=1)

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

    def set_contact_photo(self, data: bytes) -> None:
        """Update the header avatar with a PBAP photo."""
        self._avatar.set_photo(data)

    def update_contact(self, name: str, phone: str, message_type: str = "SMS") -> None:  # noqa: ARG002
        self._avatar.update_for_name(name)
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
        first = participants[0] if participants else ""
        self._avatar.update_for_name(first)
        self._name_label.setText(title)
        name_font = self._name_label.font()
        name_font.setPointSize(13)
        self._name_label.setFont(name_font)
        self._name_label.setStyleSheet("color: #f4f4f5;")
        self._phone_label.setText(f"Group · {n} participants")
        phone_font = self._phone_label.font()
        phone_font.setPointSize(11)
        self._phone_label.setFont(phone_font)
        self._phone_label.setStyleSheet("color: #71717a;")
        self.setAccessibleName(f"Group conversation with {n} participants")


class _ThreadSearchBar(QWidget):
    """Compact Ctrl+F search bar for thread view. Hidden until activated."""

    search_changed = Signal(str)
    prev_requested = Signal()
    next_requested = Signal()
    closed = Signal()

    _BTN_STYLE = (
        "QPushButton { background: transparent; border: none; color: #f4f4f5;"
        " font-size: 13px; padding: 0; }"
        " QPushButton:hover { background: #3f3f46; border-radius: 3px; }"
    )

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(34)
        self.setStyleSheet(
            "background: #27272a; border-bottom: 1px solid #3f3f46;"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(4)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Find in conversation…")
        self._input.setFixedHeight(24)
        self._input.setStyleSheet(
            "QLineEdit { border: 1px solid #52525b; border-radius: 3px;"
            " padding: 0 6px; background: #18181b; color: #f4f4f5; }"
        )
        self._input.setAccessibleName("Find in conversation")
        self._input.textChanged.connect(self.search_changed)
        layout.addWidget(self._input, stretch=1)

        self._count_label = QLabel("")
        count_font = QFont()
        count_font.setPointSize(10)
        self._count_label.setFont(count_font)
        self._count_label.setFixedWidth(70)
        self._count_label.setStyleSheet("color: #a1a1aa;")
        layout.addWidget(self._count_label)

        prev_btn = QPushButton("↑")
        prev_btn.setFixedSize(24, 24)
        prev_btn.setToolTip("Previous match (Shift+Enter)")
        prev_btn.setAccessibleName("Previous match")
        prev_btn.setStyleSheet(self._BTN_STYLE)
        prev_btn.clicked.connect(self.prev_requested)
        layout.addWidget(prev_btn)

        next_btn = QPushButton("↓")
        next_btn.setFixedSize(24, 24)
        next_btn.setToolTip("Next match (Enter)")
        next_btn.setAccessibleName("Next match")
        next_btn.setStyleSheet(self._BTN_STYLE)
        next_btn.clicked.connect(self.next_requested)
        layout.addWidget(next_btn)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setToolTip("Close search (Escape)")
        close_btn.setAccessibleName("Close search")
        close_btn.setStyleSheet(self._BTN_STYLE)
        close_btn.clicked.connect(self.closed)
        layout.addWidget(close_btn)

    def set_match_count(self, current: int, total: int) -> None:
        if total == 0:
            self._count_label.setText("No results")
            self._count_label.setStyleSheet("color: #ef4444;")
        else:
            self._count_label.setText(f"{current} / {total}")
            self._count_label.setStyleSheet("color: #a1a1aa;")

    def clear_count(self) -> None:
        self._count_label.setText("")
        self._count_label.setStyleSheet("color: #a1a1aa;")

    def focus_input(self) -> None:
        self._input.setFocus()
        self._input.selectAll()

    def current_text(self) -> str:
        return self._input.text()

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self._input.clear()
            self.closed.emit()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.ShiftModifier:
                self.prev_requested.emit()
            else:
                self.next_requested.emit()
        else:
            super().keyPressEvent(event)


class ThreadView(QWidget):
    """Right pane (minus compose): thread header + scrollable message bubbles."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._last_outbound: Optional[MessageBubble] = None
        self._last_date_key: str = ""  # YYYYMMDD of the most recently rendered message
        self._is_group = False
        self._participants: list[str] = []
        self._match_bubbles: list[MessageBubble] = []
        self._match_index: int = 0
        self._bubble_count: int = 0  # number of bubbles in current thread (for trace)
        self._build()

    def set_group_mode(self, is_group: bool, participants: list[str] | None = None) -> None:
        """Toggle group-thread rendering for the current conversation."""
        self._is_group = is_group
        self._participants = list(participants or [])
        if is_group and self._participants:
            self._header.set_group_info(self._participants)

    def set_header_photo(self, data: bytes) -> None:
        """Update the header avatar with a PBAP photo for the current contact."""
        self._header.set_contact_photo(data)

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._header = ThreadHeader()
        layout.addWidget(self._header)

        # In-thread search bar (Ctrl+F, hidden until activated)
        self._search_bar = _ThreadSearchBar()
        self._search_bar.hide()
        self._search_bar.search_changed.connect(self._on_search_changed)
        self._search_bar.prev_requested.connect(self._on_search_prev)
        self._search_bar.next_requested.connect(self._on_search_next)
        self._search_bar.closed.connect(self._on_search_closed)
        layout.addWidget(self._search_bar)

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
        failures: set[str] | None = None,
    ) -> None:
        self._header.update_contact(name, phone, message_type)
        self._last_outbound = None  # new thread — prior bubble ref is stale
        self._bubble_count = 0

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
        sep_count = 0
        for msg in messages:
            date_key = msg.sort_key[:8] if msg.sort_key else ""
            if date_key and date_key != self._last_date_key:
                label_text = _date_label_text(msg.sort_key)
                self._messages_layout.addWidget(DateSeparatorWidget(label_text))
                _trace.emit("date_separator", source="load_thread", index=self._bubble_count,
                            date_key=date_key, label=label_text)
                sep_count += 1
            if date_key:
                self._last_date_key = date_key
            bubble = MessageBubble(msg)
            if failures and msg.bubble_type == BubbleType.OUTBOUND and msg.body in failures:
                bubble.set_send_failed()
            self._messages_layout.addWidget(bubble)
            self._bubble_count += 1
        _trace.emit("thread_render", phone=phone, msg_count=len(messages), sep_count=sep_count)

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
        new_sep = False
        if date_key and date_key != self._last_date_key:
            label_text = _date_label_text(msg.sort_key)
            self._messages_layout.addWidget(DateSeparatorWidget(label_text))
            _trace.emit("date_separator", source="append", index=self._bubble_count,
                        date_key=date_key, label=label_text)
            self._last_date_key = date_key
            new_sep = True

        _trace.emit("bubble_append", bubble=msg.bubble_type.name, index=self._bubble_count,
                    date_key=date_key, new_sep=new_sep, body_len=len(msg.body or ""))
        bubble = MessageBubble(msg)
        self._messages_layout.addWidget(bubble)
        self._bubble_count += 1
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

    # ------------------------------------------------------------------
    # In-thread search (Ctrl+F)
    # ------------------------------------------------------------------

    def show_search(self) -> None:
        """Reveal the search bar and focus it (called from Ctrl+F shortcut)."""
        self._search_bar.show()
        self._search_bar.focus_input()

    def _all_bubbles(self) -> list[MessageBubble]:
        result = []
        for i in range(self._messages_layout.count()):
            item = self._messages_layout.itemAt(i)
            if item and isinstance(item.widget(), MessageBubble):
                result.append(item.widget())
        return result

    def _on_search_changed(self, term: str) -> None:
        self._match_bubbles = []
        for bubble in self._all_bubbles():
            if bubble.matches(term):
                bubble.highlight(term)
                self._match_bubbles.append(bubble)
            else:
                bubble.clear_highlight()
        self._match_index = 0
        if self._match_bubbles:
            self._search_bar.set_match_count(1, len(self._match_bubbles))
            self._scroll.ensureWidgetVisible(self._match_bubbles[0], 0, 50)
        elif term:
            self._search_bar.set_match_count(0, 0)
        else:
            self._search_bar.clear_count()

    def _on_search_next(self) -> None:
        if not self._match_bubbles:
            return
        self._match_index = (self._match_index + 1) % len(self._match_bubbles)
        self._search_bar.set_match_count(self._match_index + 1, len(self._match_bubbles))
        self._scroll.ensureWidgetVisible(self._match_bubbles[self._match_index], 0, 50)

    def _on_search_prev(self) -> None:
        if not self._match_bubbles:
            return
        self._match_index = (self._match_index - 1) % len(self._match_bubbles)
        self._search_bar.set_match_count(self._match_index + 1, len(self._match_bubbles))
        self._scroll.ensureWidgetVisible(self._match_bubbles[self._match_index], 0, 50)

    def _on_search_closed(self) -> None:
        self._search_bar.hide()
        for bubble in self._all_bubbles():
            bubble.clear_highlight()
        self._match_bubbles = []
        self._match_index = 0
