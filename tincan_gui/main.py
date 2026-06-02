"""Main window: QMainWindow with title bar, QSplitter, and component wiring."""
from __future__ import annotations

import sys
import warnings
from typing import Optional

from PySide6.QtCore import QEvent, Qt, Signal
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
from tincan_gui.dbus_client import TincandClient
from tincan_gui.degradation_banners import StateABanner, StateBBanner, StateCBanner
from tincan_gui.thread_view import BubbleType, MessageData, ThreadView
from tincan_gui.tray import TrayIcon


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
        self._connected_device: str = ""  # address of the connected BT device
        self._build()
        self._wire()
        self._load_stub_data()
        self._dbus_client = TincandClient(self)
        self._tray = TrayIcon(self)
        self._wire_dbus()
        self._sync_daemon_state()

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

        self._banner_c = StateCBanner()
        self._banner_c.hide()
        self._banner_c.refresh_clicked.connect(self.refresh_requested.emit)
        root_layout.addWidget(self._banner_c)

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

    def _wire_dbus(self) -> None:
        c = self._dbus_client
        c.connected.connect(self._on_daemon_connected)
        c.disconnected.connect(self._on_daemon_disconnected)
        c.capability_changed.connect(self._on_capability_changed)
        c.message_received.connect(self._on_message_received)
        c.conversation_updated.connect(self._on_conversation_updated)
        # Tray: badge on incoming message, reset on focus / conversation open
        c.message_received.connect(lambda _: self._tray.increment_unread())

    def _sync_daemon_state(self) -> None:
        """Query tincand at startup and sync UI to current daemon state."""
        status = self._dbus_client.get_status()
        if not status:
            return  # daemon not running — UI stays in default disconnected state
        if status.get("connected"):
            addr = str(status.get("device_address") or "")
            self._title_bar.set_connected(addr)
            self._banner_a.hide()
            caps = status.get("capabilities") or {}
            self._apply_capabilities(caps)
        else:
            self._title_bar.set_disconnected()

    def _apply_capabilities(self, caps: dict) -> None:
        # tincan-40c guarantees all three keys always present; default False (not
        # capable) when a key is absent so degradation banners show conservatively.
        messages_ok = bool(caps.get("messages", False))
        self._banner_b.setVisible(not messages_ok)
        if messages_ok:
            self._compose.set_compose_enabled(True)
        else:
            self._compose.set_compose_enabled(False, "messaging unavailable")
        ancs_ok = bool(caps.get("ancs", False))
        self._update_state_c_banner(ancs_ok)

    def _update_state_c_banner(self, ancs_ok: bool) -> None:
        """Show/hide State C banner; update chip to amber when ANCS limited (tincan-om9).

        Co-exists with State B — messages gate takes priority for compose state.
        Chip color only changes when the device is actually connected.
        """
        self._banner_c.setVisible(not ancs_ok)
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
        self._current_phone = conv_id  # conv_id is the normalized phone / address key
        status = self._dbus_client.get_status()
        if status and status.get("connected"):
            # Daemon running — load real thread (not yet implemented: requires GetMessages)
            # Fall through to stub load so the UI is not blank
            pass
        sample_messages = [
            MessageData(BubbleType.INBOUND, "Hey, are you around later?", "Alice", "10:14"),
            MessageData(BubbleType.OUTBOUND, "Yeah, free after 6", "", "10:15"),
            MessageData(BubbleType.INBOUND, "Great, see you then!", "Alice", "10:15"),
            MessageData(BubbleType.BODY_UNAVAILABLE, "", "Bob", "10:20"),
            MessageData(BubbleType.GROUP_UNKNOWN_SENDER, "Can everyone make it?", "?", "10:22"),
        ]
        self._thread_view.load_thread("Alice", "+1 555-0100", sample_messages, "SMS")
        self._compose.set_compose_enabled(True)
        self._tray.reset_unread()

    def _on_daemon_connected(self, device_address: str) -> None:
        self._connected_device = str(device_address)
        self._title_bar.set_connected(device_address)
        self._banner_a.hide()
        status = self._dbus_client.get_status()
        if status:
            caps = status.get("capabilities") or {}
        else:
            # Daemon just connected but GetStatus() is transiently unavailable;
            # assume all capabilities OK rather than showing degradation banners.
            caps = {"messages": True, "contacts": True, "ancs": True}
        self._apply_capabilities(caps)
        self._tray.set_connected(True)

    def _on_daemon_disconnected(self) -> None:
        self._connected_device = ""
        self._title_bar.set_disconnected()
        self._banner_a.show()
        self._banner_b.hide()
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

    def _on_message_received(self, message: dict) -> None:
        direction = str(message.get("direction", "inbound"))
        body = str(message.get("body", ""))
        sender = str(message.get("sender", ""))
        timestamp = str(message.get("timestamp", ""))[:5]  # HH:MM from ISO string

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
        unread_count = int(conversation.get("unread_count", 0))
        data = ConversationData(
            id=conv_id,
            name=str(conversation.get("display_name", conv_id)),
            phone=conv_id,
            preview=str(conversation.get("last_message_preview", "")),
            timestamp=str(conversation.get("last_message_at", ""))[:5],
            unread=unread_count > 0,
            unread_count=unread_count,
        )
        self._conv_list.update_item(conv_id, data)

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
        message_id = self._dbus_client.send_message(self._current_phone, text)
        if not message_id:
            print(f"[stub] send (no daemon): {text!r}")

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
