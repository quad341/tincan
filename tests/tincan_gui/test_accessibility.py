"""
Accessibility specification tests for tincan-gui (WCAG 2.1 AA).
Design spec: tincan-s42 §4.
Bead: tincan-9ho.

Written BEFORE implementation (TDD). Tests will fail until tincan_gui.widgets
is implemented AND PySide6 is installed. The builder must make all tests pass.

Color contrast math tests (no PySide6) live in test_contrast.py.

Widget API contract implied by these tests
------------------------------------------
ConversationItem(name, preview, timestamp, unread):
    .accessibleName() -> str
    .accessibleDescription() -> str
    .timestamp_label_color() -> str  # lowercase hex, e.g. "#6b7280"

MessageBubble(direction, body, sender, timestamp):
    direction: "inbound" | "outbound"
    body: str | None  # None means MAP returned no body
    .accessibleName() -> str
    .metadata_label_color() -> str

SendButton():
    .accessibleName() -> str  # "Send SMS message" (enabled), "Send unavailable — <reason>" (disabled)
    .set_disabled_reason(reason: str)

StatusChip(connected, device_name):
    .accessibleName() -> str  # "Connection status: Connected — <name>" or "Connection status: Disconnected"

CapabilityBanner(message):
    .accessibleName() -> str  # == message

MainWindow():
    .conversation_list  -> ConversationList
    .compose_panel      -> ComposePanel (with .text_input: QPlainTextEdit)
    .load_conversations(list[dict])
    .conversation_opened  (Signal)
    .message_send_requested  (Signal[str])
    .refresh_requested  (Signal)

ConversationList:
    .select_index(i: int)
    .current_index() -> int
"""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QAccessible
from tincan_gui.widgets import (
    CapabilityBanner,
    ConversationItem,
    MainWindow,
    MessageBubble,
    SendButton,
    StatusChip,
)


# ---------------------------------------------------------------------------
# §4.1 Metadata color applied on widget instances
# ---------------------------------------------------------------------------

class TestMetadataColorOnWidgets:
    """Verify the timestamp/metadata color fix is applied in actual widget instances."""

    def test_conversation_item_timestamp_color_is_6b7280(self, qtbot):
        item = ConversationItem(
            name="Alice", preview="See you tomorrow", timestamp="10:32", unread=False
        )
        qtbot.addWidget(item)
        color = item.timestamp_label_color()
        assert color.lower() == "#6b7280", (
            f"Expected #6b7280 for AA compliance, got {color!r}. "
            "tincan-9ho fix: replace #9ca3af with #6b7280 on all white backgrounds."
        )

    def test_conversation_item_timestamp_color_is_not_failing_9ca3af(self, qtbot):
        item = ConversationItem(
            name="Alice", preview="See you", timestamp="10:32", unread=False
        )
        qtbot.addWidget(item)
        assert item.timestamp_label_color().lower() != "#9ca3af"

    def test_message_bubble_metadata_color_is_6b7280(self, qtbot):
        bubble = MessageBubble(
            direction="inbound", body="Hi", sender="Alice", timestamp="10:32"
        )
        qtbot.addWidget(bubble)
        assert bubble.metadata_label_color().lower() == "#6b7280"

    def test_message_bubble_metadata_color_is_not_9ca3af(self, qtbot):
        bubble = MessageBubble(
            direction="inbound", body="Hi", sender="Alice", timestamp="10:32"
        )
        qtbot.addWidget(bubble)
        assert bubble.metadata_label_color().lower() != "#9ca3af"


# ---------------------------------------------------------------------------
# §4.4 Qt accessible roles
# ---------------------------------------------------------------------------

