"""Compose panel with character counter, routing hint, and send button."""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

_SMS_SINGLE_LIMIT = 160
_SMS_MULTI_LIMIT = 153


def _sms_segments(text: str) -> tuple[int, int, int]:
    """Return (total_chars, segment_count, chars_in_last_segment)."""
    n = len(text)
    if n == 0:
        return 0, 0, 0
    if n <= _SMS_SINGLE_LIMIT:
        return n, 1, n
    parts = math.ceil(n / _SMS_MULTI_LIMIT)
    chars_in_last = n - (parts - 1) * _SMS_MULTI_LIMIT
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
        self.setFixedHeight(100)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet("background: #ffffff; border-top: 1px solid #e5e7eb;")
        self._enabled = True
        self._disable_reason = ""
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(4)

        # Routing hint
        self._routing_hint = QLabel("Sending as SMS · may upgrade to iMessage on delivery")
        hint_font = QFont()
        hint_font.setPointSize(11)
        self._routing_hint.setFont(hint_font)
        self._routing_hint.setStyleSheet("color: #6b7280;")
        outer.addWidget(self._routing_hint)

        # Input row
        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self._input = _MessageInput()
        self._input.setPlaceholderText("Type a message…")
        self._input.setFixedHeight(52)
        self._input.setTabChangesFocus(True)   # Tab moves to Send button
        self._input.send_requested.connect(self._on_send)
        self._input.textChanged.connect(self._on_text_changed)
        input_row.addWidget(self._input, stretch=1)

        right_col = QVBoxLayout()
        right_col.setSpacing(4)

        self._send_btn = QPushButton("Send")
        self._send_btn.setFixedSize(64, 48)
        self._send_btn.setStyleSheet(
            "QPushButton { background-color: #1d4ed8; color: #ffffff; "
            "border-radius: 6px; font-size: 14px; font-weight: bold; }"
            "QPushButton:disabled { background-color: #1d4ed8; opacity: 0.4; }"
            "QPushButton:hover:!disabled { background-color: #1e40af; }"
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
        if parts <= 1:
            self._char_counter.setText(f"{total}/{_SMS_SINGLE_LIMIT}")
            self._char_counter.setStyleSheet("color: #9ca3af;")
        else:
            self._char_counter.setText(f"{parts} seg · {last}/{_SMS_MULTI_LIMIT}")
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

    def set_compose_enabled(self, enabled: bool, reason: str = "") -> None:
        self._enabled = enabled
        self._disable_reason = reason
        self._input.setEnabled(enabled)
        self._send_btn.setEnabled(enabled)

        if enabled:
            self._input.setStyleSheet("")
            self._send_btn.setStyleSheet(
                "QPushButton { background-color: #1d4ed8; color: #ffffff; "
                "border-radius: 6px; font-size: 14px; font-weight: bold; }"
                "QPushButton:hover { background-color: #1e40af; }"
            )
            self._input.setToolTip("")
            self._send_btn.setToolTip("")
            self._send_btn.setAccessibleName("Send SMS message")
        else:
            self._input.setStyleSheet("opacity: 0.4;")
            self._send_btn.setStyleSheet(
                "QPushButton { background-color: #1d4ed8; color: #ffffff; "
                "border-radius: 6px; font-size: 14px; opacity: 0.4; }"
            )
            tooltip = f"Sending unavailable — {reason}" if reason else "Sending unavailable"
            self._input.setToolTip(tooltip)
            self._send_btn.setToolTip(tooltip)
            self._send_btn.setAccessibleName(
                f"Send unavailable — {reason}" if reason else "Send unavailable"
            )
