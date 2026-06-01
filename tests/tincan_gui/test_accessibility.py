"""
Accessibility specification tests for tincan-gui (WCAG 2.1 AA).
Design spec: tincan-s42 §4.
Bead: tincan-9ho.

Written BEFORE the accessibility pass (TDD). Tests will fail until the builder
completes the accessibility additions. The color contrast math tests (no PySide6)
live in test_contrast.py — 8 tests there pass today.

=== WHAT THE BUILDER MUST DO TO MAKE THESE PASS ===

1. Register QAccessible factories:
   ConversationItem  → QAccessible.Role.ListItem
   MessageBubble     → QAccessible.Role.StaticText
   CapabilityBanner  → QAccessible.Role.AlertMessage
   (QLabel/QPushButton get StaticText/Button automatically — no factory needed)

2. Create tincan_gui/capability_banner.py with:
   class CapabilityBanner(QWidget):
       def __init__(self, message: str) -> None: ...
       # Must set accessibleName = message, accessible role = Alert

3. Fix MessageBubble._update_accessible() for OUTBOUND:
   Current: "Outbound: <body> — from <sender> at <time>"  (wrong — no "from")
   Correct: "Outbound: <body> — sent at <time>"

4. Update ComposePanel.set_compose_enabled() to update send button accessible name:
   When disabled: "Send unavailable — <reason>" (or similar)
   When enabled:  "Send SMS message"
   Add: ComposePanel.send_button property → exposes _send_btn

5. MainWindow — add public API for testability:
   conversation_opened = Signal(str)       # emitted when a conversation is selected
   message_send_requested = Signal(str)    # emitted on send
   refresh_requested = Signal()            # emitted on F5 / Ctrl+R
   @property conversation_list → ConversationListWidget
   @property compose_panel → ComposePanel

6. ConversationListWidget — add public methods:
   def select_index(self, i: int) -> None  (wraps _select_index)
   def current_index(self) -> int           (returns _selected_index)

=== MODULE IMPORTS ===
from tincan_gui.conversation_list import ConversationData, ConversationItem, ConversationListWidget
from tincan_gui.thread_view import BubbleType, MessageBubble, MessageData
from tincan_gui.compose_panel import ComposePanel
from tincan_gui.main import MainWindow, TitleBar
from tincan_gui.capability_banner import CapabilityBanner   ← new module
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QAccessible

from tincan_gui.capability_banner import CapabilityBanner
from tincan_gui.compose_panel import ComposePanel
from tincan_gui.conversation_list import (
    ConversationData,
    ConversationItem,
)
from tincan_gui.main import MainWindow, TitleBar
from tincan_gui.thread_view import BubbleType, MessageBubble, MessageData

# ---------------------------------------------------------------------------
# §4.1 Metadata color applied on widget instances
# ---------------------------------------------------------------------------

class TestMetadataColorOnWidgets:
    """
    Verify the timestamp/metadata color fix (#9ca3af → #6b7280) is applied
    in actual widget instances.

    Builder note: expose timestamp_label_color() on ConversationItem and
    metadata_label_color() on MessageBubble; these are test accessors that
    return the hex color string currently applied to the label stylesheet.
    """

    def test_conversation_item_timestamp_color_is_6b7280(self, qtbot):
        data = ConversationData(
            id="c1", name="Alice", phone="+1 555-0100",
            preview="See you tomorrow", timestamp="10:32", unread=False,
        )
        item = ConversationItem(data)
        qtbot.addWidget(item)
        color = item.timestamp_label_color()
        assert color.lower() == "#6b7280", (
            f"Expected #6b7280 for AA compliance, got {color!r}"
        )

    def test_conversation_item_timestamp_color_is_not_9ca3af(self, qtbot):
        data = ConversationData(
            id="c1", name="Alice", phone="+1 555-0100",
            preview="See you", timestamp="10:32", unread=False,
        )
        item = ConversationItem(data)
        qtbot.addWidget(item)
        assert item.timestamp_label_color().lower() != "#9ca3af"

    def test_message_bubble_metadata_color_is_6b7280(self, qtbot):
        data = MessageData(BubbleType.INBOUND, "Hi", "Alice", "10:32")
        bubble = MessageBubble(data)
        qtbot.addWidget(bubble)
        assert bubble.metadata_label_color().lower() == "#6b7280"

    def test_message_bubble_metadata_color_is_not_9ca3af(self, qtbot):
        data = MessageData(BubbleType.INBOUND, "Hi", "Alice", "10:32")
        bubble = MessageBubble(data)
        qtbot.addWidget(bubble)
        assert bubble.metadata_label_color().lower() != "#9ca3af"


# ---------------------------------------------------------------------------
# §4.4 Qt accessible roles
# ---------------------------------------------------------------------------

class TestAccessibleRoles:
    """Verify QAccessible roles per tincan-s42 §4.4 table."""

    def test_conversation_item_role_is_list_item(self, qtbot):
        data = ConversationData(
            id="c1", name="Alice", phone="+1 555-0100",
            preview="Hi", timestamp="10:32", unread=False,
        )
        item = ConversationItem(data)
        qtbot.addWidget(item)
        iface = QAccessible.queryAccessibleInterface(item)
        assert iface is not None
        assert iface.role() == QAccessible.Role.ListItem

    def test_inbound_message_bubble_role_is_static_text(self, qtbot):
        data = MessageData(BubbleType.INBOUND, "Hello", "Alice", "10:32")
        bubble = MessageBubble(data)
        qtbot.addWidget(bubble)
        iface = QAccessible.queryAccessibleInterface(bubble)
        assert iface is not None
        assert iface.role() == QAccessible.Role.StaticText

    def test_outbound_message_bubble_role_is_static_text(self, qtbot):
        data = MessageData(BubbleType.OUTBOUND, "Hello back", "", "10:33")
        bubble = MessageBubble(data)
        qtbot.addWidget(bubble)
        iface = QAccessible.queryAccessibleInterface(bubble)
        assert iface is not None
        assert iface.role() == QAccessible.Role.StaticText

    def test_body_unavailable_bubble_role_is_static_text(self, qtbot):
        data = MessageData(BubbleType.BODY_UNAVAILABLE, "", "Mom", "09:00")
        bubble = MessageBubble(data)
        qtbot.addWidget(bubble)
        iface = QAccessible.queryAccessibleInterface(bubble)
        assert iface is not None
        assert iface.role() == QAccessible.Role.StaticText

    def test_send_button_role_is_button(self, qtbot):
        # QPushButton gets Button role automatically — verify it's preserved.
        panel = ComposePanel()
        qtbot.addWidget(panel)
        iface = QAccessible.queryAccessibleInterface(panel.send_button)
        assert iface is not None
        assert iface.role() == QAccessible.Role.Button

    def test_status_chip_role_is_static_text(self, qtbot):
        # QLabel gets StaticText role automatically — verify it's preserved.
        bar = TitleBar()
        qtbot.addWidget(bar)
        iface = QAccessible.queryAccessibleInterface(bar.status_chip)
        assert iface is not None
        assert iface.role() == QAccessible.Role.StaticText

    def test_capability_banner_role_is_alert(self, qtbot):
        # Alert role causes AT to announce immediately on visibility change.
        banner = CapabilityBanner(message="⊗ Connection lost")
        qtbot.addWidget(banner)
        iface = QAccessible.queryAccessibleInterface(banner)
        assert iface is not None
        assert iface.role() == QAccessible.Role.AlertMessage


# ---------------------------------------------------------------------------
# §4.4 Accessible name patterns
# ---------------------------------------------------------------------------

class TestAccessibleNames:
    """Verify accessible name patterns per tincan-s42 §4.4."""

    # --- ConversationItem ---

    def test_conversation_item_name_includes_contact_name(self, qtbot):
        data = ConversationData(
            id="c1", name="Alice", phone="+1 555-0100",
            preview="See you tomorrow", timestamp="10:32", unread=False,
        )
        item = ConversationItem(data)
        qtbot.addWidget(item)
        assert "Alice" in item.accessibleName()

    def test_conversation_item_name_includes_preview(self, qtbot):
        data = ConversationData(
            id="c1", name="Alice", phone="+1 555-0100",
            preview="See you tomorrow", timestamp="10:32", unread=False,
        )
        item = ConversationItem(data)
        qtbot.addWidget(item)
        assert "See you tomorrow" in item.accessibleName()

    def test_conversation_item_name_includes_timestamp(self, qtbot):
        data = ConversationData(
            id="c1", name="Alice", phone="+1 555-0100",
            preview="See you tomorrow", timestamp="10:32", unread=False,
        )
        item = ConversationItem(data)
        qtbot.addWidget(item)
        assert "10:32" in item.accessibleName()

    def test_conversation_item_accessible_description_is_unread_when_unread(self, qtbot):
        data = ConversationData(
            id="c2", name="Bob", phone="+1 555-0101",
            preview="Hey!", timestamp="09:15", unread=True,
        )
        item = ConversationItem(data)
        qtbot.addWidget(item)
        assert item.accessibleDescription() == "Unread"

    def test_conversation_item_accessible_description_is_empty_when_read(self, qtbot):
        data = ConversationData(
            id="c3", name="Carol", phone="+1 555-0102",
            preview="Later", timestamp="08:00", unread=False,
        )
        item = ConversationItem(data)
        qtbot.addWidget(item)
        assert item.accessibleDescription() == ""

    # --- MessageBubble ---

    def test_inbound_bubble_name_starts_with_inbound(self, qtbot):
        data = MessageData(BubbleType.INBOUND, "Hi there", "Alice", "10:32")
        bubble = MessageBubble(data)
        qtbot.addWidget(bubble)
        assert bubble.accessibleName().startswith("Inbound")

    def test_inbound_bubble_name_contains_body(self, qtbot):
        data = MessageData(BubbleType.INBOUND, "Hi there", "Alice", "10:32")
        bubble = MessageBubble(data)
        qtbot.addWidget(bubble)
        assert "Hi there" in bubble.accessibleName()

    def test_inbound_bubble_name_contains_sender(self, qtbot):
        data = MessageData(BubbleType.INBOUND, "Hi there", "Alice", "10:32")
        bubble = MessageBubble(data)
        qtbot.addWidget(bubble)
        assert "Alice" in bubble.accessibleName()

    def test_inbound_bubble_name_contains_timestamp(self, qtbot):
        data = MessageData(BubbleType.INBOUND, "Hi there", "Alice", "10:32")
        bubble = MessageBubble(data)
        qtbot.addWidget(bubble)
        assert "10:32" in bubble.accessibleName()

    def test_outbound_bubble_name_starts_with_outbound(self, qtbot):
        data = MessageData(BubbleType.OUTBOUND, "Hello back", "", "10:33")
        bubble = MessageBubble(data)
        qtbot.addWidget(bubble)
        assert bubble.accessibleName().startswith("Outbound")

    def test_outbound_bubble_name_contains_body(self, qtbot):
        data = MessageData(BubbleType.OUTBOUND, "Hello back", "", "10:33")
        bubble = MessageBubble(data)
        qtbot.addWidget(bubble)
        assert "Hello back" in bubble.accessibleName()

    def test_outbound_bubble_name_contains_timestamp(self, qtbot):
        data = MessageData(BubbleType.OUTBOUND, "Hello back", "", "10:33")
        bubble = MessageBubble(data)
        qtbot.addWidget(bubble)
        assert "10:33" in bubble.accessibleName()

    def test_outbound_bubble_name_does_not_say_from(self, qtbot):
        # Outbound has no sender — accessible name must not include "from"
        data = MessageData(BubbleType.OUTBOUND, "Hello back", "", "10:33")
        bubble = MessageBubble(data)
        qtbot.addWidget(bubble)
        assert " from " not in bubble.accessibleName()

    def test_body_unavailable_bubble_name_says_content_unavailable(self, qtbot):
        data = MessageData(BubbleType.BODY_UNAVAILABLE, "", "Mom", "09:00")
        bubble = MessageBubble(data)
        qtbot.addWidget(bubble)
        name = bubble.accessibleName()
        assert "content unavailable" in name.lower()

    def test_body_unavailable_bubble_name_contains_sender(self, qtbot):
        data = MessageData(BubbleType.BODY_UNAVAILABLE, "", "Mom", "09:00")
        bubble = MessageBubble(data)
        qtbot.addWidget(bubble)
        assert "Mom" in bubble.accessibleName()

    def test_body_unavailable_bubble_name_contains_timestamp(self, qtbot):
        data = MessageData(BubbleType.BODY_UNAVAILABLE, "", "Mom", "09:00")
        bubble = MessageBubble(data)
        qtbot.addWidget(bubble)
        assert "09:00" in bubble.accessibleName()

    # --- ComposePanel / Send button ---

    def test_send_button_accessible_name_when_enabled(self, qtbot):
        panel = ComposePanel()
        qtbot.addWidget(panel)
        assert panel.send_button.accessibleName() == "Send SMS message"

    def test_send_button_accessible_name_when_disabled_indicates_unavailable(self, qtbot):
        panel = ComposePanel()
        panel.set_compose_enabled(False, "not connected")
        qtbot.addWidget(panel)
        name = panel.send_button.accessibleName()
        assert "unavailable" in name.lower() or "Send" in name

    def test_send_button_accessible_name_when_disabled_contains_reason(self, qtbot):
        panel = ComposePanel()
        panel.set_compose_enabled(False, "not connected")
        qtbot.addWidget(panel)
        assert "not connected" in panel.send_button.accessibleName()

    def test_send_button_accessible_name_restored_when_reenabled(self, qtbot):
        panel = ComposePanel()
        panel.set_compose_enabled(False, "not connected")
        panel.set_compose_enabled(True)
        qtbot.addWidget(panel)
        assert panel.send_button.accessibleName() == "Send SMS message"

    # --- TitleBar / StatusChip ---

    def test_status_chip_accessible_name_when_connected(self, qtbot):
        bar = TitleBar()
        bar.set_connected("iPhone 15 Pro")
        qtbot.addWidget(bar)
        name = bar.status_chip.accessibleName()
        assert "Connection status" in name
        assert "Connected" in name

    def test_status_chip_accessible_name_when_disconnected(self, qtbot):
        bar = TitleBar()
        bar.set_disconnected()
        qtbot.addWidget(bar)
        name = bar.status_chip.accessibleName()
        assert "Connection status" in name
        assert "Disconnected" in name

    # --- CapabilityBanner ---

    def test_capability_banner_accessible_name_equals_full_message(self, qtbot):
        msg = "⊗ Connection lost — Bluetooth out of range · reconnecting…"
        banner = CapabilityBanner(message=msg)
        qtbot.addWidget(banner)
        assert banner.accessibleName() == msg

    def test_capability_banner_show_notifications_message(self, qtbot):
        msg = "⚠ Messaging unavailable — Enable 'Show Notifications' on iPhone"
        banner = CapabilityBanner(message=msg)
        qtbot.addWidget(banner)
        assert banner.accessibleName() == msg


# ---------------------------------------------------------------------------
# §4.3 Keyboard navigation
# ---------------------------------------------------------------------------

class TestKeyboardNavigation:
    """Verify keyboard shortcuts and focus flow per tincan-s42 §4.3."""

    def test_ctrl_1_focuses_conversation_list(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window.compose_panel._input.setFocus()
        qtbot.keyClick(window, Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier)
        assert (
            window.conversation_list.hasFocus()
            or window.conversation_list.isAncestorOf(window.focusWidget())
        )

    def test_ctrl_n_focuses_compose_input(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window.conversation_list.setFocus()
        qtbot.keyClick(window, Qt.Key.Key_N, Qt.KeyboardModifier.ControlModifier)
        assert window.compose_panel._input.hasFocus()

    def test_arrow_down_advances_selection_in_conversation_list(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        # MainWindow._load_stub_data loads 3 conversations; select first
        window.conversation_list.select_index(0)
        assert window.conversation_list.current_index() == 0
        qtbot.keyClick(window.conversation_list, Qt.Key.Key_Down)
        assert window.conversation_list.current_index() == 1

    def test_arrow_up_retreats_selection_in_conversation_list(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window.conversation_list.select_index(1)
        qtbot.keyClick(window.conversation_list, Qt.Key.Key_Up)
        assert window.conversation_list.current_index() == 0

    def test_enter_on_conversation_list_emits_conversation_opened(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window.conversation_list.select_index(0)

        opened = []
        window.conversation_opened.connect(lambda c: opened.append(c))
        qtbot.keyClick(window.conversation_list, Qt.Key.Key_Return)
        assert len(opened) == 1

    def test_space_on_conversation_list_emits_conversation_opened(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window.conversation_list.select_index(0)

        opened = []
        window.conversation_opened.connect(lambda c: opened.append(c))
        qtbot.keyClick(window.conversation_list, Qt.Key.Key_Space)
        assert len(opened) == 1

    def test_return_in_compose_emits_message_send_requested(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window.compose_panel._input.setFocus()
        window.compose_panel._input.setPlainText("Hello world")

        sent = []
        window.message_send_requested.connect(lambda t: sent.append(t))
        qtbot.keyClick(
            window.compose_panel._input, Qt.Key.Key_Return
        )
        assert len(sent) == 1
        assert sent[0] == "Hello world"

    def test_shift_return_inserts_newline_and_does_not_send(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window.compose_panel._input.setFocus()
        window.compose_panel._input.setPlainText("Line 1")

        sent = []
        window.message_send_requested.connect(lambda t: sent.append(t))
        qtbot.keyClick(
            window.compose_panel._input,
            Qt.Key.Key_Return,
            Qt.KeyboardModifier.ShiftModifier,
        )
        assert len(sent) == 0
        assert "\n" in window.compose_panel._input.toPlainText()

    def test_f5_emits_refresh_requested(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()

        refreshed = []
        window.refresh_requested.connect(lambda: refreshed.append(True))
        qtbot.keyClick(window, Qt.Key.Key_F5)
        assert len(refreshed) == 1

    def test_ctrl_r_emits_refresh_requested(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()

        refreshed = []
        window.refresh_requested.connect(lambda: refreshed.append(True))
        qtbot.keyClick(window, Qt.Key.Key_R, Qt.KeyboardModifier.ControlModifier)
        assert len(refreshed) == 1


# ---------------------------------------------------------------------------
# §4.4 Screen reader announcements (holistic)
# ---------------------------------------------------------------------------

class TestScreenReaderAnnouncements:
    """Verify that each bubble's accessible name contains all required elements."""

    def test_inbound_bubble_announces_direction_body_sender_time(self, qtbot):
        # spec §4.6: "direction + body + sender + time in one announcement"
        data = MessageData(BubbleType.INBOUND, "Meeting at 3pm", "Alice", "10:32")
        bubble = MessageBubble(data)
        qtbot.addWidget(bubble)
        name = bubble.accessibleName()
        assert "Inbound" in name
        assert "Meeting at 3pm" in name
        assert "Alice" in name
        assert "10:32" in name

    def test_outbound_bubble_announces_direction_body_time(self, qtbot):
        data = MessageData(BubbleType.OUTBOUND, "On my way", "", "10:45")
        bubble = MessageBubble(data)
        qtbot.addWidget(bubble)
        name = bubble.accessibleName()
        assert "Outbound" in name
        assert "On my way" in name
        assert "10:45" in name

    def test_capability_banner_alert_role_is_the_immediate_announcement_mechanism(self, qtbot):
        # Alert role causes AT (ORCA, JAWS, NVDA) to announce without requiring focus.
        banner = CapabilityBanner(message="⊗ Connection lost")
        qtbot.addWidget(banner)
        iface = QAccessible.queryAccessibleInterface(banner)
        assert iface is not None
        assert iface.role() == QAccessible.Role.AlertMessage
