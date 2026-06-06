"""Main window: QMainWindow with title bar, QSplitter, and component wiring."""
from __future__ import annotations

import json
import os
import re
import sys
import warnings
from dataclasses import replace as dc_replace
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QKeyEvent, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from tincan_gui.avatar import _color_for_name
from tincan_gui.compose_panel import ComposePanel
from tincan_gui.conversation_list import ConversationData, ConversationListWidget
from tincan_gui.daemon_config import load_daemon_config
from tincan_gui.daemon_launcher import spawn_daemon
from tincan_gui.dbus_client import TincandClient
from tincan_gui.degradation_banners import (
    ANCSRepairBanner,
    ContactsEmptyBanner,
    StateABanner,
    StateBBanner,
    StateCBanner,
)
from tincan_gui.message_cache import MessageCache
from tincan_gui.notifications import DesktopNotifier
from tincan_gui.theme import is_dark_theme
from tincan_gui.thread_view import BubbleType, MessageData, ThreadView
from tincan_gui.tray import TrayIcon

_ASSETS = Path(__file__).parent / "assets"

_NON_DIGIT_RE = re.compile(r"\D")


def _is_dialable(s: str) -> bool:
    """Return True for 4-6 digit short codes or ≥7 digit phone numbers."""
    return len(_NON_DIGIT_RE.sub("", s)) >= 4


def _ts_display(raw: str) -> str:
    """Extract HH:MM from a MAP YYYYMMDDTHHMMSS timestamp; return raw[:5] for short strings."""
    if not raw:
        return ""
    t = raw.find("T")
    if t >= 0 and len(raw) >= t + 5:
        return f"{raw[t + 1:t + 3]}:{raw[t + 3:t + 5]}"
    return raw[:5]


def _same_conv(a: str, b: str) -> bool:
    """True when two conversation IDs refer to the same conversation.

    Normalises phone-shaped strings (strips non-digits, trims to 10 digits for
    US/CA) so that "+18157916347" and "8157916347" compare equal.  Returns False
    when either value is name-shaped (fewer than 7 digit chars) to avoid false
    matches between unrelated name-keyed threads.
    """
    if a == b:
        return True
    na = _NON_DIGIT_RE.sub("", a)
    nb = _NON_DIGIT_RE.sub("", b)
    if len(na) < 7 or len(nb) < 7:
        return False
    na = na[-10:] if len(na) > 10 else na
    nb = nb[-10:] if len(nb) > 10 else nb
    return na == nb


