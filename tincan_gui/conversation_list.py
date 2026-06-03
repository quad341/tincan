"""Conversation list sidebar: ConversationItem, ConversationListWidget."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAccessible, QFont, QKeyEvent
from PySide6.QtWidgets import (
    QAccessibleWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from tincan_gui.avatar import AvatarWidget
from tincan_gui.theme import is_dark_theme


class _SearchLineEdit(QLineEdit):
    """QLineEdit that clears itself on Escape."""

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.clear()
        else:
            super().keyPressEvent(event)


@dataclass
class ConversationData:
    id: str
    name: str
    phone: str
    preview: str
    timestamp: str
    unread: bool = False
    participant_count: int = 1
    unread_count: int = 0  # tincan-bxs: from daemon Conversation dict
    preview_direction: str = ""  # 'outbound' → show 'You: …' prefix in preview


class ConversationItem(QWidget):
    """Single conversation row (h=72)."""

    activated = Signal(str)   # emits conversation id

    _SELECTED_BG = "#bfdbfe"
    _SELECTED_BORDER = "#93c5fd"
    _UNREAD_DOT_COLOR = "#1d4ed8"
    _SELECTED_NAME_COLOR = "#1e40af"        # blue-800, 4.7:1 on #dbeafe — WCAG AA
    _SELECTED_MUTED_COLOR = "#374151"       # gray-700, 5.4:1 on #dbeafe — WCAG AA
    _SELECTED_BG_DARK = "#1e3a5f"
    _SELECTED_BORDER_DARK = "#1d4ed8"
    _SELECTED_NAME_COLOR_DARK = "#93c5fd"   # blue-300 on #1e3a5f — WCAG AA
    _SELECTED_MUTED_COLOR_DARK = "#a1a1aa"  # zinc-400 on #1e3a5f — WCAG AA
    _CARD_BG = "#ffffff"
    _CARD_BORDER = "#e5e7eb"
    _CARD_BG_DARK = "#18181b"
    _CARD_BORDER_DARK = "#3f3f46"

    def __init__(self, data: ConversationData, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._data = data
        self._selected = False
        self._dark = is_dark_theme()
        self.setFixedHeight(72)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFocusPolicy(Qt.StrongFocus)
        self._build()
        self._update_accessible()
        # When used as a top-level widget (e.g. in unit tests without a parent window),
        # show() is needed so isVisible() on children reflects setVisible() state rather
        # than the unshown parent tree.
        if not self.parent():
            self.show()

    def _build(self) -> None:
        outer = QHBoxLayout(self)
        outer.setContentsMargins(6, 0, 6, 0)
        outer.setSpacing(6)

        # QFrame card wraps avatar + text columns
        frame = QFrame()
        bg = self._CARD_BG_DARK if self._dark else self._CARD_BG
        border = self._CARD_BORDER_DARK if self._dark else self._CARD_BORDER
        frame.setStyleSheet(
            f"QFrame {{ background: {bg}; border: 1px solid {border}; border-radius: 4px; }}"
        )
        # Pass mouse events through so ConversationItem.mousePressEvent fires on card clicks.
        frame.setAttribute(Qt.WA_TransparentForMouseEvents)
        frame_layout = QHBoxLayout(frame)
        frame_layout.setContentsMargins(8, 8, 8, 8)
        frame_layout.setSpacing(8)

        # Avatar (40×40 circle — initials until PBAP photo set)
        self._avatar = AvatarWidget(self._data.name)
        frame_layout.addWidget(self._avatar, alignment=Qt.AlignVCenter)

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
        name_font.setBold(False)
        self._name_label.setFont(name_font)
        self._name_label.setStyleSheet(
            "color: #f4f4f5;" if self._dark else "color: #111827;"
        )
        top_row.addWidget(self._name_label, stretch=1)

        self._ts_label = QLabel(self._data.timestamp)
        ts_font = QFont()
        ts_font.setPointSize(11)
        self._ts_label.setFont(ts_font)
        self._ts_label.setStyleSheet(
            "color: #a1a1aa;" if self._dark else "color: #6b7280;"
        )
        top_row.addWidget(self._ts_label)

        text_col.addLayout(top_row)

        # Preview row (tincan-33k)
        self._preview_label = QLabel()
        prev_font = QFont()
        prev_font.setPointSize(12)
        self._preview_label.setFont(prev_font)
        text_col.addWidget(self._preview_label)

        frame_layout.addLayout(text_col, stretch=1)
        outer.addWidget(frame, stretch=1)

        # Unread indicator (right side): dot + optional badge (tincan-yq1)
        self._dot = QLabel()
        self._dot.setFixedSize(10, 10)
        self._dot.setStyleSheet(
            f"background-color: {self._UNREAD_DOT_COLOR}; border-radius: 5px;"
        )
        outer.addWidget(self._dot, alignment=Qt.AlignVCenter)

        self._badge_label = QLabel()
        badge_font = QFont()
        badge_font.setPointSize(10)
        badge_font.setBold(True)
        self._badge_label.setFont(badge_font)
        self._badge_label.setStyleSheet(
            f"color: #ffffff; background-color: {self._UNREAD_DOT_COLOR};"
            " border-radius: 8px; padding: 0 5px;"
        )
        outer.addWidget(self._badge_label, alignment=Qt.AlignVCenter)

        self._apply_unread_style()
        self._apply_preview()

    def _apply_unread_style(self) -> None:
        count = self._data.unread_count
        is_unread = count > 0 or self._data.unread
        f = self._name_label.font()
        f.setBold(is_unread)
        self._name_label.setFont(f)
        self._dot.setVisible(is_unread)
        if count >= 10:
            self._badge_label.setText("9+")
            self._badge_label.setVisible(True)
        else:
            self._badge_label.setVisible(False)

    def _apply_preview(self) -> None:
        raw = self._data.preview
        if self._selected:
            preview_color = (
                self._SELECTED_MUTED_COLOR_DARK if self._dark else self._SELECTED_MUTED_COLOR
            )
            no_preview_color = preview_color
        else:
            preview_color = "#a1a1aa" if self._dark else "#6b7280"
            no_preview_color = "#71717a" if self._dark else "#9ca3af"
        if raw:
            direction = getattr(self._data, "preview_direction", "")
            if direction == "outbound":
                body = raw[:30] + "…" if len(raw) > 30 else raw
                display = f"You: {body}"
            else:
                display = raw[:36] + "…" if len(raw) > 36 else raw
            self._preview_label.setText(display)
            self._preview_label.setStyleSheet(f"color: {preview_color};")
            f = self._preview_label.font()
            f.setItalic(False)
            self._preview_label.setFont(f)
            self._preview_label.setAccessibleName(raw)
        else:
            self._preview_label.setText("—")
            self._preview_label.setStyleSheet(f"color: {no_preview_color};")
            f = self._preview_label.font()
            f.setItalic(True)
            self._preview_label.setFont(f)
            self._preview_label.setAccessibleName("No preview available")

    def _update_accessible(self) -> None:
        full_preview = self._data.preview or ""
        base = (
            f"Conversation with {self._data.name}, "
            f"last message: {full_preview}, "
            f"{self._data.timestamp}"
        )
        count = self._data.unread_count
        if count > 0:
            badge = "9+" if count >= 10 else str(count)
            self.setAccessibleName(f"{base}, Unread: {badge}")
        else:
            self.setAccessibleName(base)
        # tincan-298: use "Unread: N" format for unread_count; fall back to plain
        # "Unread" for legacy data using the unread bool flag (unread_count==0).
        if count >= 10:
            self.setAccessibleDescription("Unread: 9+")
        elif count > 0:
            self.setAccessibleDescription(f"Unread: {count}")
        elif self._data.unread:
            self.setAccessibleDescription("Unread")
        else:
            self.setAccessibleDescription("")

    def update_data(self, data: ConversationData) -> None:
        """Update this item in-place from new ConversationData (tincan-yq1)."""
        self._data = data
        self._ts_label.setText(data.timestamp)
        self._apply_unread_style()
        self._apply_preview()
        self._update_accessible()

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        if selected:
            sel_bg = self._SELECTED_BG_DARK if self._dark else self._SELECTED_BG
            sel_border = self._SELECTED_BORDER_DARK if self._dark else self._SELECTED_BORDER
            sel_name = self._SELECTED_NAME_COLOR_DARK if self._dark else self._SELECTED_NAME_COLOR
            sel_muted = (
                self._SELECTED_MUTED_COLOR_DARK if self._dark else self._SELECTED_MUTED_COLOR
            )
            self.setStyleSheet(
                f"ConversationItem {{"
                f" background-color: {sel_bg}; border: 1px solid {sel_border};"
                " border-radius: 8px; margin: 4px 6px;"
                " } QLabel { background: transparent; }"
            )
            self._name_label.setStyleSheet(f"color: {sel_name};")
            self._ts_label.setStyleSheet(f"color: {sel_muted};")
            self._apply_preview()
        else:
            self.setStyleSheet("QLabel { background: transparent; }")
            self._name_label.setStyleSheet(
                "color: #f4f4f5;" if self._dark else "color: #111827;"
            )
            self._ts_label.setStyleSheet(
                "color: #a1a1aa;" if self._dark else "color: #6b7280;"
            )
            self._apply_preview()

    def set_read(self) -> None:
        """Clear unread state immediately when a conversation is opened."""
        self._data = replace(self._data, unread=False, unread_count=0)
        self._apply_unread_style()

    def mousePressEvent(self, event) -> None:
        self.activated.emit(self._data.id)
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Space):
            self.activated.emit(self._data.id)
        else:
            super().keyPressEvent(event)

    def set_photo(self, data: bytes) -> None:
        """Set PBAP contact photo (raw bytes). Called asynchronously when photo arrives."""
        self._avatar.set_photo(data)

    def name_label_color(self) -> str:
        """Return the hex color applied to the name label (used by a11y tests)."""
        style = self._name_label.styleSheet()
        for part in style.split(";"):
            if "color" in part:
                return part.split(":")[1].strip()
        return "#111827"

    def timestamp_label_color(self) -> str:
        """Return the hex color applied to the timestamp label (used by a11y tests)."""
        style = self._ts_label.styleSheet()
        for part in style.split(";"):
            if "color" in part:
                return part.split(":")[1].strip()
        return "#6b7280"

    @property
    def conversation_id(self) -> str:
        return self._data.id


class ConversationListWidget(QWidget):
    """Left sidebar: header, scrollable list of ConversationItems, footer."""

    conversation_selected = Signal(str)    # conversation id
    focus_thread_requested = Signal()
    compose_new_requested = Signal()       # user clicked "+" compose-new button
    refresh_requested = Signal()           # user clicked the ↻ refresh button

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self._items: list[ConversationItem] = []
        self._selected_index: int = -1
        self._pending_updates: dict[str, ConversationData] = {}
        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.setInterval(200)
        self._update_timer.timeout.connect(self._flush_updates)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setFixedHeight(40)
        _dark = is_dark_theme()
        header.setStyleSheet(
            "background: #27272a; border-bottom: 1px solid #3f3f46;" if _dark
            else "background: #f9fafb; border-bottom: 1px solid #e5e7eb;"
        )
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 0, 8, 0)

        conversations_label = QLabel("Conversations")
        conv_font = QFont()
        conv_font.setPointSize(13)
        conversations_label.setFont(conv_font)
        conversations_label.setStyleSheet(
            "color: #e4e4e7;" if _dark else "color: #374151;"
        )
        header_layout.addWidget(conversations_label, stretch=1)

        _btn_hover = "#3f3f46" if _dark else "#e5e7eb"
        _btn_color = "#f4f4f5" if _dark else "#374151"
        _btn_style = (
            f"QToolButton {{ font-size: 18px; font-weight: bold; color: {_btn_color};"
            " border: none; background: transparent; border-radius: 4px; }"
            f" QToolButton:hover {{ background: {_btn_hover}; }}"
            " QToolButton:disabled { opacity: 0.4; }"
        )

        self._refresh_btn = QToolButton()
        self._refresh_btn.setText("↻")
        self._refresh_btn.setFixedSize(28, 28)
        self._refresh_btn.setToolTip("Refresh conversations")
        self._refresh_btn.setAccessibleName("Refresh conversations")
        self._refresh_btn.setStyleSheet(_btn_style)
        self._refresh_btn.clicked.connect(self.refresh_requested.emit)
        header_layout.addWidget(self._refresh_btn)

        self._compose_btn = QToolButton()
        self._compose_btn.setText("+")
        self._compose_btn.setFixedSize(28, 28)
        self._compose_btn.setToolTip("New conversation")
        self._compose_btn.setAccessibleName("New conversation")
        self._compose_btn.setStyleSheet(_btn_style)
        self._compose_btn.clicked.connect(self.compose_new_requested.emit)
        header_layout.addWidget(self._compose_btn)

        layout.addWidget(header)

        # Search / filter input (clears on Escape via _SearchLineEdit subclass)
        self._search = _SearchLineEdit()
        self._search.setFixedHeight(32)
        self._search.setPlaceholderText("Filter conversations…")
        self._search.setAccessibleName("Filter conversations")
        if _dark:
            self._search.setStyleSheet(
                "QLineEdit { border: none; border-bottom: 1px solid #3f3f46;"
                " padding: 0 12px; background: #27272a; color: #f4f4f5; }"
            )
        else:
            self._search.setStyleSheet(
                "QLineEdit { border: none; border-bottom: 1px solid #e5e7eb;"
                " padding: 0 12px; background: #f9fafb; }"
            )
        self._search.textChanged.connect(self._on_filter_changed)
        layout.addWidget(self._search)

        # No-results empty state (shown when filter has no matches)
        self._no_results = QLabel("No results")
        nr_font = QFont()
        nr_font.setPointSize(12)
        self._no_results.setFont(nr_font)
        self._no_results.setStyleSheet(
            "color: #71717a; padding: 12px;" if _dark else "color: #9ca3af; padding: 12px;"
        )
        self._no_results.setAlignment(Qt.AlignCenter)
        self._no_results.setVisible(False)
        layout.addWidget(self._no_results)

        # Scrollable list area (stored as instance var to prevent Python GC of the wrapper)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.NoFrame)

        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(0)
        self._list_layout.addStretch()

        self._scroll.setWidget(self._list_container)
        layout.addWidget(self._scroll, stretch=1)

        # Footer
        footer = QLabel("↑ recent window only · not full history")
        footer_font = QFont()
        footer_font.setPointSize(10)
        footer.setFont(footer_font)
        if _dark:
            footer.setStyleSheet(
                "color: #a1a1aa; background: #27272a; "
                "border-top: 1px solid #3f3f46; padding: 4px 12px;"
            )
        else:
            footer.setStyleSheet(
                "color: #9ca3af; background: #f9fafb; "
                "border-top: 1px solid #e5e7eb; padding: 4px 12px;"
            )
        footer.setAlignment(Qt.AlignCenter)
        layout.addWidget(footer)

    def load_conversations(self, conversations: list[ConversationData]) -> None:
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._items.clear()
        self._item_data_list: list[ConversationData] = []
        self._selected_index = -1

        for data in conversations:
            widget = ConversationItem(data)
            widget.activated.connect(self._on_item_activated)
            self._list_layout.insertWidget(self._list_layout.count() - 1, widget)
            self._items.append(widget)
            self._item_data_list.append(data)

        self._on_filter_changed(self._search.text())
        # When running as a top-level widget (e.g. in unit tests without a parent window),
        # show() is needed so that isVisible() on child items reflects filter state rather
        # than always returning False due to the parent tree being unshown.
        if not self.parent():
            self.show()

    def _on_filter_changed(self, text: str) -> None:
        query = text.strip().lower()
        visible_count = 0
        for i, (widget, data) in enumerate(
            zip(self._items, getattr(self, "_item_data_list", []))
        ):
            match = (
                not query
                or query in data.name.lower()
                or query in data.preview.lower()
            )
            widget.setVisible(match)
            if match:
                visible_count += 1
        self._no_results.setVisible(visible_count == 0 and bool(query))

    def clear_filter(self) -> None:
        """Clear search input and show all rows."""
        self._search.clear()

    def select_conversation(self, conv_id: str) -> None:
        """Programmatically select and open a conversation by ID."""
        self._on_item_activated(conv_id)

    def _on_item_activated(self, conv_id: str) -> None:
        for i, item in enumerate(self._items):
            if item.conversation_id == conv_id:
                self._select_index(i)
                item.set_read()
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
        if event.key() == Qt.Key.Key_Down:
            next_idx = min(self._selected_index + 1, len(self._items) - 1)
            self._select_index(next_idx)
        elif event.key() == Qt.Key.Key_Up:
            prev_idx = max(self._selected_index - 1, 0)
            self._select_index(prev_idx)
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Space):
            if 0 <= self._selected_index < len(self._items):
                item = self._items[self._selected_index]
                self.conversation_selected.emit(item.conversation_id)
                self.focus_thread_requested.emit()
        elif event.key() == Qt.Key.Key_Tab:
            self.focus_thread_requested.emit()
        else:
            super().keyPressEvent(event)

    def update_item(self, conv_id: str, data: ConversationData) -> None:
        """Queue an in-place update for a single item; 200ms debounce (tincan-yq1)."""
        self._pending_updates[conv_id] = data
        if not self._update_timer.isActive():
            self._update_timer.start()

    def _flush_updates(self) -> None:
        updates = self._pending_updates.copy()
        self._pending_updates.clear()
        for conv_id, data in updates.items():
            for item in self._items:
                if item.conversation_id == conv_id:
                    item.update_data(data)
                    break

    def select_index(self, index: int) -> None:
        """Public API for tests: select conversation at index."""
        self._select_index(index)

    def current_index(self) -> int:
        """Public API for tests: return the currently selected index."""
        return self._selected_index

    def set_refresh_loading(self, loading: bool) -> None:
        """Disable/re-enable the refresh button and show ↻/⌛ text."""
        self._refresh_btn.setEnabled(not loading)
        self._refresh_btn.setText("⌛" if loading else "↻")

    def set_conversation_photo(self, conv_id: str, photo: bytes) -> None:
        """Route a contact photo to the matching ConversationItem."""
        for item in self._items:
            if item.conversation_id == conv_id:
                item.set_photo(photo)
                break


# ---------------------------------------------------------------------------
# Accessible role factory — ConversationItem → ListItem
# ---------------------------------------------------------------------------

def _conversation_list_factory(classname: str, obj) -> Optional[QAccessibleWidget]:
    if isinstance(obj, ConversationItem):
        return QAccessibleWidget(obj, QAccessible.Role.ListItem)
    return None


QAccessible.installFactory(_conversation_list_factory)
