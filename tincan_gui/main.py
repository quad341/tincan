"""Main window: QMainWindow with title bar, QSplitter, and component wiring."""
from __future__ import annotations

import sys
import warnings
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeyEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from tincan_gui.compose_panel import ComposePanel
from tincan_gui.conversation_list import ConversationData, ConversationListWidget
from tincan_gui.thread_view import BubbleType, MessageData, ThreadView


class TitleBar(QWidget):
    """Title bar (h=48, navy #1e3a5f): wordmark + connection status chip."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(48)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet("background-color: #1e3a5f;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)

        wordmark = QLabel("tincan")
        wm_font = QFont()
        wm_font.setPointSize(22)
        wm_font.setBold(True)
        wordmark.setFont(wm_font)
        wordmark.setStyleSheet("color: #ffffff;")
        layout.addWidget(wordmark)

        layout.addStretch()

        self._status_chip = QLabel("○ Disconnected")
        chip_font = QFont()
        chip_font.setPointSize(12)
        self._status_chip.setFont(chip_font)
        self._status_chip.setStyleSheet("color: #fca5a5;")
        self._status_chip.setAccessibleName("Connection status: Disconnected")
        layout.addWidget(self._status_chip)

    @property
    def status_chip(self) -> QLabel:
        """Expose status chip label for accessibility tests."""
        return self._status_chip

    def set_connected(self, device_name: str) -> None:
        self._status_chip.setText(f"● Connected — {device_name}")
        self._status_chip.setStyleSheet("color: #86efac;")
        self._status_chip.setAccessibleName(f"Connection status: Connected — {device_name}")

    def set_disconnected(self) -> None:
        self._status_chip.setText("○ Disconnected")
        self._status_chip.setStyleSheet("color: #fca5a5;")
        self._status_chip.setAccessibleName("Connection status: Disconnected")


class MainWindow(QMainWindow):
    """Top-level window: title bar + QSplitter(left 300px, right pane)."""

    conversation_opened = Signal(object)
    message_send_requested = Signal(str)
    refresh_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("tincan")
        self.resize(1024, 700)
        self.setMinimumSize(600, 400)
        self._build()
        self._wire()
        self._load_stub_data()

    def _build(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Title bar
        self._title_bar = TitleBar()
        root_layout.addWidget(self._title_bar)

        # Splitter: left sidebar + right content
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle { background: #e5e7eb; }")

        # Left: conversation list
        self._conv_list = ConversationListWidget()
        self._conv_list.setMinimumWidth(200)
        splitter.addWidget(self._conv_list)

        # Right: thread view + compose panel
        right_pane = QWidget()
        right_layout = QVBoxLayout(right_pane)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self._thread_view = ThreadView()
        right_layout.addWidget(self._thread_view, stretch=1)

        self._compose = ComposePanel()
        right_layout.addWidget(self._compose)

        splitter.addWidget(right_pane)
        splitter.setSizes([300, 724])

        root_layout.addWidget(splitter, stretch=1)

        # Keep QShortcut as fallback for platform-native shortcut routing
        QShortcut(QKeySequence("Ctrl+1"), self).activated.connect(
            lambda: self._conv_list.setFocus(Qt.ShortcutFocusReason)
        )
        QShortcut(QKeySequence("Ctrl+N"), self).activated.connect(
            lambda: self._compose._input.setFocus(Qt.ShortcutFocusReason)
        )
        QShortcut(QKeySequence("F5"), self).activated.connect(self.refresh_requested.emit)
        QShortcut(QKeySequence("Ctrl+R"), self).activated.connect(self.refresh_requested.emit)

    def _wire(self) -> None:
        self._conv_list.conversation_selected.connect(self._on_conversation_selected)
        self._conv_list.focus_thread_requested.connect(self._compose._input.setFocus)
        self._compose.send_requested.connect(self._on_send)

    @property
    def conversation_list(self) -> ConversationListWidget:
        return self._conv_list

    @property
    def compose_panel(self) -> ComposePanel:
        return self._compose

    def _on_conversation_selected(self, conv_id: str) -> None:
        self.conversation_opened.emit(conv_id)
        sample_messages = [
            MessageData(BubbleType.INBOUND, "Hey, are you around later?", "Alice", "10:14"),
            MessageData(BubbleType.OUTBOUND, "Yeah, free after 6", "", "10:15"),
            MessageData(BubbleType.INBOUND, "Great, see you then!", "Alice", "10:15"),
            MessageData(BubbleType.BODY_UNAVAILABLE, "", "Bob", "10:20"),
            MessageData(BubbleType.GROUP_UNKNOWN_SENDER, "Can everyone make it?", "?", "10:22"),
        ]
        self._thread_view.load_thread("Alice", "+1 555-0100", sample_messages, "SMS")
        self._compose.set_compose_enabled(True)

    def _on_send(self, text: str) -> None:
        self.message_send_requested.emit(text)
        print(f"[stub] send: {text!r}")

    def _activate_and_focus(self, widget) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            QApplication.setActiveWindow(self)
        widget.setFocus()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        if key == Qt.Key.Key_1 and ctrl:
            self._activate_and_focus(self._conv_list)
        elif key == Qt.Key.Key_N and ctrl:
            self._activate_and_focus(self._compose._input)
        elif key == Qt.Key.Key_F5:
            self.refresh_requested.emit()
        elif key == Qt.Key.Key_R and ctrl:
            self.refresh_requested.emit()
        else:
            super().keyPressEvent(event)

    def _on_refresh(self) -> None:
        self.refresh_requested.emit()

    def _load_stub_data(self) -> None:
        """Populate with placeholder data so the UI is visible on first launch."""
        conversations = [
            ConversationData(
                id="c1",
                name="Alice",
                phone="+1 555-0100",
                preview="Yeah, free after 6",
                timestamp="10:15",
                unread=False,
            ),
            ConversationData(
                id="c2",
                name="Bob",
                phone="+1 555-0101",
                preview="Don't forget the meeting",
                timestamp="Yesterday",
                unread=True,
            ),
            ConversationData(
                id="c3",
                name="Family",
                phone="+1 555-0102",
                preview="Can everyone make it?",
                timestamp="Mon",
                unread=True,
                participant_count=4,
            ),
        ]
        self._conv_list.load_conversations(conversations)


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
