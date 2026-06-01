"""
tincan_gui.widgets — tested widget components per tincan-s42.
All widgets satisfy the accessibility API contract in tests/tincan_gui/test_accessibility.py.
Bead: tincan-9ho.
"""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAccessible, QFont, QKeyEvent, QKeySequence
from PySide6.QtWidgets import (
    QAccessibleWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QShortcut,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# Accessible role factory — registered once at module import
# ---------------------------------------------------------------------------

def _tincan_accessible_factory(classname: str, obj) -> Optional[QAccessibleWidget]:
    if isinstance(obj, ConversationItem):
        return QAccessibleWidget(obj, QAccessible.Role.ListItem)
    if isinstance(obj, MessageBubble):
        return QAccessibleWidget(obj, QAccessible.Role.StaticText)
    if isinstance(obj, CapabilityBanner):
        return QAccessibleWidget(obj, QAccessible.Role.AlertMessage)
    return None


QAccessible.installFactory(_tincan_accessible_factory)


# ---------------------------------------------------------------------------
# ConversationItem
# ---------------------------------------------------------------------------

class ConversationItem(QFrame):
    """Single conversation row (h=72) with WCAG AA metadata color."""

    _TS_COLOR = "#6b7280"   # AA-compliant replacement for failing #9ca3af
    _SELECTED_BG = "#dbeafe"
    _SELECTED_BORDER = "#bfdbfe"
    _UNREAD_DOT = "#1d4ed8"

    def __init__(
        self,
        name: str,
        preview: str,
        timestamp: str,
        unread: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._name = name
        self._unread = unread
        self.setFixedHeight(72)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        top_row = QHBoxLayout()
        name_label = QLabel(name)
        name_font = QFont()
        name_font.setPointSize(14)
        name_font.setBold(True)
        name_label.setFont(name_font)
        top_row.addWidget(name_label, stretch=1)

        self._ts_label = QLabel(timestamp)
        ts_font = QFont()
        ts_font.setPointSize(11)
        self._ts_label.setFont(ts_font)
        self._ts_label.setStyleSheet(f"color: {self._TS_COLOR};")
        top_row.addWidget(self._ts_label)
        text_col.addLayout(top_row)

        preview_short = preview[:36] + "…" if len(preview) > 36 else preview
        preview_label = QLabel(preview_short)
        prev_font = QFont()
        prev_font.setPointSize(12)
        preview_label.setFont(prev_font)
        preview_label.setStyleSheet(f"color: {self._TS_COLOR};")
        text_col.addWidget(preview_label)
        layout.addLayout(text_col, stretch=1)

        dot = QLabel()
        dot.setFixedSize(10, 10)
        dot.setStyleSheet(f"background-color: {self._UNREAD_DOT}; border-radius: 5px;")
        dot.setVisible(unread)
        layout.addWidget(dot, alignment=Qt.AlignVCenter)

        # Accessible name: includes "Unread" when unread
        an = f"Conversation with {name}, last message {preview}, {timestamp}"
        if unread:
            an += " — Unread"
        self.setAccessibleName(an)
        self.setAccessibleDescription("Unread" if unread else "")

    def timestamp_label_color(self) -> str:
        return self._TS_COLOR

    def set_selected(self, selected: bool) -> None:
        if selected:
            self.setStyleSheet(
                f"background-color: {self._SELECTED_BG}; border: 1px solid {self._SELECTED_BORDER};"
            )
        else:
            self.setStyleSheet("")


# ---------------------------------------------------------------------------
# MessageBubble
# ---------------------------------------------------------------------------

class MessageBubble(QFrame):
    """Message bubble with 2-direction + body-unavailable support. Role: StaticText."""

    _META_COLOR = "#6b7280"   # AA-compliant metadata color

    def __init__(
        self,
        direction: str,
        body: Optional[str],
        sender: Optional[str],
        timestamp: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._direction = direction
        self._meta_color = self._META_COLOR

        is_outbound = direction == "outbound"
        unavailable = body is None

        # Colors
        if is_outbound:
            bg, fg = "#1d4ed8", "#ffffff"
        elif unavailable:
            bg, fg = "#fef9c3", "#92400e"
        else:
            bg, fg = "#f3f4f6", "#111827"

        layout = QHBoxLayout(self)
        m_left = 80 if is_outbound else 20
        m_right = 20 if is_outbound else 80
        layout.setContentsMargins(m_left, 4, m_right, 4)

        if is_outbound:
            layout.addStretch()

        bubble = QWidget()
        bubble.setStyleSheet(f"background-color: {bg}; border-radius: 12px;")
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(12, 8, 12, 8)
        bubble_layout.setSpacing(4)

        body_text = "⚠ Message content unavailable — MAP did not return body" if unavailable else body
        body_label = QLabel(body_text)
        body_label.setWordWrap(True)
        body_label.setStyleSheet(f"color: {fg};")
        bubble_layout.addWidget(body_label)

        meta_text = (f"{timestamp} · Sent ✓" if is_outbound
                     else f"{sender or '?'} · {timestamp}")
        meta_label = QLabel(meta_text)
        meta_font = QFont()
        meta_font.setPointSize(10)
        meta_label.setFont(meta_font)
        meta_label.setStyleSheet(f"color: {self._meta_color};")
        meta_label.setAlignment(Qt.AlignRight if is_outbound else Qt.AlignLeft)
        bubble_layout.addWidget(meta_label)

        layout.addWidget(bubble)
        if not is_outbound:
            layout.addStretch()

        # Accessible name: direction + body + sender + time in one announcement
        if unavailable:
            an = f"Inbound: content unavailable — from {sender or '?'} at {timestamp}"
        elif is_outbound:
            an = f"Outbound: {body} at {timestamp}"
        else:
            an = f"Inbound: {body} — from {sender or '?'} at {timestamp}"
        self.setAccessibleName(an)

    def metadata_label_color(self) -> str:
        return self._meta_color


# ---------------------------------------------------------------------------
# SendButton
# ---------------------------------------------------------------------------

class SendButton(QPushButton):
    """Send button with dynamic accessible name reflecting enabled/disabled state."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("Send", parent)
        self.setFixedSize(64, 48)
        self.setStyleSheet(
            "QPushButton { background-color: #1d4ed8; color: #ffffff; "
            "border-radius: 6px; font-size: 14px; font-weight: bold; }"
            "QPushButton:hover:!disabled { background-color: #1e40af; }"
            "QPushButton:disabled { opacity: 0.4; }"
        )
        self.setAccessibleName("Send SMS message")

    def set_disabled_reason(self, reason: str) -> None:
        self.setAccessibleName(f"Send unavailable — {reason}")


# ---------------------------------------------------------------------------
# StatusChip (QLabel → role StaticText by default)
# ---------------------------------------------------------------------------

class StatusChip(QLabel):
    """Connection status chip — QLabel gives StaticText role automatically."""

    def __init__(
        self,
        connected: bool,
        device_name: Optional[str],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        font = QFont()
        font.setPointSize(12)
        self.setFont(font)
        if connected and device_name:
            self.setText(f"● Connected — {device_name}")
            self.setStyleSheet("color: #86efac;")
            self.setAccessibleName(f"Connection status: Connected — {device_name}")
        else:
            self.setText("○ Disconnected")
            self.setStyleSheet("color: #fca5a5;")
            self.setAccessibleName("Connection status: Disconnected")

    def set_connected(self, connected: bool, device_name: Optional[str] = None) -> None:
        if connected and device_name:
            self.setText(f"● Connected — {device_name}")
            self.setStyleSheet("color: #86efac;")
            self.setAccessibleName(f"Connection status: Connected — {device_name}")
        else:
            self.setText("○ Disconnected")
            self.setStyleSheet("color: #fca5a5;")
            self.setAccessibleName("Connection status: Disconnected")


# ---------------------------------------------------------------------------
# CapabilityBanner (role AlertMessage via factory)
# ---------------------------------------------------------------------------

class CapabilityBanner(QFrame):
    """Capability degradation banner with Alert role for immediate AT announcement."""

    def __init__(self, message: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        label = QLabel(message)
        label.setWordWrap(True)
        layout.addWidget(label)

        self.setAccessibleName(message)


# ---------------------------------------------------------------------------
# ConversationList
# ---------------------------------------------------------------------------

class ConversationList(QWidget):
    """Scrollable conversation list with keyboard navigation."""

    conversation_activated = Signal(object)  # emits item dict on Enter/Space

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self._items: list[ConversationItem] = []
        self._item_data: list[dict] = []
        self._current_index = -1

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._layout.addStretch()

    def load_conversations(self, conversations: list[dict]) -> None:
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._items.clear()
        self._item_data.clear()
        self._current_index = -1

        for data in conversations:
            widget = ConversationItem(
                name=data["name"],
                preview=data["preview"],
                timestamp=data["timestamp"],
                unread=data.get("unread", False),
            )
            self._layout.insertWidget(self._layout.count() - 1, widget)
            self._items.append(widget)
            self._item_data.append(data)

    def select_index(self, i: int) -> None:
        if 0 <= self._current_index < len(self._items):
            self._items[self._current_index].set_selected(False)
        self._current_index = i
        if 0 <= i < len(self._items):
            self._items[i].set_selected(True)

    def current_index(self) -> int:
        return self._current_index

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key == Qt.Key.Key_Down:
            self.select_index(min(self._current_index + 1, len(self._items) - 1))
        elif key == Qt.Key.Key_Up:
            self.select_index(max(self._current_index - 1, 0))
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Space):
            if 0 <= self._current_index < len(self._items):
                self.conversation_activated.emit(self._item_data[self._current_index])
        else:
            super().keyPressEvent(event)


# ---------------------------------------------------------------------------
# ComposePanel
# ---------------------------------------------------------------------------

_SMS_SINGLE = 160
_SMS_MULTI = 153


def _sms_counter_text(text: str) -> str:
    n = len(text)
    if n <= _SMS_SINGLE:
        return f"{n}/{_SMS_SINGLE}"
    parts = math.ceil(n / _SMS_MULTI)
    last = n - (parts - 1) * _SMS_MULTI
    return f"{parts} seg · {last}/{_SMS_MULTI}"


class _ComposeSendInput(QPlainTextEdit):
    """QPlainTextEdit: Return sends, Shift+Return inserts newline."""

    send_triggered = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Return and not (event.modifiers() & Qt.ShiftModifier):
            self.send_triggered.emit()
        else:
            super().keyPressEvent(event)


class ComposePanel(QWidget):
    """Bottom compose area with character counter and send button."""

    send_requested = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: #ffffff; border-top: 1px solid #e5e7eb;")
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(4)

        routing = QLabel("Sending as SMS · may upgrade to iMessage on delivery")
        rf = QFont()
        rf.setPointSize(11)
        routing.setFont(rf)
        routing.setStyleSheet("color: #6b7280;")
        outer.addWidget(routing)

        row = QHBoxLayout()
        row.setSpacing(8)

        self.text_input = _ComposeSendInput()
        self.text_input.setPlaceholderText("Type a message…")
        self.text_input.setFixedHeight(52)
        self.text_input.setTabChangesFocus(True)
        self.text_input.send_triggered.connect(self._on_send)
        self.text_input.textChanged.connect(self._on_text_changed)
        row.addWidget(self.text_input, stretch=1)

        self.send_button = SendButton()
        self.send_button.clicked.connect(self._on_send)
        row.addWidget(self.send_button, alignment=Qt.AlignBottom)

        outer.addLayout(row)

        self._counter = QLabel("0/160")
        cf = QFont()
        cf.setPointSize(10)
        self._counter.setFont(cf)
        self._counter.setStyleSheet("color: #9ca3af;")
        outer.addWidget(self._counter, alignment=Qt.AlignLeft)

    def _on_text_changed(self) -> None:
        text = self.text_input.toPlainText()
        self._counter.setText(_sms_counter_text(text))

    def _on_send(self) -> None:
        if not self.send_button.isEnabled():
            return
        text = self.text_input.toPlainText().strip()
        if text:
            self.send_requested.emit(text)
            self.text_input.clear()

    def set_enabled(self, enabled: bool, reason: str = "") -> None:
        self.text_input.setEnabled(enabled)
        self.send_button.setEnabled(enabled)
        if not enabled:
            self.send_button.set_disabled_reason(reason or "unavailable")


# ---------------------------------------------------------------------------
# MainWindow
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    """Main application window with testable signal API."""

    conversation_opened = Signal(object)
    message_send_requested = Signal(str)
    refresh_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("tincan")
        self.resize(1024, 700)
        self._build()
        self._wire()

    def _build(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Title bar
        title_bar = QWidget()
        title_bar.setFixedHeight(48)
        title_bar.setStyleSheet("background-color: #1e3a5f;")
        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(16, 0, 16, 0)
        wordmark = QLabel("tincan")
        wm_font = QFont()
        wm_font.setPointSize(22)
        wm_font.setBold(True)
        wordmark.setFont(wm_font)
        wordmark.setStyleSheet("color: #ffffff;")
        tb_layout.addWidget(wordmark)
        tb_layout.addStretch()
        self._status_chip = StatusChip(connected=False, device_name=None)
        tb_layout.addWidget(self._status_chip)
        root.addWidget(title_bar)

        # Splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle { background: #e5e7eb; }")

        self.conversation_list = ConversationList()
        self.conversation_list.setMinimumWidth(200)
        splitter.addWidget(self.conversation_list)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Thread area placeholder
        self._thread_area = QLabel("Select a conversation to read messages")
        self._thread_area.setAlignment(Qt.AlignCenter)
        self._thread_area.setStyleSheet("color: #9ca3af;")
        right_layout.addWidget(self._thread_area, stretch=1)

        self.compose_panel = ComposePanel()
        right_layout.addWidget(self.compose_panel)

        splitter.addWidget(right)
        splitter.setSizes([300, 724])
        root.addWidget(splitter, stretch=1)

    def _wire(self) -> None:
        self.conversation_list.conversation_activated.connect(self.conversation_opened)
        self.compose_panel.send_requested.connect(self.message_send_requested)

        QShortcut(QKeySequence("Ctrl+1"), self).activated.connect(
            self.conversation_list.setFocus
        )
        QShortcut(QKeySequence("Ctrl+N"), self).activated.connect(
            self.compose_panel.text_input.setFocus
        )
        QShortcut(QKeySequence("F5"), self).activated.connect(self.refresh_requested)
        QShortcut(QKeySequence("Ctrl+R"), self).activated.connect(self.refresh_requested)

    def load_conversations(self, conversations: list[dict]) -> None:
        self.conversation_list.load_conversations(conversations)
