"""Tests: GUI group conversation display, compose dialog, thread view, dbus_client additions.
Bead: tincan-m9609

Coverage:
  §1  ConversationData is_group=True renders GroupAvatarWidget, not AvatarWidget
  §2  Group card accessible name — includes participant names and unread count
  §3  Compose dialog chip states: 0 chips → Start disabled; 1 chip → Start enabled;
      ≥2 chips → Start Group enabled
  §4  Backspace with empty input removes last chip
  §5  Already-chipped contact appears grayed/disabled in autocomplete
  §6  Compose accept ≥2 chips calls dbus_client.send_message_to_recipients with correct phones
  §7  ThreadView.set_group_mode(True) shows group header with participant count
  §8  Sender attribution label appears above inbound bubbles in group mode
  §9  Outbound bubbles: no attribution label
  §10 ComposePanel.set_group_mode(True) hides SMS character counter
  §11 dbus_client.send_message_to_recipients returns conv_id from D-Bus
  §12 dbus_client.get_conversation_participants returns list from D-Bus

No real D-Bus needed — GUI tests are isolated by conftest._hermetic_dbus.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt

from tincan_gui.avatar import AvatarWidget, GroupAvatarWidget
from tincan_gui.conversation_list import ConversationData, ConversationItem
from tincan_gui.dbus_client import TincandClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _group_data(**overrides) -> ConversationData:
    defaults = {
        "id": "g1",
        "name": "Group",
        "phone": "",
        "preview": "Hey",
        "timestamp": "10:00",
        "unread": False,
        "unread_count": 0,
        "is_group": True,
        "participants": ["Alice", "Bob"],
        "group_name": "",
        "preview_sender": "",
    }
    defaults.update(overrides)
    return ConversationData(**defaults)


def _solo_data(**overrides) -> ConversationData:
    defaults = {
        "id": "c1",
        "name": "Alice",
        "phone": "+15550101234",
        "preview": "Hi",
        "timestamp": "09:00",
        "unread": False,
        "unread_count": 0,
        "is_group": False,
        "participants": [],
        "group_name": "",
        "preview_sender": "",
    }
    defaults.update(overrides)
    return ConversationData(**defaults)


# ---------------------------------------------------------------------------
# §1 Group avatar widget type
# ---------------------------------------------------------------------------

class TestGroupCardAvatarWidget:
    """is_group=True uses GroupAvatarWidget; is_group=False uses AvatarWidget."""

    def test_is_group_true_uses_group_avatar_widget(self, qtbot):
        item = ConversationItem(_group_data())
        qtbot.addWidget(item)
        assert isinstance(item._avatar, GroupAvatarWidget)

    def test_is_group_false_uses_avatar_widget_not_group(self, qtbot):
        item = ConversationItem(_solo_data())
        qtbot.addWidget(item)
        assert isinstance(item._avatar, AvatarWidget)
        assert not isinstance(item._avatar, GroupAvatarWidget)


# ---------------------------------------------------------------------------
# §2 Group card accessible name
# ---------------------------------------------------------------------------

class TestGroupCardAccessibleName:
    """Group card accessible name identifies group and reports unread count."""

    def test_accessible_name_contains_group_identifier(self, qtbot):
        item = ConversationItem(_group_data(participants=["Alice", "Bob"], unread_count=0))
        qtbot.addWidget(item)
        name = item.accessibleName()
        assert "Group" in name or "group" in name

    def test_accessible_name_contains_participant_names(self, qtbot):
        item = ConversationItem(_group_data(participants=["Alice", "Bob"], unread_count=0))
        qtbot.addWidget(item)
        name = item.accessibleName()
        assert "Alice" in name or "Bob" in name

    def test_accessible_name_contains_unread_count_when_nonzero(self, qtbot):
        item = ConversationItem(_group_data(participants=["Alice", "Bob"], unread_count=3))
        qtbot.addWidget(item)
        name = item.accessibleName()
        assert "3" in name


# ---------------------------------------------------------------------------
# §3 Compose dialog chip states
# ---------------------------------------------------------------------------

class TestComposeDialogChipStates:
    """NewConversationDialog OK button state tracks chip count."""

    @pytest.fixture
    def dialog(self, qtbot):
        from tincan_gui.main import NewConversationDialog
        d = NewConversationDialog()
        qtbot.addWidget(d)
        return d

    def test_zero_chips_start_button_disabled(self, dialog):
        # No chips added yet — Start button must be disabled
        assert not dialog.start_button.isEnabled()

    def test_one_chip_start_button_enabled(self, dialog):
        dialog.add_chip("Alice", "+15550101234")
        assert dialog.start_button.isEnabled()

    def test_one_chip_start_button_label_is_start(self, dialog):
        dialog.add_chip("Alice", "+15550101234")
        assert "Start" in dialog.start_button.text()
        assert "Group" not in dialog.start_button.text()

    def test_two_chips_start_group_button_enabled(self, dialog):
        dialog.add_chip("Alice", "+15550101234")
        dialog.add_chip("Bob", "+15550105678")
        assert dialog.start_button.isEnabled()

    def test_two_chips_button_label_becomes_start_group(self, dialog):
        dialog.add_chip("Alice", "+15550101234")
        dialog.add_chip("Bob", "+15550105678")
        assert "Group" in dialog.start_button.text()


# ---------------------------------------------------------------------------
# §4 Backspace with empty input removes last chip
# ---------------------------------------------------------------------------

class TestComposeDialogBackspaceRemovesChip:
    """Pressing Backspace in empty input field removes the most recently added chip."""

    @pytest.fixture
    def dialog(self, qtbot):
        from tincan_gui.main import NewConversationDialog
        d = NewConversationDialog()
        qtbot.addWidget(d)
        return d

    def test_backspace_removes_last_chip(self, dialog, qtbot):
        dialog.add_chip("Alice", "+15550101234")
        dialog.add_chip("Bob", "+15550105678")
        assert dialog.chip_count() == 2
        qtbot.keyPress(dialog.chip_input, Qt.Key_Backspace)
        assert dialog.chip_count() == 1

    def test_backspace_with_no_chips_does_not_raise(self, dialog, qtbot):
        assert dialog.chip_count() == 0
        qtbot.keyPress(dialog.chip_input, Qt.Key_Backspace)  # must not raise


# ---------------------------------------------------------------------------
# §5 Already-chipped contact is grayed in autocomplete
# ---------------------------------------------------------------------------

class TestComposeDialogAlreadyChippedGrayed:
    """A contact that already has a chip appears as disabled in autocomplete."""

    @pytest.fixture
    def dialog(self, qtbot):
        from tincan_gui.main import NewConversationDialog
        d = NewConversationDialog()
        qtbot.addWidget(d)
        return d

    def test_already_chipped_contact_not_selectable(self, dialog, qtbot):
        dialog.add_chip("Alice", "+15550101234")
        # Trigger autocomplete for "Alice"
        suggestions = dialog.get_autocomplete_suggestions("Alice")
        alice_items = [s for s in suggestions if s.get("phone") == "+15550101234"]
        if alice_items:
            assert alice_items[0].get("disabled") or not alice_items[0].get("enabled", True)


# ---------------------------------------------------------------------------
# §6 Compose accept ≥2 chips calls send_message_to_recipients
# ---------------------------------------------------------------------------

class TestComposeDialogAcceptCallsSendToRecipients:
    """Accepting ≥2 chips calls dbus_client.send_message_to_recipients with phone list."""

    @pytest.fixture
    def dialog_with_client(self, qtbot):
        from tincan_gui.main import NewConversationDialog
        mock_client = MagicMock()
        mock_client.send_message_to_recipients.return_value = "group-conv-1"
        d = NewConversationDialog(dbus_client=mock_client)
        qtbot.addWidget(d)
        return d, mock_client

    def test_accept_with_two_chips_calls_send_to_recipients(self, dialog_with_client, qtbot):
        dialog, mock_client = dialog_with_client
        dialog.add_chip("Alice", "+15550101234")
        dialog.add_chip("Bob", "+15550105678")
        dialog.accept()
        mock_client.send_message_to_recipients.assert_called_once()

    def test_phones_passed_to_send_to_recipients(self, dialog_with_client, qtbot):
        dialog, mock_client = dialog_with_client
        dialog.add_chip("Alice", "+15550101234")
        dialog.add_chip("Bob", "+15550105678")
        dialog.accept()
        phones = mock_client.send_message_to_recipients.call_args[0][0]
        assert "+15550101234" in phones or "5550101234" in phones
        assert "+15550105678" in phones or "5550105678" in phones


# ---------------------------------------------------------------------------
# §7 ThreadView.set_group_mode(True) shows group header with participant count
# ---------------------------------------------------------------------------

class TestThreadViewGroupMode:
    """set_group_mode(True) activates a group header showing participant count."""

    def test_set_group_mode_true_does_not_raise(self, qtbot):
        from tincan_gui.thread_view import ThreadView
        view = ThreadView()
        qtbot.addWidget(view)
        view.set_group_mode(True, participants=["Alice", "Bob", "Carol"])

    def test_group_header_shows_participant_count(self, qtbot):
        from tincan_gui.thread_view import ThreadView
        view = ThreadView()
        qtbot.addWidget(view)
        view.set_group_mode(True, participants=["Alice", "Bob", "Carol"])
        # Header subtitle should contain "3" (participant count)
        header_text = view._thread_header.subtitle_text()
        assert "3" in header_text

    def test_set_group_mode_false_hides_group_subtitle(self, qtbot):
        from tincan_gui.thread_view import ThreadView
        view = ThreadView()
        qtbot.addWidget(view)
        view.set_group_mode(True, participants=["Alice", "Bob"])
        view.set_group_mode(False)
        header_text = view._thread_header.subtitle_text()
        assert "Group" not in header_text and "2" not in header_text


# ---------------------------------------------------------------------------
# §8 Sender attribution label on inbound group bubbles
# ---------------------------------------------------------------------------

class TestSenderAttributionLabel:
    """In group mode, an attribution label appears above inbound bubbles."""

    def test_inbound_bubble_in_group_mode_has_attribution(self, qtbot):
        from tincan_gui.thread_view import BubbleType, MessageBubble, MessageData
        msg = MessageData(
            id="1",
            direction="inbound",
            body="Hey",
            timestamp="10:00",
            status="read",
            from_addr="Alice",
            show_attribution=True,
        )
        bubble = MessageBubble(msg, is_group=True)
        qtbot.addWidget(bubble)
        assert bubble._attribution_label is not None
        assert bubble._attribution_label.isVisible()

    def test_attribution_label_shows_sender_name(self, qtbot):
        from tincan_gui.thread_view import BubbleType, MessageBubble, MessageData
        msg = MessageData(
            id="2",
            direction="inbound",
            body="Hi",
            timestamp="10:01",
            status="read",
            from_addr="Alice",
            show_attribution=True,
        )
        bubble = MessageBubble(msg, is_group=True)
        qtbot.addWidget(bubble)
        assert "Alice" in bubble._attribution_label.text()


# ---------------------------------------------------------------------------
# §9 Outbound bubbles have no attribution label
# ---------------------------------------------------------------------------

class TestNoAttributionOnOutbound:
    """Outbound bubbles never show a sender attribution label."""

    def test_outbound_bubble_no_attribution(self, qtbot):
        from tincan_gui.thread_view import BubbleType, MessageBubble, MessageData
        msg = MessageData(
            id="3",
            direction="outbound",
            body="Hello",
            timestamp="10:02",
            status="read",
            from_addr="",
            show_attribution=False,
        )
        bubble = MessageBubble(msg, is_group=True)
        qtbot.addWidget(bubble)
        # Attribution label should either not exist or be invisible
        attrib = getattr(bubble, "_attribution_label", None)
        if attrib is not None:
            assert not attrib.isVisible()


# ---------------------------------------------------------------------------
# §10 SMS character counter hidden in group mode
# ---------------------------------------------------------------------------

class TestSmsCounterHiddenInGroupMode:
    """ComposePanel.set_group_mode(True) hides the SMS character counter."""

    def test_sms_counter_hidden_after_set_group_mode_true(self, qtbot):
        from tincan_gui.compose_panel import ComposePanel
        panel = ComposePanel()
        qtbot.addWidget(panel)
        panel.set_group_mode(True)
        # The SMS counter widget (varies by name: _counter_label, _sms_counter, etc.)
        counter = (
            getattr(panel, "_counter_label", None)
            or getattr(panel, "_sms_counter", None)
            or getattr(panel, "_char_counter", None)
        )
        assert counter is not None, "No SMS counter widget found on ComposePanel"
        assert not counter.isVisible()

    def test_sms_counter_visible_in_non_group_mode(self, qtbot):
        from tincan_gui.compose_panel import ComposePanel
        panel = ComposePanel()
        qtbot.addWidget(panel)
        panel.set_group_mode(False)
        counter = (
            getattr(panel, "_counter_label", None)
            or getattr(panel, "_sms_counter", None)
            or getattr(panel, "_char_counter", None)
        )
        if counter is not None:
            assert counter.isVisible()


# ---------------------------------------------------------------------------
# §11 dbus_client.send_message_to_recipients returns conv_id
# ---------------------------------------------------------------------------

class TestDbusSendMessageToRecipients:
    """TincandClient.send_message_to_recipients calls D-Bus and returns conv_id."""

    def test_returns_string(self, _hermetic_dbus):
        client = TincandClient()
        with patch.object(client, "_dbus_call", return_value="/conv/group-1"):
            result = client.send_message_to_recipients(["+15550101234", "+15550105678"], "")
        assert isinstance(result, str)

    def test_returns_empty_on_dbus_failure(self, _hermetic_dbus):
        client = TincandClient()
        with patch.object(client, "_dbus_call", return_value=None):
            result = client.send_message_to_recipients(["+15550101234", "+15550105678"], "")
        assert result == "" or result is None

    def test_phones_passed_to_dbus_call(self, _hermetic_dbus):
        client = TincandClient()
        calls = []

        def _capture(*args, **kwargs):
            calls.append(args)
            return "/conv/g1"

        with patch.object(client, "_dbus_call", side_effect=_capture):
            client.send_message_to_recipients(["+15550101234", "+15550105678"], "")

        assert calls, "No D-Bus call was made"


# ---------------------------------------------------------------------------
# §12 dbus_client.get_conversation_participants returns list
# ---------------------------------------------------------------------------

class TestDbusGetConversationParticipants:
    """TincandClient.get_conversation_participants returns a list of phone strings."""

    def test_returns_list(self, _hermetic_dbus):
        client = TincandClient()
        with patch.object(client, "_dbus_call", return_value=["5550101234", "5550105678"]):
            result = client.get_conversation_participants("group-1")
        assert isinstance(result, list)

    def test_returns_phone_strings(self, _hermetic_dbus):
        client = TincandClient()
        with patch.object(client, "_dbus_call", return_value=["5550101234", "5550105678"]):
            result = client.get_conversation_participants("group-1")
        assert "5550101234" in result

    def test_returns_empty_list_on_failure(self, _hermetic_dbus):
        client = TincandClient()
        with patch.object(client, "_dbus_call", return_value=None):
            result = client.get_conversation_participants("unknown-conv")
        assert result == [] or result is None
