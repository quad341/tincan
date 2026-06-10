"""Notification center dialog — scrollable history of in-session notifications (tincan-ka57d)."""
from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from tincan_gui.text_render import _emoji_font_families
from tincan_gui.theme import is_dark_theme

if TYPE_CHECKING:
    from tincan_gui.notifications import DesktopNotifier, NotificationEntry


def _format_ts(ts: float) -> str:
    """Convert a Unix timestamp to a human-readable short time string."""
    try:
        dt = datetime.datetime.fromtimestamp(ts)
        now = datetime.datetime.now()
        if dt.date() == now.date():
            hour = dt.hour % 12 or 12
            ampm = "AM" if dt.hour < 12 else "PM"
            return f"{hour}:{dt.minute:02d} {ampm}"
        return dt.strftime("%b %-d, %H:%M")
    except (OSError, OverflowError, ValueError):
        return ""


class _NotifRow(QWidget):
    """Single notification row: sender, summary/body, timestamp."""

    def __init__(
        self, entry: NotificationEntry, dark: bool, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        dark_bg = "#1c1c1e"
        dark_border = "#3f3f46"
        light_bg = "#f9fafb"
        light_border = "#e5e7eb"

        bg = dark_bg if dark else light_bg
        border = dark_border if dark else light_border
        self.setStyleSheet(
            f"background: {bg}; border: 1px solid {border}; border-radius: 6px;"
        )

        outer = QHBoxLayout(self)
        outer.setContentsMargins(12, 8, 12, 8)
        outer.setSpacing(8)

        # Kind badge — use _emoji_font_families so the glyph renders on systems
        # where the system font doesn't cover emoji (tincan-36af0).
        badge = QLabel("💬" if entry.kind == "sms" else "🔔")
        badge_font = QFont()
        badge_font.setFamilies(_emoji_font_families())
        badge_font.setPointSize(14)
        badge.setFont(badge_font)
        badge.setFixedWidth(20)
        badge.setAttribute(Qt.WA_TransparentForMouseEvents)
        outer.addWidget(badge, alignment=Qt.AlignTop)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        text_col.setContentsMargins(0, 0, 0, 0)

        sender_lbl = QLabel(entry.sender)
        f = QFont()
        f.setPointSize(13)
        f.setBold(True)
        sender_lbl.setFont(f)
        sender_lbl.setStyleSheet("color: #f4f4f5;" if dark else "color: #111827;")
        sender_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
        text_col.addWidget(sender_lbl)

        body_text = entry.body or entry.summary
        if body_text:
            body_lbl = QLabel(body_text[:120] + ("…" if len(body_text) > 120 else ""))
            bf = QFont()
            bf.setPointSize(11)
            body_lbl.setFont(bf)
            body_lbl.setStyleSheet("color: #a1a1aa;" if dark else "color: #6b7280;")
            body_lbl.setWordWrap(True)
            body_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
            text_col.addWidget(body_lbl)

        outer.addLayout(text_col, stretch=1)

        ts_lbl = QLabel(_format_ts(entry.ts))
        ts_f = QFont()
        ts_f.setPointSize(10)
        ts_lbl.setFont(ts_f)
        ts_lbl.setStyleSheet("color: #a1a1aa;" if dark else "color: #9ca3af;")
        ts_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
        outer.addWidget(ts_lbl, alignment=Qt.AlignTop)


class NotificationCenterDialog(QDialog):
    """Modal dialog showing the in-session notification history (newest first)."""

    def __init__(self, notifier: DesktopNotifier, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Notification Center")
        self.resize(480, 500)
        dark = is_dark_theme()

        if dark:
            self.setStyleSheet("background: #18181b;")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QWidget()
        header.setFixedHeight(44)
        header.setStyleSheet("background: #0f4c3a;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(16, 0, 16, 0)
        title_lbl = QLabel("Notifications")
        tf = QFont()
        tf.setPointSize(14)
        tf.setBold(True)
        title_lbl.setFont(tf)
        title_lbl.setStyleSheet("color: #ccfbf1;")
        h_layout.addWidget(title_lbl)
        root.addWidget(header)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        if dark:
            scroll.setStyleSheet("QScrollArea { background: #18181b; border: none; }")

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(12, 12, 12, 12)
        content_layout.setSpacing(6)

        entries = list(reversed(notifier.history()))  # newest first
        if entries:
            for entry in entries:
                row = _NotifRow(entry, dark)
                content_layout.addWidget(row)
        else:
            empty = QLabel("No notifications yet this session")
            ef = QFont()
            ef.setPointSize(12)
            empty.setFont(ef)
            empty.setStyleSheet("color: #71717a;")
            empty.setAlignment(Qt.AlignCenter)
            content_layout.addStretch()
            content_layout.addWidget(empty, alignment=Qt.AlignCenter)
            content_layout.addStretch()

        content_layout.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll, stretch=1)
