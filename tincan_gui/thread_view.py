"""Thread view: ThreadHeader, MessageBubble (4 types), ThreadView."""
from __future__ import annotations

import html as _html
import re as _re
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAccessible, QFont
from PySide6.QtWidgets import (
    QAccessibleWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from tincan_gui.theme import is_dark_theme

_URL_RE = _re.compile(r"(https?://[^\s<>\"']+)")


def _linkify(text: str) -> str:
    """HTML-escape text and wrap URLs in clickable <a> tags."""
    return _URL_RE.sub(r'<a href="\1">\1</a>', _html.escape(text))


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

        bubble.setStyleSheet(
            f"background-color: {bg}; border-radius: 12px;"
        )

        ml = style["margin_left"]
        mr = style["margin_right"]
        outer.setContentsMargins(ml, 0, mr, 0)
        outer.addWidget(bubble)

        if style["align"] == Qt.AlignLeft:
            outer.addStretch()

    def metadata_label_color(self) -> str:
        """Return the hex color applied to the metadata label (used by a11y tests)."""
        return self._meta_color

    def _update_accessible(self) -> None:
        btype = self._data.bubble_type
        if btype == BubbleType.OUTBOUND:
            # Outbound has no "from" — announce direction + body + time only
            self.setAccessibleName(
                f"Outbound: {self._data.body} — sent at {self._data.timestamp}"
            )
        elif btype == BubbleType.BODY_UNAVAILABLE:
            self.setAccessibleName(
                f"Inbound: content unavailable — from {self._data.sender}"
                f" at {self._data.timestamp}"
            )
        elif btype == BubbleType.GROUP_UNKNOWN_SENDER:
            self.setAccessibleName(
                f"Inbound: {self._data.body} — from {self._data.sender} at {self._data.timestamp}"
            )
        else:  # INBOUND
            self.setAccessibleName(
                f"Inbound: {self._data.body} — from {self._data.sender} at {self._data.timestamp}"
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

    def update_contact(self, name: str, phone: str, message_type: str = "SMS") -> None:
        self._name_label.setText(name)
        self._phone_label.setText(f"{phone}  ·  {message_type}")


class ThreadView(QWidget):
    """Right pane (minus compose): thread header + scrollable message bubbles."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._build()

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
        self._empty_label.setAccessibleName("No conversation selected")
        self._messages_layout.addStretch()
        self._messages_layout.addWidget(self._empty_label, alignment=Qt.AlignCenter)
        self._messages_layout.addStretch()

        self._scroll.setWidget(self._messages_container)
        self.setAccessibleName("No conversation selected")
        layout.addWidget(self._scroll, stretch=1)

    def load_thread(
        self,
        name: str,
        phone: str,
        messages: list[MessageData],
        message_type: str = "SMS",
    ) -> None:
        self._header.update_contact(name, phone, message_type)

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
        for msg in messages:
            bubble = MessageBubble(msg)
            self._messages_layout.addWidget(bubble)

        # Scroll to latest after Qt recomputes layout geometry
        scroll_ref = self._scroll

        def _scroll_to_bottom() -> None:
            try:
                sb = scroll_ref.verticalScrollBar()
                sb.setValue(sb.maximum())
            except RuntimeError:
                pass  # widget deleted before deferred call ran

        QTimer.singleShot(0, _scroll_to_bottom)

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

        bubble = MessageBubble(msg)
        self._messages_layout.addWidget(bubble)

        scroll_ref = self._scroll
        sb = scroll_ref.verticalScrollBar()
        at_bottom = sb.value() >= sb.maximum() - 4  # 4px tolerance

        if at_bottom:
            def _scroll_to_bottom() -> None:
                try:
                    sb = scroll_ref.verticalScrollBar()
                    sb.setValue(sb.maximum())
                except RuntimeError:
                    pass
            QTimer.singleShot(0, _scroll_to_bottom)

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
