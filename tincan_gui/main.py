"""Main window: QMainWindow with title bar, QSplitter, and component wiring."""
from __future__ import annotations

import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QEvent, QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QFont, QKeyEvent, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QSizePolicy,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from tincan_gui.compose_panel import ComposePanel
from tincan_gui.conversation_list import ConversationData, ConversationListWidget
from tincan_gui.dbus_client import TincandClient
from tincan_gui.degradation_banners import (
    ANCSRepairBanner,
    StateABanner,
    StateBBanner,
    StateCBanner,
)
from tincan_gui.notifications import DesktopNotifier
from tincan_gui.theme import is_dark_theme
from tincan_gui.thread_view import BubbleType, MessageData, ThreadView
from tincan_gui.tray import TrayIcon

_ASSETS = Path(__file__).parent / "assets"


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
        dpr = QApplication.primaryScreen().devicePixelRatio() if QApplication.primaryScreen() else 1.0
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


class _SendWorker(QObject):
    """Worker that calls SendMessage on a background thread to avoid freezing the GUI."""

    done = Signal(str, str, str)  # (phone, text, message_id_or_empty)

    def __init__(self, phone: str, text: str, parent=None) -> None:
        super().__init__(parent)
        self._phone = phone
        self._text = text

    @Slot()
    def run(self) -> None:
        try:
            import dbus as _dbus
            bus = _dbus.SessionBus()
            obj = bus.get_object("im.tincan.Daemon", "/im/tincan")
            iface = _dbus.Interface(obj, "im.tincan.Messages")
            result = str(iface.SendMessage(self._phone, self._text))
        except Exception:
            result = ""
        self.done.emit(self._phone, self._text, result)


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
        self._connected_device: str = ""  # human-readable name or address of connected BT device
        self._messages_ok: bool = False   # True when daemon reports messages capability
        self._repair_notified: bool = False  # rate-limit: only one FALLBACK notification
        self._conversations_by_id: dict[str, ConversationData] = {}
        self._pending_sends: set[tuple[str, str]] = set()  # (conv_id, body) awaiting ack
        self._notifier = DesktopNotifier(on_action_invoked=self._on_notification_clicked)
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

    def _wire(self) -> None:
        self._conv_list.conversation_selected.connect(self._on_conversation_selected)
        self._conv_list.focus_thread_requested.connect(self._compose._input.setFocus)
        self._conv_list.compose_new_requested.connect(self._on_compose_new)
        self._conv_list.refresh_requested.connect(self.refresh_requested.emit)
        self._compose.send_requested.connect(self._on_send)
        self._title_bar.gear_button.clicked.connect(self._open_settings)
        self._banner_ancs_repair.reconnect_clicked.connect(self._open_pairing_wizard)

    def _wire_dbus(self) -> None:
        c = self._dbus_client
        c.connected.connect(self._on_daemon_connected)
        c.disconnected.connect(self._on_daemon_disconnected)
        c.capability_changed.connect(self._on_capability_changed)
        c.message_received.connect(self._on_message_received)
        c.conversation_updated.connect(self._on_conversation_updated)
        c.contact_photo_received.connect(self._on_contact_photo_received)
        self.refresh_requested.connect(self._load_conversations)

    def _sync_daemon_state(self) -> None:
        """Query tincand at startup and sync UI to current daemon state."""
        status = self._dbus_client.get_status()
        if not status:
            return  # daemon not running — UI stays in default disconnected state
        if status.get("connected"):
            addr = str(status.get("device_name") or status.get("device_address") or "")
            self._title_bar.set_connected(addr)
            self._banner_a.hide()
            caps = status.get("capabilities") or {}
            self._apply_capabilities(caps)
            self._load_conversations()
        else:
            self._title_bar.set_disconnected()

    def _sync_compose_state(self) -> None:
        """Gate compose on messaging availability AND conversation selection.

        Three states:
        - messaging OK + conversation selected → fully enabled
        - messaging unavailable + conversation selected → fully disabled
          (set_compose_enabled so Enter key also blocked; BLOCKER-2)
        - no conversation selected (regardless of messaging) → button-only
          disable so keyboard navigation stays accessible (a11y)
        """
        if self._messages_ok and self._current_phone:
            self._compose.set_compose_enabled(True)
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
            if ancs_ok:
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
        self._current_phone = conv_data.phone if conv_data else conv_id
        name = conv_data.name if conv_data else conv_id
        raw_msgs = self._dbus_client.get_messages(conv_id)
        messages = [self._msg_dict_to_data(m) for m in raw_msgs]
        self._thread_view.load_thread(name, conv_id, messages, "SMS")
        self._sync_compose_state()
        self._tray.reset_unread()
        self._dbus_client.fetch_contact_photo(conv_id)

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
        self._title_bar.set_disconnected()
        self._banner_a.show()
        self._banner_b.hide()
        self._banner_ancs_repair.hide()
        self._banner_c.hide()
        self._compose.set_compose_enabled(False, "not connected")
        self._tray.set_connected(False)

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
        if self._current_phone and conv_id and conv_id != self._current_phone:
            return  # message is for a different conversation; notification already sent
        direction = str(message.get("direction", "inbound"))
        body = str(message.get("body", ""))
        # Suppress daemon echo for messages already shown as optimistic bubbles.
        if direction == "outbound" and (conv_id, body) in self._pending_sends:
            return
        sender = str(message.get("sender", "") or message.get("from", ""))
        timestamp = str(message.get("timestamp", ""))[:5]  # HH:MM

        if not body:
            bubble_type = BubbleType.BODY_UNAVAILABLE
        elif direction == "inbound":
            bubble_type = BubbleType.INBOUND
        else:
            bubble_type = BubbleType.OUTBOUND

        group_hint = bool(message.get("group_hint", False))
        if group_hint and bubble_type == BubbleType.INBOUND:
            bubble_type = BubbleType.GROUP_UNKNOWN_SENDER

        self._thread_view.append_message(MessageData(bubble_type, body, sender, timestamp))

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
            timestamp=str(conversation.get("last_message_at", ""))[:5],
            unread=unread_count > 0,
            unread_count=unread_count,
            preview_direction=str(conversation.get("last_message_direction", "")),
        )
        self._conv_list.update_item(conv_id, data)

    def _on_contact_photo_received(self, conv_id: str, photo: bytes) -> None:
        if photo:
            self._conv_list.set_conversation_photo(conv_id, photo)

    def _on_notification_clicked(self, conversation_id: str) -> None:
        """Raise window and select conversation when user clicks a notification."""
        self.show()
        self.raise_()
        self.activateWindow()
        if conversation_id:
            self._conv_list.select_conversation(conversation_id)

    def _open_pairing_wizard(self) -> None:
        from tincan_gui.pairing_wizard import PairingWizard
        from tincand.pairing import PairingOrchestrator
        orch = PairingOrchestrator(on_state_change=lambda state, reason=None: None)
        wizard = PairingWizard(orchestrator=orch, parent=self)
        wizard.exec()

    def _open_settings(self) -> None:
        from tincan_gui.settings_dialog import SettingsDialog
        dlg = SettingsDialog(self)
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

    def _on_compose_new(self) -> None:
        """Open a dialog asking for a recipient phone number and start a new thread."""
        phone, ok = QInputDialog.getText(
            self,
            "New Conversation",
            "Recipient phone number:",
        )
        if not ok or not phone.strip():
            return
        phone = phone.strip()
        self._current_phone = phone
        self._thread_view.load_thread(phone, phone, [], "SMS")
        self._sync_compose_state()
        self._compose._input.setFocus()

    def _on_send(self, text: str) -> None:
        self.message_send_requested.emit(text)
        self._compose.hide_send_error()
        if not self._current_phone:
            return
        phone = self._current_phone
        ts = datetime.now(tz=timezone.utc).strftime("%H:%M")
        self._thread_view.append_message(MessageData(BubbleType.OUTBOUND, text, "", ts))
        self._pending_sends.add((phone, text))
        worker = _SendWorker(phone, text)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(self._on_send_done)
        worker.done.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        worker.done.connect(worker.deleteLater)
        thread.start()

    def _on_send_done(self, phone: str, text: str, message_id: str) -> None:
        self._pending_sends.discard((phone, text))
        if not message_id:
            self._compose.show_send_error(text)

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
        """Hide to tray on window close; only quit via tray menu or QApplication.quit."""
        if hasattr(self, "_tray") and self._tray.isSystemTrayAvailable():
            event.ignore()
            self.hide()
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
            ts = str(c.get("last_message_at", ""))[:5]
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

    def _msg_dict_to_data(self, msg: dict) -> MessageData:
        direction = str(msg.get("direction", "inbound"))
        body = str(msg.get("body", ""))
        sender = str(msg.get("from", ""))
        ts = str(msg.get("timestamp", ""))[:5]
        if direction == "outbound":
            btype = BubbleType.OUTBOUND
        elif body:
            btype = BubbleType.INBOUND
        else:
            btype = BubbleType.BODY_UNAVAILABLE
        return MessageData(btype, body, sender, ts)


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
