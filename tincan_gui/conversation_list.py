"""Conversation list sidebar: ConversationItem, ConversationListWidget."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


@dataclass
class ConversationData:
    id: str
    name: str
    phone: str
    preview: str
    timestamp: str
    unread: bool = False
    participant_count: int = 1


class ConversationItem(QWidget):
    """Single conversation row (h=72)."""

    activated = Signal(str)   # emits conversation id

    _SELECTED_BG = "#dbeafe"
    _SELECTED_BORDER = "#bfdbfe"
    _UNREAD_DOT_COLOR = "#1d4ed8"

    def __init__(self, data: ConversationData, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._data = data
        self._selected = False
        self.setFixedHeight(72)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFocusPolicy(Qt.StrongFocus)
        self._build()
        self._update_accessible()

    def _build(self) -> None:
        outer = QHBoxLayout(self)
        outer.setContentsMargins(12, 0, 12, 0)
        outer.setSpacing(8)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        # Top row: name + timestamp
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)

        name = self._data.name
        if self._data.participant_count > 1:
            name = f"{name} [{self._data.participant_count}]"

        self._name_label = QLabel(name)
        name_font = QFont()
        name_font.setPointSize(14)
        name_font.setBold(True)
        self._name_label.setFont(name_font)
        top_row.addWidget(self._name_label, stretch=1)

        ts_label = QLabel(self._data.timestamp)
        ts_font = QFont()
        ts_font.setPointSize(11)
        ts_label.setFont(ts_font)
        ts_label.setStyleSheet("color: #6b7280;")
        top_row.addWidget(ts_label)

        text_col.addLayout(top_row)

        # Preview row
        preview = self._data.preview
        if len(preview) > 36:
            preview = preview[:36] + "…"
        self._preview_label = QLabel(preview)
        prev_font = QFont()
        prev_font.setPointSize(12)
        self._preview_label.setFont(prev_font)
        self._preview_label.setStyleSheet("color: #6b7280;")
        text_col.addWidget(self._preview_label)

        outer.addLayout(text_col, stretch=1)

        # Unread dot (right side)
        self._dot = QLabel()
        self._dot.setFixedSize(10, 10)
        self._dot.setStyleSheet(
            f"background-color: {self._UNREAD_DOT_COLOR}; border-radius: 5px;"
        )
        self._dot.setVisible(self._data.unread)
        outer.addWidget(self._dot, alignment=Qt.AlignVCenter)

        self._apply_unread_style()

    def _apply_unread_style(self) -> None:
        if self._data.unread:
            f = self._name_label.font()
            f.setBold(True)
            self._name_label.setFont(f)
        else:
            f = self._name_label.font()
            f.setBold(False)
            self._name_label.setFont(f)

    def _update_accessible(self) -> None:
        self.setAccessibleName(
            f"Conversation with {self._data.name}, "
            f"last message {self._data.preview[:36]}, "
            f"{self._data.timestamp}"
        )
        if self._data.unread:
            self.setAccessibleDescription("Unread")
        else:
            self.setAccessibleDescription("")

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        if selected:
            self.setStyleSheet(
                f"background-color: {self._SELECTED_BG}; "
                f"border: 1px solid {self._SELECTED_BORDER};"
            )
        else:
            self.setStyleSheet("")

    def mousePressEvent(self, event) -> None:
        self.activated.emit(self._data.id)
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Space):
            self.activated.emit(self._data.id)
        else:
            super().keyPressEvent(event)

    @property
    def conversation_id(self) -> str:
        return self._data.id


class ConversationListWidget(QWidget):
    """Left sidebar: header, scrollable list of ConversationItems, footer."""

    conversation_selected = Signal(str)    # conversation id
    focus_thread_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._items: list[ConversationItem] = []
        self._selected_index: int = -1
        self._badge_dismissed = False
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setFixedHeight(40)
        header.setStyleSheet("background: #f9fafb; border-bottom: 1px solid #e5e7eb;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 0, 12, 0)

        conversations_label = QLabel("Conversations")
        conv_font = QFont()
        conv_font.setPointSize(13)
        conversations_label.setFont(conv_font)
        conversations_label.setStyleSheet("color: #374151;")
        header_layout.addWidget(conversations_label, stretch=1)

        self._badge = QLabel("10 max")
        badge_font = QFont()
        badge_font.setPointSize(11)
        self._badge.setFont(badge_font)
        self._badge.setStyleSheet(
            "color: #9ca3af; background: #f3f4f6; border-radius: 4px; padding: 0 4px;"
        )
        self._badge.setVisible(not self._badge_dismissed)
        header_layout.addWidget(self._badge)

        self._dismiss_btn = QLabel("×")
        self._dismiss_btn.setStyleSheet("color: #9ca3af; padding: 0 4px; cursor: pointer;")
        self._dismiss_btn.setVisible(not self._badge_dismissed)
        self._dismiss_btn.mousePressEvent = lambda _: self._dismiss_badge()
        header_layout.addWidget(self._dismiss_btn)

        layout.addWidget(header)

        # Scrollable list area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)

        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(0)
        self._list_layout.addStretch()

        scroll.setWidget(self._list_container)
        layout.addWidget(scroll, stretch=1)

        # Footer
        footer = QLabel("↑ recent window only · not full history")
        footer_font = QFont()
        footer_font.setPointSize(10)
        footer.setFont(footer_font)
        footer.setStyleSheet(
            "color: #9ca3af; background: #f9fafb; "
            "border-top: 1px solid #e5e7eb; padding: 4px 12px;"
        )
        footer.setAlignment(Qt.AlignCenter)
        layout.addWidget(footer)

    def _dismiss_badge(self) -> None:
        self._badge_dismissed = True
        self._badge.setVisible(False)
        self._dismiss_btn.setVisible(False)

    def load_conversations(self, conversations: list[ConversationData]) -> None:
        # Remove old items
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._items.clear()
        self._selected_index = -1

        for data in conversations:
            widget = ConversationItem(data)
            widget.activated.connect(self._on_item_activated)
            self._list_layout.insertWidget(self._list_layout.count() - 1, widget)
            self._items.append(widget)

    def _on_item_activated(self, conv_id: str) -> None:
        for i, item in enumerate(self._items):
            if item.conversation_id == conv_id:
                self._select_index(i)
                self.conversation_selected.emit(conv_id)
                self.focus_thread_requested.emit()
                break

    def _select_index(self, index: int) -> None:
        if self._selected_index >= 0 and self._selected_index < len(self._items):
            self._items[self._selected_index].set_selected(False)
        self._selected_index = index
        if 0 <= index < len(self._items):
            self._items[index].set_selected(True)
            self._items[index].setFocus()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Down:
            next_idx = min(self._selected_index + 1, len(self._items) - 1)
            self._select_index(next_idx)
        elif event.key() == Qt.Key_Up:
            prev_idx = max(self._selected_index - 1, 0)
            self._select_index(prev_idx)
        elif event.key() in (Qt.Key_Return, Qt.Key_Space):
            if 0 <= self._selected_index < len(self._items):
                item = self._items[self._selected_index]
                self.conversation_selected.emit(item.conversation_id)
                self.focus_thread_requested.emit()
        elif event.key() == Qt.Key_Tab:
            self.focus_thread_requested.emit()
        else:
            super().keyPressEvent(event)