class TitleBar(QWidget):
    """Title bar (h=48, forest teal #0f4c3a): wordmark + gear button + connection status chip."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(48)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet("background-color: #0f4c3a;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)

        icon_label = QLabel()
        icon_label.setFixedSize(32, 32)
        icon_label.setAccessibleName("")
        icon_label.setStyleSheet("border: none; background: transparent;")
        screen = QApplication.primaryScreen()
        dpr = screen.devicePixelRatio() if screen else 1.0
        px = QPixmap(str(_ASSETS / "tincan-icon.png")).scaled(
            int(32 * dpr), int(32 * dpr), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        px.setDevicePixelRatio(dpr)
        icon_label.setPixmap(px)
        layout.addWidget(icon_label)
        layout.addSpacing(8)

        wordmark = QLabel("tincan")
        wm_font = QFont()
        wm_font.setPointSize(22)
        wm_font.setBold(True)
        wordmark.setFont(wm_font)
        wordmark.setStyleSheet("color: #ccfbf1;")
        layout.addWidget(wordmark)

        layout.addStretch()

        self._gear_btn = QToolButton()
        self._gear_btn.setText("⚙")
        self._gear_btn.setFixedSize(32, 32)
        self._gear_btn.setToolTip("Settings")
        self._gear_btn.setAccessibleName("Settings")
        self._gear_btn.setStyleSheet(
            "QToolButton { color: #ccfbf1; font-size: 22px; border: none;"
            " background: transparent; }"
            " QToolButton:hover { background: rgba(255,255,255,0.2); border-radius: 4px; }"
        )
        layout.addWidget(self._gear_btn)

        layout.addSpacing(8)

        self._status_chip = QLabel("○ Disconnected")
        chip_font = QFont()
        chip_font.setPointSize(12)
        self._status_chip.setFont(chip_font)
        self._status_chip.setStyleSheet("color: #fca5a5;")
        self._status_chip.setAccessibleName("Connection status: Disconnected")
        layout.addWidget(self._status_chip)

    @property
    def gear_button(self) -> QToolButton:
        return self._gear_btn

    @property
    def status_chip(self) -> QLabel:
        """Expose status chip label for accessibility tests."""
        return self._status_chip

    def set_connected(self, device_name: str) -> None:
        self._status_chip.setText(f"● Connected — {device_name}")
        self._status_chip.setStyleSheet("color: #86efac;")
        self._status_chip.setAccessibleName("Connection status: Connected")

    def set_connected_limited(self, device_name: str) -> None:
        self._status_chip.setText(f"● Connected (limited) — {device_name}")
        self._status_chip.setStyleSheet("color: #fbbf24;")
        self._status_chip.setAccessibleName(
            "Connection status: Connected, limited — push notifications unavailable"
        )

    def set_disconnected(self) -> None:
        self._status_chip.setText("○ Disconnected")
        self._status_chip.setStyleSheet("color: #fca5a5;")
        self._status_chip.setAccessibleName("Connection status: Disconnected")


class _ChipWidget(QWidget):
    """Single contact chip (26px height) with × dismiss button."""

    dismissed = Signal(str)  # emits phone

    def __init__(self, display: str, phone: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._phone = phone
        color = _color_for_name(display)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 4, 2)
        layout.setSpacing(4)

        label = QLabel(display)
        label_font = QFont()
        label_font.setPointSize(11)
        label.setFont(label_font)
        label.setStyleSheet("color: #ffffff; background: transparent;")
        layout.addWidget(label)

        dismiss = QPushButton("×")
        dismiss.setFlat(True)
        dismiss.setStyleSheet("color: #ffffff; border: none; font-size: 14px;")
        dismiss.setFixedSize(18, 18)
        dismiss.clicked.connect(lambda: self.dismissed.emit(self._phone))
        layout.addWidget(dismiss)

        self.setStyleSheet(
            f"background: {color}; border-radius: 4px;"
        )
        self.setFixedHeight(26)
        self.setAccessibleName(f"{display}, press Delete to remove")

    @property
    def phone(self) -> str:
        return self._phone


class NewConversationDialog(QDialog):
    """Multi-chip compose dialog for starting a new 1:1 or group conversation."""

    def __init__(
        self,
        contacts: list[dict],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Conversation")
        self.setMinimumWidth(480)
        self.setStyleSheet("background: #18181b; color: #f4f4f5;")
        self._contacts = contacts
        self._chips: list[_ChipWidget] = []
        self._build()
        self._refresh_autocomplete("")

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        to_label = QLabel("To:")
        to_font = QFont()
        to_font.setPointSize(12)
        to_label.setFont(to_font)
        layout.addWidget(to_label)

        # Chip area + text input inside a scroll area
        self._chip_scroll = QScrollArea()
        self._chip_scroll.setWidgetResizable(True)
        self._chip_scroll.setFixedHeight(80)
        self._chip_scroll.setStyleSheet(
            "QScrollArea { border: 2px solid #3b82f6; border-radius: 4px; background: #18181b; }"
        )

        self._chip_container = QWidget()
        self._chip_flow = QHBoxLayout(self._chip_container)
        self._chip_flow.setContentsMargins(4, 4, 4, 4)
        self._chip_flow.setSpacing(4)
        self._chip_flow.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        self._text_input = QLineEdit()
        self._text_input.setPlaceholderText("Add recipient…")
        self._text_input.setStyleSheet(
            "QLineEdit { background: transparent; border: none; color: #f4f4f5; font-size: 13px; }"
        )
        self._text_input.textChanged.connect(self._refresh_autocomplete)
        self._chip_flow.addWidget(self._text_input, stretch=1)

        self._chip_scroll.setWidget(self._chip_container)
        layout.addWidget(self._chip_scroll)

        # Autocomplete list
        self._autocomplete = QListWidget()
        self._autocomplete.setStyleSheet(
            "QListWidget { background: #27272a; color: #f4f4f5; border: none; }"
            "QListWidget::item:selected { background: #3f3f46; }"
            "QListWidget::item:hover { background: #3f3f46; }"
        )
        self._autocomplete.setMaximumHeight(120)
        self._autocomplete.itemActivated.connect(self._on_autocomplete_selected)
        self._autocomplete.setAccessibleName("Autocomplete suggestions")
        layout.addWidget(self._autocomplete)
        self._text_input.installEventFilter(self)
        self._autocomplete.installEventFilter(self)

        # Buttons
        self._btn_box = QDialogButtonBox()
        self._cancel_btn = self._btn_box.addButton("Cancel", QDialogButtonBox.RejectRole)
        self._ok_btn = self._btn_box.addButton("Start", QDialogButtonBox.AcceptRole)
        self._ok_btn.setEnabled(False)
        self._ok_btn.setStyleSheet(
            "QPushButton { background: #0d9488; color: #ffffff;"
            " border-radius: 4px; padding: 4px 12px; }"
        )
        self._btn_box.accepted.connect(self.accept)
        self._btn_box.rejected.connect(self.reject)
        layout.addWidget(self._btn_box)

    def eventFilter(self, obj, event) -> bool:
        if obj is self._text_input and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            text = self._text_input.text().strip()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab, Qt.Key.Key_Comma):
                if text:
                    self._add_chip(text, text)
                    self._text_input.clear()
                    return True
                elif self._autocomplete.currentItem():
                    self._on_autocomplete_selected(self._autocomplete.currentItem())
                    return True
            elif key == Qt.Key.Key_Backspace and not text and self._chips:
                self._remove_chip(self._chips[-1].phone)
                return True
            elif key == Qt.Key.Key_Down:
                self._autocomplete.setFocus()
                if self._autocomplete.count():
                    self._autocomplete.setCurrentRow(0)
                return True
        if obj is self._autocomplete and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                item = self._autocomplete.currentItem()
                if item:
                    self._on_autocomplete_selected(item)
                    self._text_input.setFocus()
                    return True
            elif event.key() == Qt.Key.Key_Up:
                if self._autocomplete.currentRow() == 0:
                    self._text_input.setFocus()
                    return True
        return super().eventFilter(obj, event)

    def _add_chip(self, display: str, phone: str) -> None:
        chipped_phones = {c.phone for c in self._chips}
        if phone in chipped_phones:
            return
        chip = _ChipWidget(display, phone)
        chip.dismissed.connect(self._remove_chip)
        self._chips.append(chip)
        idx = self._chip_flow.count() - 1  # insert before text input stretch
        self._chip_flow.insertWidget(idx, chip)
        self._update_ok_button()
        self._refresh_autocomplete(self._text_input.text())

    def _remove_chip(self, phone: str) -> None:
        for chip in list(self._chips):
            if chip.phone == phone:
                self._chips.remove(chip)
                self._chip_flow.removeWidget(chip)
                chip.deleteLater()
                break
        self._update_ok_button()
        self._refresh_autocomplete(self._text_input.text())

    def _refresh_autocomplete(self, query: str) -> None:
        self._autocomplete.clear()
        chipped_phones = {c.phone for c in self._chips}
        query = query.strip().lower()
        for contact in self._contacts:
            name = str(contact.get("name", ""))
            phone = str(contact.get("phone", ""))
            if phone in chipped_phones:
                continue
            if query and query not in name.lower() and query not in phone.lower():
                continue
            display = f"{name}  {phone}" if name else phone
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, {"name": name, "phone": phone})
            if phone in chipped_phones:
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            self._autocomplete.addItem(item)
        count = self._autocomplete.count()
        self._autocomplete.setVisible(count > 0)
        self._autocomplete.setAccessibleName(f"{count} suggestions")

    def _on_autocomplete_selected(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.UserRole)
        if data:
            display = data.get("name") or data.get("phone", "")
            phone = data.get("phone", "")
            if phone:
                self._add_chip(display, phone)
                self._text_input.clear()

    def _update_ok_button(self) -> None:
        n = len(self._chips)
        self._ok_btn.setEnabled(n >= 1)
        if n >= 2:
            self._ok_btn.setText("Start Group")
        else:
            self._ok_btn.setText("Start")

    def selected_phones(self) -> list[str]:
        return [c.phone for c in self._chips]


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
        self._current_phone: str = ""     # phone for the open conversation
        self._current_phone_dialable: bool = True  # False when phone is unresolvable name
        self._connected_device: str = ""  # human-readable name or address of connected BT device
        self._daemon_spawn_attempted: bool = False
        self._messages_ok: bool = False   # True when daemon reports messages capability
        self._repair_notified: bool = False  # rate-limit: only one FALLBACK notification
        self._conversations_by_id: dict[str, ConversationData] = {}
        self._pending_sends: set[tuple[str, str]] = set()  # (conv_id, body) awaiting ack
        self._sent_bodies: dict[str, set[str]] = {}  # conv_id → {body}; suppresses MAP poll echoes
        self._self_echo_guard: set[tuple[str, str]] = set()  # suppress MAP echo of self-sends
        self._sent_cache: dict[str, list[MessageData]] = {}  # conv_id → sent msgs; thread render
        self._failed_sends: dict[str, set[str]] = {}  # phone → {body}; failed state survives reload
        self._msg_cache = MessageCache()
        self._notifier = DesktopNotifier(
            on_action_invoked=self._on_notification_clicked,
            on_mark_read=self._on_notification_mark_read,
        )
        self._build()
        self._wire()
        self._dbus_client = TincandClient(self)
        self._tray = TrayIcon(self)
        self._wire_dbus()
        self._sync_daemon_state()
        self._sync_compose_state()  # ensure button reflects initial state (no daemon)

    def _build(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Title bar
        self._title_bar = TitleBar()
        root_layout.addWidget(self._title_bar)

        # Degradation banners (hidden until daemon signals arrive)
        self._banner_a = StateABanner()
        self._banner_a.hide()
        root_layout.addWidget(self._banner_a)

        self._banner_b = StateBBanner()
        self._banner_b.hide()
        self._banner_b.show_me_how_clicked.connect(self._on_show_notifications_help)
        root_layout.addWidget(self._banner_b)

        # ANCSRepairBanner between State B and State C (tincan-5mze)
        self._banner_ancs_repair = ANCSRepairBanner()
        self._banner_ancs_repair.hide()
        root_layout.addWidget(self._banner_ancs_repair)

        self._banner_c = StateCBanner()
        self._banner_c.hide()
        self._banner_c.refresh_clicked.connect(self.refresh_requested.emit)
        root_layout.addWidget(self._banner_c)

        # Contacts-empty hint (tincan-d3xw)
        self._banner_contacts_empty = ContactsEmptyBanner()
        self._banner_contacts_empty.hide()
        root_layout.addWidget(self._banner_contacts_empty)

        # Splitter: left sidebar + right content
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet(
            "QSplitter::handle { background: #3f3f46; }" if is_dark_theme()
            else "QSplitter::handle { background: #e5e7eb; }"
        )

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
        QShortcut(QKeySequence("Alt+,"), self).activated.connect(self._open_settings)
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self._thread_view.show_search)

    def _wire(self) -> None:
        self._conv_list.conversation_selected.connect(self._on_conversation_selected)
        self._conv_list.focus_thread_requested.connect(self._compose._input.setFocus)
        self._conv_list.compose_new_requested.connect(self._on_compose_new)
        self._conv_list.refresh_requested.connect(self.refresh_requested.emit)
        self._compose.send_requested.connect(self._on_send)
        self._title_bar.gear_button.clicked.connect(self._open_settings)
        self._banner_a.reconnect_clicked.connect(self._on_reconnect_clicked)
        self._banner_ancs_repair.reconnect_clicked.connect(self._open_pairing_wizard)

    def _wire_dbus(self) -> None:
        c = self._dbus_client
        c.connected.connect(self._on_daemon_connected)
        c.disconnected.connect(self._on_daemon_disconnected)
        c.capability_changed.connect(self._on_capability_changed)
        c.message_received.connect(self._on_message_received)
        c.app_notification_received.connect(self._notifier.dispatch_app_notification)
        c.conversation_updated.connect(self._on_conversation_updated)
        c.contact_photo_received.connect(self._on_contact_photo_received)
        c.message_send_accepted.connect(self._on_send_accepted)
        c.message_send_failed.connect(self._on_send_failed)
        self.refresh_requested.connect(self._load_conversations)

    def _maybe_spawn_daemon(self) -> None:
        """Spawn tincand if config has a device and no spawn has been attempted yet."""
        if self._daemon_spawn_attempted:
            return
        self._daemon_spawn_attempted = True
        config = load_daemon_config()
        if not config.device:
            return
        spawn_daemon(config.backend, config.device)
        QTimer.singleShot(2000, self._sync_daemon_state)

    def _sync_daemon_state(self) -> None:
        """Query tincand at startup and sync UI to current daemon state."""
        status = self._dbus_client.get_status()
        if not status:
            self._maybe_spawn_daemon()
            return
        if status.get("connected"):
            addr = str(status.get("device_name") or status.get("device_address") or "")
            self._connected_device = addr
            self._title_bar.set_connected(addr)
            self._banner_a.hide()
            caps = status.get("capabilities") or {}
            self._apply_capabilities(caps)
            self._tray.set_connected(True)
            self._load_conversations()
        else:
            self._title_bar.set_disconnected()
            self._banner_a.show()

    def _sync_compose_state(self) -> None:
        """Gate compose on messaging availability AND conversation selection.

        States:
        - messaging OK + conversation selected + phone resolvable → fully enabled
        - messaging OK + conversation selected + phone unresolvable → disabled
          with "phone number unavailable" (name-keyed thread, tincan-6b9m)
        - messaging unavailable + conversation selected → fully disabled
          (set_compose_enabled so Enter key also blocked; BLOCKER-2)
        - no conversation selected (regardless of messaging) → button-only
          disable so keyboard navigation stays accessible (a11y)
        """
        if self._messages_ok and self._current_phone:
            if self._current_phone_dialable:
                self._compose.set_compose_enabled(True)
            else:
                self._compose.set_compose_enabled(
                    False, "phone number unavailable for this thread"
                )
        elif not self._messages_ok and self._current_phone:
            self._compose.set_compose_enabled(False, "messaging unavailable")
        else:
            btn = self._compose.send_button
            btn.setEnabled(False)
            reason = "no conversation selected"
            btn.setToolTip(f"Sending unavailable — {reason}")
            btn.setAccessibleName(f"Send unavailable — {reason}")

    def _apply_capabilities(self, caps: dict) -> None:
        # tincan-40c/tincan-5mze: all keys always present; default False (not
        # capable) when a key is absent so degradation banners show conservatively.
        messages_ok = bool(caps.get("messages", False))
        self._messages_ok = messages_ok
        self._banner_b.setVisible(not messages_ok)
        self._sync_compose_state()
        ancs_ok = bool(caps.get("ancs", False))
        ancs_needs_repair = bool(caps.get("ancs_needs_repair", False))
        self._update_ancs_repair_banner(ancs_needs_repair)
        self._update_state_c_banner(ancs_ok, ancs_needs_repair)
        # Contacts-empty hint (tincan-d3xw)
        contacts_empty = bool(caps.get("contacts_empty", False))
        self._banner_contacts_empty.setVisible(contacts_empty)

    def _update_ancs_repair_banner(self, needs_repair: bool) -> None:
        """Show/hide ANCSRepairBanner; fire FALLBACK notification on first entry."""
        self._banner_ancs_repair.setVisible(needs_repair)
        if needs_repair:
            if hasattr(self, "_tray"):
                self._tray.set_repair_needed(True)
            if not self._repair_notified:
                self._repair_notified = True
                self._notifier.dispatch_repair(on_reconnect=self._open_pairing_wizard)
        else:
            if hasattr(self, "_tray"):
                self._tray.set_repair_needed(False)
            self._repair_notified = False

    def _update_state_c_banner(self, ancs_ok: bool, ancs_needs_repair: bool = False) -> None:
        """Show/hide State C banner; update chip to amber when ANCS limited (tincan-om9).

        State C is hidden when ancs_needs_repair=True — ANCSRepairBanner takes precedence.
        Co-exists with State B — messages gate takes priority for compose state.
        Chip color only changes when the device is actually connected.
        """
        show_c = not ancs_ok and not ancs_needs_repair
        self._banner_c.setVisible(show_c)
        if self._connected_device:
            # Chip reflects messaging capability (primary), not ANCS notifications
            # (secondary). ANCS unavailability is surfaced via the State C banner.
            if self._messages_ok:
                self._title_bar.set_connected(self._connected_device)
            else:
                self._title_bar.set_connected_limited(self._connected_device)

    @property
    def conversation_list(self) -> ConversationListWidget:
        return self._conv_list

    @property
    def compose_panel(self) -> ComposePanel:
        return self._compose

    def _on_conversation_selected(self, conv_id: str) -> None:
        self.conversation_opened.emit(conv_id)
        conv_data = self._conversations_by_id.get(conv_id)
        if conv_data:
            self._current_phone = conv_data.phone
            # Only flag as undialable when we KNOW the phone from a populated conv.
            # Unknown convs (conv_data is None) stay dialable so compose stays open.
            self._current_phone_dialable = _is_dialable(conv_data.phone)
        else:
            self._current_phone = conv_id
            self._current_phone_dialable = True
        name = conv_data.name if conv_data else conv_id

        # Set group mode on thread + compose before loading messages.
        is_group = bool(conv_data and conv_data.is_group)
        participants: list[str] = (
            list(conv_data.participants) if conv_data and conv_data.is_group else []
        )
        self._thread_view.set_group_mode(is_group, participants)
        self._compose.set_group_mode(is_group)

        # Show cached messages immediately (no empty-thread flash), then merge
        # MAP results in the next event-loop tick once the D-Bus round trip completes.
        cache_key = self._current_phone or conv_id
        # Migrate any messages written under the old (wrong) conv_id key.
        if conv_id and conv_id != cache_key:
            self._msg_cache.merge_into(cache_key, conv_id)
        cached: list[MessageData] = [
            self._cache_msg_to_data(c) for c in self._msg_cache.get_messages(cache_key)
        ]
        cached += self._sent_cache.get(cache_key, [])
        cached.sort(key=lambda m: m.sort_key or m.timestamp)
        self._compose.hide_send_error()
        self._thread_view.load_thread(
            name, conv_id, cached, "SMS",
            failures=self._failed_sends.get(cache_key, set()),
        )
        self._sync_compose_state()
        self._tray.reset_unread()
        self._dbus_client.mark_conversation_read(conv_id)
        self._dbus_client.fetch_contact_photo(conv_id)
        QTimer.singleShot(0, lambda: self._load_thread_messages(conv_id, name))

    def _load_thread_messages(self, conv_id: str, name: str) -> None:
        """Populate the thread view with messages (deferred from _on_conversation_selected)."""
        # Guard: user may have switched conversations during the deferred tick.
        if self._current_phone and not _same_conv(conv_id, self._current_phone):
            return
        raw_msgs = self._dbus_client.get_messages(conv_id)
        messages: list[MessageData] = [self._msg_dict_to_data(m) for m in raw_msgs]
        cache_key = self._current_phone or conv_id
        # Migrate any messages written under the old (wrong) conv_id key.
        if conv_id and conv_id != cache_key:
            self._msg_cache.merge_into(cache_key, conv_id)

        # Dedup key: prefer sort_key (MAP timestamp); fall back to body for keyless msgs.
        def _dk(m: MessageData) -> tuple:
            return (m.bubble_type, m.sort_key) if m.sort_key else (m.bubble_type, m.body)

        seen: set[tuple] = {_dk(m) for m in messages}
        extras: list[MessageData] = []

        # Persistent cache — inbound + outbound from all sessions.
        for m in (self._cache_msg_to_data(c) for c in self._msg_cache.get_messages(cache_key)):
            k = _dk(m)
            if k not in seen:
                extras.append(m)
                seen.add(k)

        # In-session sent cache — fast path; covers sends from this session not yet
        # visible in MAP results (iOS sent folder is always empty).
        for m in self._sent_cache.get(cache_key, []):
            k = _dk(m)
            if k not in seen:
                extras.append(m)
                seen.add(k)

        if extras:
            messages = sorted(messages + extras, key=lambda m: m.sort_key or m.timestamp)
        self._thread_view.load_thread(
            name, conv_id, messages, "SMS",
            failures=self._failed_sends.get(cache_key, set()),
        )

    def _on_daemon_connected(self, device_address: str) -> None:
        status = self._dbus_client.get_status()
        if status:
            caps = status.get("capabilities") or {}
            name = str(status.get("device_name") or device_address)
        else:
            # Daemon just connected but GetStatus() is transiently unavailable;
            # assume all capabilities OK rather than showing degradation banners.
            caps = {"messages": True, "contacts": True, "ancs": True}
            name = str(device_address)
        self._connected_device = name
        self._title_bar.set_connected(name)
        self._banner_a.hide()
        self._apply_capabilities(caps)
        self._tray.set_connected(True)
        self._load_conversations()

    def _on_daemon_disconnected(self) -> None:
        self._connected_device = ""
        self._messages_ok = False
        self._sent_bodies.clear()
        self._self_echo_guard.clear()
        self._sent_cache.clear()
        self._failed_sends.clear()
        self._title_bar.set_disconnected()
        self._banner_a.show()
        self._banner_b.hide()
        self._banner_ancs_repair.hide()
        self._banner_c.hide()
        self._banner_contacts_empty.hide()
        self._compose.set_compose_enabled(False, "not connected")
        self._tray.set_connected(False)

    def _on_reconnect_clicked(self) -> None:
        self._dbus_client.request_reconnect()

    def _on_capability_changed(self, feature: str, available: bool) -> None:
        """Handle a CapabilityChanged signal by re-fetching full status.

        Re-fetching GetStatus() avoids stale views when multiple capability
        changes arrive in rapid succession.  When the daemon is unreachable
        (e.g., in tests), synthesize a safe fallback dict from defaults-True
        then override with the reported feature value.
        """
        status = self._dbus_client.get_status()
        if status:
            caps = status.get("capabilities") or {}
        else:
            caps = {"messages": True, "contacts": True, "ancs": True}
            caps[feature] = available
        self._apply_capabilities(caps)
        if feature == "contacts" and available:
            self._load_conversations()

    def _on_message_received(self, message: dict) -> None:
        self._notifier.dispatch(message)
        # Tray badge: only for genuinely-new inbound unread (not historical replay)
        if (str(message.get("direction", "")) == "inbound"
                and str(message.get("status", "")) in ("unread", "new")):
            self._tray.increment_unread()
        conv_id = str(message.get("conversation_id", ""))
        if conv_id and not self._current_phone:
            return  # no conversation selected; don't append routed messages to thread view
        if self._current_phone and conv_id and not _same_conv(conv_id, self._current_phone):
            return  # message is for a different conversation; notification already sent
        direction = str(message.get("direction", "inbound"))
        body = str(message.get("body", ""))
        # Suppress daemon echo for messages already shown as optimistic bubbles.
        # Use _same_conv for pending/sent lookups: daemon may normalize the phone
        # differently (e.g. "+15550100" → "5550100") producing a key mismatch.
        if direction == "outbound" and any(
            _same_conv(k, conv_id) and b == body for k, b in self._pending_sends
        ):
            return
        # Suppress MAP-poll duplicates (poll re-emits the sent message from 'sent'
        # folder after _pending_sends is cleared; _sent_bodies persists longer).
        if direction == "outbound" and any(
            _same_conv(k, conv_id) and body in bodies
            for k, bodies in self._sent_bodies.items()
        ):
            return
        # iOS MAP delivers messages sent to yourself back to the inbox as "inbound".
        # Use the echo arrival as a delivery confirmation, then fall through so it
        # renders as its own inbound bubble and gets written to the message cache.
        # Suppressing the echo here was tincan-wqrq8 regression: self-convos only
        # showed one side (tincan-tqsre).
        if direction == "inbound":
            _echo_key = next(
                (
                    (k, b)
                    for k, b in self._self_echo_guard
                    if _same_conv(k, conv_id) and b == body
                ),
                None,
            )
            if _echo_key is not None:
                self._self_echo_guard.discard(_echo_key)
                self._thread_view.mark_last_send_delivered()
        sender = str(message.get("sender", "") or message.get("from", ""))
        raw_ts = str(message.get("timestamp", ""))
        timestamp = _ts_display(raw_ts)
        raw_att = message.get("attachments", [])
        if isinstance(raw_att, list):
            attachments = raw_att
        else:
            try:
                attachments = json.loads(str(raw_att))
                if not isinstance(attachments, list):
                    attachments = []
            except (ValueError, TypeError):
                attachments = []

        if not body and not attachments:
            bubble_type = BubbleType.BODY_UNAVAILABLE
        elif direction == "inbound":
            bubble_type = BubbleType.INBOUND
        else:
            bubble_type = BubbleType.OUTBOUND

        group_hint = bool(message.get("group_hint", False))
        if group_hint and bubble_type == BubbleType.INBOUND:
            bubble_type = BubbleType.GROUP_UNKNOWN_SENDER

        self._thread_view.append_message(
            MessageData(
                bubble_type, body, sender, timestamp,
                sort_key=raw_ts, attachments=attachments,
            )
        )
        # Use current_phone-first to match the read key in _load_thread_messages;
        # conv_id-first caused miskeyed writes that read operations never found.
        cache_id = self._current_phone or conv_id
        if body and cache_id and bubble_type != BubbleType.BODY_UNAVAILABLE:
            self._msg_cache.add_message(cache_id, direction, body, sender, raw_ts, raw_ts)

    def _on_conversation_updated(self, conversation: dict) -> None:
        conv_id = str(conversation.get("id", ""))
        if not conv_id:
            return
        if conv_id not in self._conversations_by_id:
            # New conversation arrived — reload the full list from the daemon
            self._load_conversations()
            return
        unread_count = int(conversation.get("unread_count", 0))
        data = ConversationData(
            id=conv_id,
            name=str(conversation.get("display_name", conv_id)),
            phone=conv_id,
            preview=str(conversation.get("last_message_preview", "")),
            timestamp=_ts_display(str(conversation.get("last_message_at", ""))),
            unread=unread_count > 0,
            unread_count=unread_count,
            preview_direction=str(conversation.get("last_message_direction", "")),
        )
        self._conversations_by_id[conv_id] = data
        self._conv_list.update_item(conv_id, data)
        if _same_conv(conv_id, self._current_phone):
            self._thread_view._header.update_contact(data.name, data.phone)

    def _on_contact_photo_received(self, conv_id: str, photo: bytes) -> None:
        if photo:
            self._conv_list.set_conversation_photo(conv_id, photo)
            if self._current_phone and _same_conv(conv_id, self._current_phone):
                self._thread_view.set_header_photo(photo)

    def _on_notification_clicked(self, conversation_id: str) -> None:
        """Raise window and select conversation when user clicks a notification."""
        self.show()
        self.raise_()
        self.activateWindow()
        if conversation_id:
            self._conv_list.select_conversation(conversation_id)

    def _on_notification_mark_read(self, conversation_id: str) -> None:
        """Mark conversation as read when user activates the mark-read notification action."""
        if conversation_id:
            self._dbus_client.mark_conversation_read(conversation_id)

    def _open_pairing_wizard(self) -> None:
        from tincan_gui.pairing_wizard import PairingWizard
        from tincand.pairing import PairingOrchestrator
        orch = PairingOrchestrator(on_state_change=lambda state, reason=None: None)
        wizard = PairingWizard(orchestrator=orch, parent=self)
        wizard.exec()

    def _open_settings(self) -> None:
        from tincan_gui.settings_dialog import SettingsDialog
        dlg = SettingsDialog(self, client=self._dbus_client)
        if hasattr(self, "_tray"):
            dlg.notifications_toggled.connect(self._tray.sync_notifications_action)
        dlg.exec()

    def _on_show_notifications_help(self) -> None:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            "Enable Show Notifications",
            "On your iPhone:\n"
            "  Settings → Bluetooth → [your Mac/PC] → Show Notifications\n\n"
            "Toggle it on, then wait a few seconds for tincan to reconnect.",
        )

    def _on_send(self, text: str) -> None:
        self.message_send_requested.emit(text)
        self._compose.hide_send_error()
        if not self._current_phone or not self._current_phone_dialable:
            self._compose.show_send_error(text)
            return
        phone = self._current_phone
        # In-flight guard: prevent double-submit while a send of same (phone, text) is pending.
        if (phone, text) in self._pending_sends:
            return
        now = datetime.now()
        ts = now.strftime("%H:%M")
        sent_msg = MessageData(
            BubbleType.OUTBOUND, text, "", ts, sort_key=now.strftime("%Y%m%dT%H%M%S")
        )
        self._thread_view.append_message(sent_msg)
        # Cache sent message for thread reload (iOS MAP sent folder returns 0 messages).
        self._sent_cache.setdefault(phone, []).append(sent_msg)
        self._msg_cache.add_message(
            phone, "outbound", text, "", sent_msg.sort_key, sent_msg.sort_key
        )
        self._pending_sends.add((phone, text))
        # Guard self-conversations: MAP re-delivers self-sent messages to inbox as inbound.
        self._self_echo_guard.add((phone, text))
        QTimer.singleShot(10000, lambda: self._self_echo_guard.discard((phone, text)))
        # Update conversation-list preview immediately. iOS MAP sent folder never populates
        # last_message_preview for outbound messages, so we must push it from the GUI.
        _preview_conv = next(
            (c for c in self._conversations_by_id.values()
             if c.phone == phone or _same_conv(c.id, phone)),
            None,
        )
        if _preview_conv is not None:
            _updated = dc_replace(
                _preview_conv, preview=text, timestamp=ts, preview_direction="outbound",
                unread=False, unread_count=0,
            )
            self._conversations_by_id[_preview_conv.id] = _updated
            self._conv_list.update_item(_preview_conv.id, _updated)
        # Non-blocking send — outcome arrives via _on_send_accepted / _on_send_failed.
        self._dbus_client.send_message_async(phone, text)

    def _on_send_accepted(self, to: str, body: str, message_id: str) -> None:
        # Defer cleanup so daemon's MessageReceived echo arrives first and is suppressed.
        QTimer.singleShot(0, lambda: self._pending_sends.discard((to, body)))
        self._failed_sends.get(to, set()).discard(body)
        if message_id:
            # Track sent body so MAP-poll echoes (which arrive after _pending_sends
            # is cleared) are suppressed without showing a duplicate bubble.
            self._sent_bodies.setdefault(to, set()).add(body)

    def _on_send_failed(self, to: str, body: str) -> None:
        QTimer.singleShot(0, lambda: self._pending_sends.discard((to, body)))
        self._failed_sends.setdefault(to, set()).add(body)
        self._thread_view.mark_last_send_failed()
        self._compose.show_send_error(body)

    def _on_compose_new(self) -> None:
        """Open the multi-chip New Conversation dialog."""
        contacts = self._gather_autocomplete_contacts()
        dlg = NewConversationDialog(contacts, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        phones = dlg.selected_phones()
        if not phones:
            return
        if len(phones) == 1:
            phone = phones[0]
            self._current_phone = phone
            self._current_phone_dialable = _is_dialable(phone)
            self._thread_view.set_group_mode(False)
            self._compose.set_group_mode(False)
            self._thread_view.load_thread(phone, phone, [], "SMS")
            self._sync_compose_state()
            self._compose._input.setFocus()
        else:
            conv_id = self._dbus_client.send_message_to_recipients(phones, "")
            if not conv_id:
                conv_id = phones[0]
            self._current_phone = conv_id
            self._current_phone_dialable = True
            self._thread_view.set_group_mode(True, phones)
            self._compose.set_group_mode(True)
            self._thread_view.load_thread(conv_id, conv_id, [], "MMS")
            self._sync_compose_state()
            self._compose._input.setFocus()

    def _gather_autocomplete_contacts(self) -> list[dict]:
        """Build autocomplete list from PBAP contacts + conversation history."""
        contacts: list[dict] = []
        seen: set[str] = set()
        # PBAP contacts first (highest-quality names)
        for c in self._dbus_client.list_contacts():
            phone = str(c.get("phone", ""))
            name = str(c.get("name", ""))
            if phone and phone not in seen:
                seen.add(phone)
                contacts.append({"name": name, "phone": phone})
        # Fill in from conversation history for any phone not already covered
        for conv in self._dbus_client.list_conversations():
            phone = str(conv.get("id", ""))
            name = str(conv.get("display_name", phone))
            if phone and phone not in seen:
                seen.add(phone)
                contacts.append({"name": name if name != phone else "", "phone": phone})
        return contacts

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

    def closeEvent(self, event) -> None:
        """Hide to tray or quit on window close, per behavior/close_to_tray setting."""
        from tincan_gui._settings import app_settings  # noqa: PLC0415
        s = app_settings()
        s.sync()  # flush before exit so prefs survive crashes/kills
        if hasattr(self, "_tray") and self._tray.isSystemTrayAvailable():
            close_to_tray = s.value("behavior/close_to_tray", True, type=bool)
            if close_to_tray:
                event.ignore()
                self.hide()
            else:
                QApplication.quit()
        else:
            super().closeEvent(event)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if (
            event.type() == QEvent.Type.ActivationChange
            and self.isActiveWindow()
            and hasattr(self, "_tray")
        ):
            self._tray.reset_unread()

    def _on_refresh(self) -> None:
        self.refresh_requested.emit()

    def _load_conversations(self) -> None:
        """Load conversation list from daemon; show empty state when unavailable."""
        self._conv_list.set_refresh_loading(True)
        raw = self._dbus_client.list_conversations()
        conversations = []
        self._conversations_by_id = {}
        for c in raw:
            ts = _ts_display(str(c.get("last_message_at", "")))
            unread = int(c.get("unread_count", 0))
            data = ConversationData(
                id=str(c.get("id", "")),
                name=str(c.get("display_name", c.get("id", ""))),
                phone=str(c.get("send_target", "") or c.get("id", "")),
                preview=str(c.get("last_message_preview", "")),
                timestamp=ts,
                unread=unread > 0,
                unread_count=unread,
                preview_direction=str(c.get("last_message_direction", "")),
            )
            conversations.append(data)
            self._conversations_by_id[data.id] = data
        self._conv_list.load_conversations(conversations)
        self._conv_list.set_refresh_loading(False)
        if conversations and not self._current_phone:
            first_id = conversations[0].id
            QTimer.singleShot(0, lambda: self._conv_list.select_conversation(first_id))

    def _cache_msg_to_data(self, m: dict) -> MessageData:
        direction = m.get("direction", "inbound")
        body = str(m.get("body", ""))
        sender = str(m.get("sender", ""))
        sort_key = str(m.get("sort_key") or m.get("timestamp", ""))
        ts = _ts_display(str(m.get("timestamp", "")))
        try:
            attachments = json.loads(str(m.get("attachments", "[]")))
        except (ValueError, TypeError):
            attachments = []
        if direction == "outbound":
            btype = BubbleType.OUTBOUND
        elif body or attachments:
            btype = BubbleType.INBOUND
        else:
            btype = BubbleType.BODY_UNAVAILABLE
        return MessageData(btype, body, sender, ts, sort_key=sort_key, attachments=attachments)

    def _msg_dict_to_data(self, msg: dict) -> MessageData:
        direction = str(msg.get("direction", "inbound"))
        body = str(msg.get("body", ""))
        sender = str(msg.get("from", ""))
        raw_ts = str(msg.get("timestamp", ""))
        ts = _ts_display(raw_ts)
        raw_att = msg.get("attachments", [])
        if isinstance(raw_att, list):
            attachments = raw_att
        else:
            try:
                attachments = json.loads(str(raw_att))
                if not isinstance(attachments, list):
                    attachments = []
            except (ValueError, TypeError):
                attachments = []
        if direction == "outbound":
            btype = BubbleType.OUTBOUND
        elif body or attachments:
            btype = BubbleType.INBOUND
        else:
            btype = BubbleType.BODY_UNAVAILABLE
        return MessageData(btype, body, sender, ts, sort_key=raw_ts, attachments=attachments)


def main() -> None:
    if os.environ.get("TINCAN_DEBUG"):
        from tincan_gui.debug_log import install, install_excepthook  # noqa: PLC0415
        install()
        install_excepthook()
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