class TestAccessibleRoles:
    """Verify QAccessible roles per tincan-s42 §4.4 table."""

    def test_conversation_item_role_is_list_item(self, qtbot):
        item = ConversationItem(
            name="Alice", preview="Hi", timestamp="10:32", unread=False
        )
        qtbot.addWidget(item)
        iface = QAccessible.queryAccessibleInterface(item)
        assert iface is not None
        assert iface.role() == QAccessible.Role.ListItem

    def test_inbound_message_bubble_role_is_static_text(self, qtbot):
        bubble = MessageBubble(
            direction="inbound", body="Hello", sender="Alice", timestamp="10:32"
        )
        qtbot.addWidget(bubble)
        iface = QAccessible.queryAccessibleInterface(bubble)
        assert iface is not None
        assert iface.role() == QAccessible.Role.StaticText

    def test_outbound_message_bubble_role_is_static_text(self, qtbot):
        bubble = MessageBubble(
            direction="outbound", body="Hello back", sender=None, timestamp="10:33"
        )
        qtbot.addWidget(bubble)
        iface = QAccessible.queryAccessibleInterface(bubble)
        assert iface is not None
        assert iface.role() == QAccessible.Role.StaticText

    def test_send_button_role_is_button(self, qtbot):
        btn = SendButton()
        qtbot.addWidget(btn)
        iface = QAccessible.queryAccessibleInterface(btn)
        assert iface is not None
        assert iface.role() == QAccessible.Role.Button

    def test_status_chip_role_is_static_text(self, qtbot):
        chip = StatusChip(connected=True, device_name="iPhone 15 Pro")
        qtbot.addWidget(chip)
        iface = QAccessible.queryAccessibleInterface(chip)
        assert iface is not None
        assert iface.role() == QAccessible.Role.StaticText

    def test_capability_banner_role_is_alert(self, qtbot):
        # Alert role causes AT to announce the banner immediately — no focus required.
        banner = CapabilityBanner(message="⊗ Connection lost")
        qtbot.addWidget(banner)
        iface = QAccessible.queryAccessibleInterface(banner)
        assert iface is not None
        assert iface.role() == QAccessible.Role.Alert


# ---------------------------------------------------------------------------
# §4.4 Accessible name patterns
# ---------------------------------------------------------------------------

