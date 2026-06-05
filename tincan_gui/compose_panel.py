"""Compose panel with character counter, routing hint, and send button."""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAccessible, QFont, QKeyEvent
from PySide6.QtWidgets import (
    QAccessibleWidget,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from tincan_gui.theme import is_dark_theme
from tincan_gui.thread_view import _emoji_font_families

_SMS_SINGLE_LIMIT = 160
_SMS_MULTI_LIMIT = 153
_SMS_UCS2_SINGLE = 70
_SMS_UCS2_MULTI = 67

# GSM 7-bit charset: basic (1 septet) plus extended (2 septets via ESC prefix).
# Characters outside this set force UCS-2 encoding with 70/67-char limits.
_GSM7_CHARSET = frozenset(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ"
    " !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿"
    "abcdefghijklmnopqrstuvwxyzäöñüà"
    "\x0c€^{}[~]\\|"  # extended table via ESC
)


def _is_ucs2(text: str) -> bool:
    """Return True if *text* contains characters outside the GSM-7 charset."""
    return any(c not in _GSM7_CHARSET for c in text)


_COMPOSE_HINTS: dict[str, str] = {
    "phone number unavailable for this thread": "Can't reply — no number for this contact",
    "messaging unavailable": "Can't reply — messaging unavailable",
    "not connected": "Can't reply — not connected to device",
}


def _compose_hint(reason: str) -> str:
    """Return a user-facing hint string for a disabled-compose reason."""
    return _COMPOSE_HINTS.get(reason, f"Can't reply — {reason}" if reason else "Can't reply")


class _ErrorBar(QWidget):
    """Error bar widget — subclassed so the a11y factory can give it AlertMessage role."""


def _error_bar_factory(classname: str, obj) -> Optional[QAccessibleWidget]:
    if isinstance(obj, _ErrorBar):
        return QAccessibleWidget(obj, QAccessible.Role.AlertMessage)
    return None


QAccessible.installFactory(_error_bar_factory)


def _sms_segments(text: str) -> tuple[int, int, int]:
    """Return (total_chars, segment_count, chars_in_last_segment).

    Uses UCS-2 limits (70/67) when the text requires UCS-2 encoding.
    """
    n = len(text)
    if n == 0:
        return 0, 0, 0
    ucs2 = _is_ucs2(text)
    single = _SMS_UCS2_SINGLE if ucs2 else _SMS_SINGLE_LIMIT
    multi = _SMS_UCS2_MULTI if ucs2 else _SMS_MULTI_LIMIT
    if n <= single:
        return n, 1, n
    parts = math.ceil(n / multi)
    chars_in_last = n - (parts - 1) * multi
    return n, parts, chars_in_last


class _MessageInput(QPlainTextEdit):
    """QPlainTextEdit that emits send_requested on Return (not Shift+Return)."""

    send_requested = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        is_return = event.key() == Qt.Key.Key_Return
        is_shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if is_return and not is_shift:
            self.send_requested.emit()
        else:
            super().keyPressEvent(event)


class ComposePanel(QWidget):
    """Bottom compose area: routing hint, text input, char counter, send button."""

    send_requested = Signal(str)    # emits message text

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("composePanel")
        self.setMinimumHeight(80)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        if is_dark_theme():
            self.setStyleSheet("background: #27272a; border-top: 1px solid #3f3f46;")
        else:
            self.setStyleSheet("background: #ffffff; border-top: 1px solid #e5e7eb;")
        self._enabled = True
        self._disable_reason = ""
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(4)

        # Error bar (hidden until a send failure occurs)
        _dark = is_dark_theme()
        self._error_bar = _ErrorBar()
        self._error_bar.setMinimumHeight(32)
        self._error_bar.setAccessibleName("Send error notification")
        self._error_bar.setAccessibleDescription("Message failed to send")
        if _dark:
            self._error_bar.setStyleSheet(
                "background: #3f1212; border-top: 1px solid #991b1b;"
            )
        else:
            self._error_bar.setStyleSheet(
                "background: #fef2f2; border-top: 1px solid #fca5a5;"
            )
        err_row = QHBoxLayout(self._error_bar)
        err_row.setContentsMargins(8, 4, 8, 4)
        err_row.setSpacing(8)

        warn_label = QLabel("⚠")
        warn_label.setStyleSheet("color: #f87171;" if _dark else "color: #dc2626;")
        err_row.addWidget(warn_label)

        self._error_text = QLabel("Failed to send")
        self._error_text.setStyleSheet("color: #fca5a5;" if _dark else "color: #991b1b;")
        self._error_text.setWordWrap(True)
        err_font = QFont()
        err_font.setPointSize(11)
        self._error_text.setFont(err_font)
        err_row.addWidget(self._error_text, stretch=1)

        self._retry_btn = QPushButton("Retry")
        self._retry_btn.setFixedHeight(24)
        self._retry_btn.setAccessibleName("Retry sending message")
        self._retry_btn.setStyleSheet(
            "QPushButton { font-size: 11px; padding: 0 8px; border-radius: 3px;"
            " background: #dc2626; color: #fff; border: none; }"
            "QPushButton:hover { background: #b91c1c; }"
        ) if not _dark else self._retry_btn.setStyleSheet(
            "QPushButton { font-size: 11px; padding: 0 8px; border-radius: 3px;"
            " background: #991b1b; color: #fff; border: none; }"
            "QPushButton:hover { background: #7f1d1d; }"
        )
        self._retry_btn.clicked.connect(self._on_retry)
        err_row.addWidget(self._retry_btn)

        dismiss_btn = QToolButton()
        dismiss_btn.setText("×")
        dismiss_btn.setFixedSize(24, 24)
        dismiss_btn.setAccessibleName("Dismiss send error")
        dismiss_btn.setStyleSheet(
            "QToolButton { border: none; color: #fca5a5; font-size: 14px; }"
        ) if _dark else dismiss_btn.setStyleSheet(
            "QToolButton { border: none; color: #991b1b; font-size: 14px; }"
        )
        dismiss_btn.clicked.connect(self.hide_send_error)
        err_row.addWidget(dismiss_btn)

        self._error_bar.setVisible(False)
        outer.addWidget(self._error_bar)

        self._retry_text: str = ""

        # Input row
        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self._input = _MessageInput()
        self._input.setPlaceholderText("Type a message…")
        self._input.setFixedHeight(52)
        _input_font = QFont()
        _input_font.setFamilies(_emoji_font_families())
        _input_font.setPointSize(13)
        self._input.setFont(_input_font)
        self._input.setTabChangesFocus(True)   # Tab moves to Send button
        self._input.send_requested.connect(self._on_send)
        self._input.textChanged.connect(self._on_text_changed)
        input_row.addWidget(self._input, stretch=1)

        right_col = QVBoxLayout()
        right_col.setSpacing(4)

        self._send_btn = QPushButton("Send")
        self._send_btn.setObjectName("sendButton")
        self._send_btn.setFixedSize(64, 48)
        self._send_btn.setStyleSheet(
            "QPushButton { background-color: #0d9488; color: #ffffff; "
            "border-radius: 6px; font-size: 14px; font-weight: bold; }"
            "QPushButton:disabled { background-color: #0d9488; opacity: 0.4; }"
            "QPushButton:hover:!disabled { background-color: #0f766e; }"
        )
        self._send_btn.setAccessibleName("Send SMS message")
        self._send_btn.clicked.connect(self._on_send)
        right_col.addWidget(self._send_btn)
        right_col.addStretch()

        input_row.addLayout(right_col)
        outer.addLayout(input_row)

        # Character counter (below input, left-aligned)
        self._char_counter = QLabel("0/160")
        counter_font = QFont()
        counter_font.setPointSize(10)
        self._char_counter.setFont(counter_font)
        self._char_counter.setStyleSheet("color: #9ca3af;")
        outer.addWidget(self._char_counter, alignment=Qt.AlignLeft)

    def _on_text_changed(self) -> None:
        text = self._input.toPlainText()
        total, parts, last = _sms_segments(text)
        ucs2 = _is_ucs2(text)
        single_limit = _SMS_UCS2_SINGLE if ucs2 else _SMS_SINGLE_LIMIT
        multi_limit = _SMS_UCS2_MULTI if ucs2 else _SMS_MULTI_LIMIT
        if parts <= 1:
            self._char_counter.setText(f"{total}/{single_limit}")
            self._char_counter.setStyleSheet("color: #9ca3af;")
        else:
            self._char_counter.setText(f"{parts} seg · {last}/{multi_limit}")
            self._char_counter.setStyleSheet("color: #d97706;")

    def _on_send(self) -> None:
        if not self._enabled:
            return
        text = self._input.toPlainText().strip()
        if text:
            self.send_requested.emit(text)
            self._input.clear()

    @property
    def send_button(self):
        """Expose send button for accessibility tests."""
        return self._send_btn

    def set_group_mode(self, is_group: bool) -> None:
        """Update compose bar for 1:1 vs group conversation."""
        if is_group:
            self._input.setPlaceholderText("Reply to group…")
            self._char_counter.setVisible(False)
        else:
            self._input.setPlaceholderText("Type a message…")
            self._char_counter.setVisible(True)

    def set_compose_enabled(self, enabled: bool, reason: str = "") -> None:
        self._enabled = enabled
        self._disable_reason = reason
        self._input.setEnabled(enabled)
        self._send_btn.setEnabled(enabled)

        if enabled:
            self._input.setPlaceholderText("Type a message…")
            self._input.setStyleSheet("")
            self._send_btn.setStyleSheet(
                "QPushButton { background-color: #0d9488; color: #ffffff; "
                "border-radius: 6px; font-size: 14px; font-weight: bold; }"
                "QPushButton:hover { background-color: #0f766e; }"
            )
            self._input.setToolTip("")
            self._send_btn.setToolTip("")
            self._send_btn.setAccessibleName("Send SMS message")
        else:
            hint = _compose_hint(reason)
            self._input.setPlaceholderText(hint)
            _dark = is_dark_theme()
            self._input.setStyleSheet(
                "QPlainTextEdit { background: #3f3f46; color: #a1a1aa; }"
                if _dark else
                "QPlainTextEdit { background: #f3f4f6; color: #6b7280; }"
            )
            self._send_btn.setStyleSheet(
                "QPushButton { background-color: #0d9488; color: #ffffff; "
                "border-radius: 6px; font-size: 14px; }"
            )
            tooltip = f"Sending unavailable — {reason}" if reason else "Sending unavailable"
            self._input.setToolTip(tooltip)
            self._send_btn.setToolTip(tooltip)
            self._send_btn.setAccessibleName(
                f"Send unavailable — {reason}" if reason else "Send unavailable"
            )

    def show_send_error(self, failed_text: str) -> None:
        """Show the send error bar and store text for retry."""
        self._retry_text = failed_text
        self._error_bar.setVisible(True)
        self._retry_btn.setFocus()

    def hide_send_error(self) -> None:
        """Hide the send error bar."""
        self._error_bar.setVisible(False)
        self._retry_text = ""

    def _on_retry(self) -> None:
        text = self._retry_text  # save before hide clears it
        self.hide_send_error()
        if text:
            self._input.setPlainText(text)
            self._on_send()