class TestAccessibleNames:
    """Verify accessible name patterns per tincan-s42 §4.4."""

    def test_conversation_item_name_includes_contact_name(self, qtbot):
        item = ConversationItem(
            name="Alice", preview="See you tomorrow", timestamp="10:32", unread=False
        )
        qtbot.addWidget(item)
        assert "Alice" in item.accessibleName()

    def test_conversation_item_name_includes_preview(self, qtbot):
        item = ConversationItem(
            name="Alice", preview="See you tomorrow", timestamp="10:32", unread=False
        )
        qtbot.addWidget(item)
        assert "See you tomorrow" in item.accessibleName()

    def test_conversation_item_name_includes_timestamp(self, qtbot):
        item = ConversationItem(
            name="Alice", preview="See you tomorrow", timestamp="10:32", unread=False
        )
        qtbot.addWidget(item)
        assert "10:32" in item.accessibleName()

    def test_conversation_item_name_includes_unread_marker_when_unread(self, qtbot):
        item = ConversationItem(
            name="Bob", preview="Are you coming?", timestamp="09:15", unread=True
        )
        qtbot.addWidget(item)
        assert "Unread" in item.accessibleName()

    def test_conversation_item_name_excludes_unread_marker_when_read(self, qtbot):
        item = ConversationItem(
            name="Carol", preview="See you", timestamp="08:00", unread=False
        )
        qtbot.addWidget(item)
        assert "Unread" not in item.accessibleName()

    def test_conversation_item_accessible_description_is_unread_when_unread(self, qtbot):
        # Spec §4.4: unread state expressed via setAccessibleDescription("Unread")
        item = ConversationItem(
            name="Dave", preview="Hey!", timestamp="11:00", unread=True
        )
        qtbot.addWidget(item)
        assert item.accessibleDescription() == "Unread"

    def test_conversation_item_accessible_description_empty_when_read(self, qtbot):
        item = ConversationItem(
            name="Eve", preview="Later", timestamp="14:00", unread=False
        )
        qtbot.addWidget(item)
        assert item.accessibleDescription() == ""

    def test_inbound_bubble_name_starts_with_inbound(self, qtbot):
        bubble = MessageBubble(
            direction="inbound", body="Hi there", sender="Alice", timestamp="10:32"
        )
        qtbot.addWidget(bubble)
        assert bubble.accessibleName().startswith("Inbound")

    def test_inbound_bubble_name_contains_body(self, qtbot):
        bubble = MessageBubble(
            direction="inbound", body="Hi there", sender="Alice", timestamp="10:32"
        )
        qtbot.addWidget(bubble)
        assert "Hi there" in bubble.accessibleName()

    def test_inbound_bubble_name_contains_sender(self, qtbot):
        bubble = MessageBubble(
            direction="inbound", body="Hi there", sender="Alice", timestamp="10:32"
        )
        qtbot.addWidget(bubble)
        assert "Alice" in bubble.accessibleName()

    def test_inbound_bubble_name_contains_timestamp(self, qtbot):
        bubble = MessageBubble(
            direction="inbound", body="Hi there", sender="Alice", timestamp="10:32"
        )
        qtbot.addWidget(bubble)
        assert "10:32" in bubble.accessibleName()

    def test_outbound_bubble_name_starts_with_outbound(self, qtbot):
        bubble = MessageBubble(
            direction="outbound", body="Hello back", sender=None, timestamp="10:33"
        )
        qtbot.addWidget(bubble)
        assert bubble.accessibleName().startswith("Outbound")

    def test_outbound_bubble_name_contains_body(self, qtbot):
        bubble = MessageBubble(
            direction="outbound", body="Hello back", sender=None, timestamp="10:33"
        )
        qtbot.addWidget(bubble)
        assert "Hello back" in bubble.accessibleName()

    def test_outbound_bubble_name_contains_timestamp(self, qtbot):
        bubble = MessageBubble(
            direction="outbound", body="Hello back", sender=None, timestamp="10:33"
        )
        qtbot.addWidget(bubble)
        assert "10:33" in bubble.accessibleName()

    def test_content_unavailable_bubble_name_says_content_unavailable(self, qtbot):
        # body=None means MAP returned no body (iOS Show Previews off or fetch failure)
        bubble = MessageBubble(
            direction="inbound", body=None, sender="Mom", timestamp="09:00"
        )
        qtbot.addWidget(bubble)
        name = bubble.accessibleName()
        assert "content unavailable" in name.lower()
        assert "Mom" in name

    def test_content_unavailable_bubble_name_contains_sender_and_time(self, qtbot):
        bubble = MessageBubble(
            direction="inbound", body=None, sender="Mom", timestamp="09:00"
        )
        qtbot.addWidget(bubble)
        name = bubble.accessibleName()
        assert "Mom" in name
        assert "09:00" in name

    def test_send_button_accessible_name_when_enabled(self, qtbot):
        btn = SendButton()
        qtbot.addWidget(btn)
        assert btn.accessibleName() == "Send SMS message"

    def test_send_button_accessible_name_when_disabled_contains_reason(self, qtbot):
        btn = SendButton()
        btn.setEnabled(False)
        btn.set_disabled_reason("not connected")
        qtbot.addWidget(btn)
        name = btn.accessibleName()
        assert "not connected" in name

    def test_send_button_accessible_name_when_disabled_indicates_unavailable(self, qtbot):
        btn = SendButton()
        btn.setEnabled(False)
        btn.set_disabled_reason("not connected")
        qtbot.addWidget(btn)
        name = btn.accessibleName()
        assert "unavailable" in name.lower() or "Send" in name

    def test_status_chip_accessible_name_when_connected(self, qtbot):
        chip = StatusChip(connected=True, device_name="iPhone 15 Pro")
        qtbot.addWidget(chip)
        name = chip.accessibleName()
        assert "Connection status" in name
        assert "Connected" in name

    def test_status_chip_accessible_name_when_disconnected(self, qtbot):
        chip = StatusChip(connected=False, device_name=None)
        qtbot.addWidget(chip)
        name = chip.accessibleName()
        assert "Connection status" in name
        assert "Disconnected" in name

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
        # Start focus in compose
        window.compose_panel.text_input.setFocus()
        qtbot.keyClick(window, Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier)
        assert window.conversation_list.hasFocus() or window.conversation_list.isAncestorOf(
            window.focusWidget()
        )

    def test_ctrl_n_focuses_compose_text_input(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window.conversation_list.setFocus()
        qtbot.keyClick(window, Qt.Key.Key_N, Qt.KeyboardModifier.ControlModifier)
        assert window.compose_panel.text_input.hasFocus()

    def test_arrow_down_advances_conversation_selection(self, qtbot):
        window = MainWindow()
        window.load_conversations([
            {"name": "Alice", "preview": "Hi", "timestamp": "10:00", "unread": False},
            {"name": "Bob", "preview": "Hey", "timestamp": "09:00", "unread": False},
        ])
        qtbot.addWidget(window)
        window.show()
        window.conversation_list.setFocus()
        window.conversation_list.select_index(0)
        initial = window.conversation_list.current_index()
        qtbot.keyClick(window.conversation_list, Qt.Key.Key_Down)
        assert window.conversation_list.current_index() == initial + 1

    def test_arrow_up_retreats_conversation_selection(self, qtbot):
        window = MainWindow()
        window.load_conversations([
            {"name": "Alice", "preview": "Hi", "timestamp": "10:00", "unread": False},
            {"name": "Bob", "preview": "Hey", "timestamp": "09:00", "unread": False},
        ])
        qtbot.addWidget(window)
        window.show()
        window.conversation_list.setFocus()
        window.conversation_list.select_index(1)
        qtbot.keyClick(window.conversation_list, Qt.Key.Key_Up)
        assert window.conversation_list.current_index() == 0

    def test_enter_opens_selected_conversation(self, qtbot):
        window = MainWindow()
        window.load_conversations([
            {"name": "Alice", "preview": "Hi", "timestamp": "10:00", "unread": False},
        ])
        qtbot.addWidget(window)
        window.show()
        window.conversation_list.setFocus()
        window.conversation_list.select_index(0)

        opened = []
        window.conversation_opened.connect(lambda c: opened.append(c))
        qtbot.keyClick(window.conversation_list, Qt.Key.Key_Return)
        assert len(opened) == 1

    def test_space_opens_selected_conversation(self, qtbot):
        window = MainWindow()
        window.load_conversations([
            {"name": "Alice", "preview": "Hi", "timestamp": "10:00", "unread": False},
        ])
        qtbot.addWidget(window)
        window.show()
        window.conversation_list.setFocus()
        window.conversation_list.select_index(0)

        opened = []
        window.conversation_opened.connect(lambda c: opened.append(c))
        qtbot.keyClick(window.conversation_list, Qt.Key.Key_Space)
        assert len(opened) == 1

    def test_return_in_compose_emits_send_signal(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window.compose_panel.text_input.setFocus()
        window.compose_panel.text_input.setPlainText("Hello world")

        sent_texts = []
        window.message_send_requested.connect(lambda t: sent_texts.append(t))
        qtbot.keyClick(
            window.compose_panel.text_input, Qt.Key.Key_Return
        )
        assert len(sent_texts) == 1
        assert sent_texts[0] == "Hello world"

    def test_shift_return_inserts_newline_without_sending(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()
        window.compose_panel.text_input.setFocus()
        window.compose_panel.text_input.setPlainText("Line 1")

        sent_texts = []
        window.message_send_requested.connect(lambda t: sent_texts.append(t))
        qtbot.keyClick(
            window.compose_panel.text_input,
            Qt.Key.Key_Return,
            Qt.KeyboardModifier.ShiftModifier,
        )
        # Must NOT send
        assert len(sent_texts) == 0
        # Must contain a newline
        assert "\n" in window.compose_panel.text_input.toPlainText()

    def test_f5_triggers_refresh_signal(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()

        refreshed = []
        window.refresh_requested.connect(lambda: refreshed.append(True))
        qtbot.keyClick(window, Qt.Key.Key_F5)
        assert len(refreshed) == 1

    def test_ctrl_r_triggers_refresh_signal(self, qtbot):
        window = MainWindow()
        qtbot.addWidget(window)
        window.show()

        refreshed = []
        window.refresh_requested.connect(lambda: refreshed.append(True))
        qtbot.keyClick(window, Qt.Key.Key_R, Qt.KeyboardModifier.ControlModifier)
        assert len(refreshed) == 1


# ---------------------------------------------------------------------------
# §4.4 Screen reader announcements
# ---------------------------------------------------------------------------

class TestScreenReaderAnnouncements:
    """Verify announcement content satisfies spec §4.4 — one cohesive announcement."""

    def test_inbound_bubble_announces_all_four_elements_in_one_name(self, qtbot):
        # Spec §4.4: "direction + body + sender + time in one announcement"
        bubble = MessageBubble(
            direction="inbound",
            body="Meeting at 3pm",
            sender="Alice",
            timestamp="10:32",
        )
        qtbot.addWidget(bubble)
        name = bubble.accessibleName()
        assert "Inbound" in name       # direction
        assert "Meeting at 3pm" in name  # body
        assert "Alice" in name         # sender
        assert "10:32" in name         # time

    def test_outbound_bubble_announces_direction_body_time(self, qtbot):
        # Outbound has no "sender" — announces direction + body + time
        bubble = MessageBubble(
            direction="outbound",
            body="On my way",
            sender=None,
            timestamp="10:45",
        )
        qtbot.addWidget(bubble)
        name = bubble.accessibleName()
        assert "Outbound" in name
        assert "On my way" in name
        assert "10:45" in name

    def test_capability_banner_alert_role_enables_immediate_announcement(self, qtbot):
        # The Alert role is the AT mechanism that triggers announcement without focus.
        banner = CapabilityBanner(message="⊗ Connection lost — Bluetooth out of range")
        qtbot.addWidget(banner)
        iface = QAccessible.queryAccessibleInterface(banner)
        assert iface is not None
        assert iface.role() == QAccessible.Role.Alert

    def test_capability_banner_accessible_name_is_full_text(self, qtbot):
        msg = "⚠ Messaging unavailable — Enable 'Show Notifications' on iPhone"
        banner = CapabilityBanner(message=msg)
        qtbot.addWidget(banner)
        assert banner.accessibleName() == msg
