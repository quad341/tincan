"""pytest-qt GUI-driving harness (tincan-8wr26).

Drives real widgets against a fake daemon, simulating user actions (keystrokes,
mouse clicks, signal firings) and asserting signals, state, and call-counts.
Closes the gate hole where backend unit tests pass but live GUI behaviors
are broken.

Coverage:
  §1  Send call-count
      §1a  single Send-button click → send_message_async called once
      §1b  rapid double widget-click (input cleared by first) → one D-Bus call
      §1c  Enter key in compose input → exactly one D-Bus call
      §1d  empty input on button click → no D-Bus call
      §1e  double _on_send call while in-flight (guard via method) → one D-Bus call

  §2  Notification Reply → window focus/activate
      §2a  "reply" action_id routes to on_action_invoked callback
      §2b  on_notification_clicked calls raise_() on MainWindow
      §2c  on_notification_clicked calls activateWindow() on MainWindow
      §2d  "mark-read" fires on_mark_read, not on_action_invoked

  §3  Send button enabled/disabled state (via real widget wiring)
      §3a  no conversation selected → send button disabled on construction
      §3b  _apply_capabilities(messages=False) → button disabled
      §3c  valid conversation + dialable phone + messages_ok → button enabled

  §4  Contact list filters on keystroke (real key events, not .setText)
      §4a  keyClicks on search widget filters by name
      §4b  keyClicks on search widget filters by phone digits
      §4c  Backspace removes one character and widens filter
      §4d  Escape key clears the search field

  §5  Date separator layout position
      §5a  separator layout-index is strictly less than the first message of the new day
      §5b  separator layout-index is strictly greater than the last message of the previous day
      §5c  same-day messages have no separator between them in the layout
"""
from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSystemTrayIcon

from tincan_gui.conversation_list import ConversationData, ConversationListWidget
from tincan_gui.dbus_client import TincandClient
from tincan_gui.main import MainWindow
from tincan_gui.notifications import DesktopNotifier
from tincan_gui.thread_view import BubbleType, MessageData, ThreadView


# ---------------------------------------------------------------------------
# Global autouse fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _no_tray_show():
    with patch.object(QSystemTrayIcon, "show"):
        yield


@pytest.fixture(autouse=True)
def _no_live_daemon(monkeypatch):
    monkeypatch.setattr(TincandClient, "get_status", lambda self: {})
    monkeypatch.setattr(TincandClient, "get_messages", lambda self, cid: [])
    monkeypatch.setattr(TincandClient, "list_conversations", lambda self: [])
    monkeypatch.setattr(TincandClient, "mark_conversation_read", lambda self, cid: None)
    monkeypatch.setattr(TincandClient, "fetch_contact_photo", lambda self, cid: None)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_window(
    qtbot,
    *,
    phone: str = "+15550001",
    messages_ok: bool = True,
) -> MainWindow:
    """Return a MainWindow wired for testing.

    Sets a current conversation and messaging state, then syncs compose so
    all button-enabled assertions reflect a known baseline.
    """
    win = MainWindow()
    qtbot.addWidget(win)
    win._dbus_client.send_message_async = MagicMock()
    if phone:
        data = ConversationData(
            id=phone, name=phone, phone=phone,
            preview="", timestamp="", preview_direction="inbound",
        )
        win._conversations_by_id[phone] = data
        win._current_phone = phone
        win._current_phone_dialable = True
    win._messages_ok = messages_ok
    win._sync_compose_state()
    return win


def _make_conv(name: str, phone: str) -> ConversationData:
    return ConversationData(
        id=phone, name=name, phone=phone, preview="hi", timestamp="10:00",
        preview_direction="inbound",
    )


def _make_msg(body: str, d: datetime.date, hour: int = 10) -> MessageData:
    sort_key = d.strftime("%Y%m%d") + f"T{hour:02d}0000"
    return MessageData(
        bubble_type=BubbleType.INBOUND,
        body=body,
        sender="Alice",
        timestamp=f"{hour:02d}:00",
        sort_key=sort_key,
    )


def _layout_items(view: ThreadView) -> list:
    """Return all widgets in the thread messages layout in order."""
    layout = view._messages_layout
    widgets = []
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item is not None and item.widget() is not None:
            widgets.append(item.widget())
    return widgets


# ---------------------------------------------------------------------------
# §1  Send call-count — real widget actions
# ---------------------------------------------------------------------------

class TestSendCallCount:
    """Send button and Enter key each trigger exactly one D-Bus call."""

    def test_single_button_click_calls_send_once(self, qtbot):
        """Clicking Send once with text typed → send_message_async called exactly once."""
        win = _make_window(qtbot)
        qtbot.keyClicks(win._compose._input, "hello")
        qtbot.mouseClick(win._compose._send_btn, Qt.MouseButton.LeftButton)

        assert win._dbus_client.send_message_async.call_count == 1, (
            f"Expected 1 send call, got {win._dbus_client.send_message_async.call_count}"
        )

    def test_second_button_click_after_input_cleared_is_noop(self, qtbot):
        """After the first click clears the input, a second click does nothing."""
        win = _make_window(qtbot)
        qtbot.keyClicks(win._compose._input, "hello")
        qtbot.mouseClick(win._compose._send_btn, Qt.MouseButton.LeftButton)
        # Input is cleared by first click; second click finds empty text
        qtbot.mouseClick(win._compose._send_btn, Qt.MouseButton.LeftButton)

        assert win._dbus_client.send_message_async.call_count == 1, (
            "Second click on Send with empty input should not trigger a D-Bus call"
        )

    def test_enter_key_in_compose_calls_send_once(self, qtbot):
        """Pressing Enter in the compose input emits send exactly once."""
        win = _make_window(qtbot)
        qtbot.keyClicks(win._compose._input, "via keyboard")
        qtbot.keyClick(win._compose._input, Qt.Key.Key_Return)

        assert win._dbus_client.send_message_async.call_count == 1, (
            f"Expected 1 send call via Enter key, got "
            f"{win._dbus_client.send_message_async.call_count}"
        )

    def test_button_click_with_empty_input_does_not_call_send(self, qtbot):
        """Clicking Send with no typed text → no D-Bus call."""
        win = _make_window(qtbot)
        qtbot.mouseClick(win._compose._send_btn, Qt.MouseButton.LeftButton)

        assert win._dbus_client.send_message_async.call_count == 0, (
            "Send button click with empty input should not call send_message_async"
        )

    def test_double_submit_guard_via_on_send_method(self, qtbot):
        """Calling _on_send twice with same text while in-flight → one D-Bus call.

        Simulates rapid duplicate submit (e.g. double Enter from a key-repeat
        event before the pending guard clears).
        """
        win = _make_window(qtbot)
        win._on_send("guard test")
        win._on_send("guard test")  # same text, same phone, guard should block

        assert win._dbus_client.send_message_async.call_count == 1, (
            "Double _on_send with same (phone, text) while in-flight should fire only once"
        )

    def test_send_target_phone_is_current_conversation(self, qtbot):
        """The D-Bus call is addressed to the current conversation's phone number."""
        phone = "+15559998877"
        win = _make_window(qtbot, phone=phone)
        qtbot.keyClicks(win._compose._input, "targeted")
        qtbot.mouseClick(win._compose._send_btn, Qt.MouseButton.LeftButton)

        assert win._dbus_client.send_message_async.call_count == 1
        to_arg = win._dbus_client.send_message_async.call_args[0][0]
        assert to_arg == phone, (
            f"send_message_async called with '{to_arg}', expected '{phone}'"
        )


# ---------------------------------------------------------------------------
# §2  Notification Reply → window focus/activate
# ---------------------------------------------------------------------------

class TestNotificationReplyFocusActivate:
    """Notification Reply action must cascade through to raise_() + activateWindow()."""

    def test_reply_action_id_invokes_on_action_invoked_callback(self):
        """DesktopNotifier routes 'reply' action_id to the on_action_invoked callback."""
        received = []
        notifier = DesktopNotifier(on_action_invoked=lambda cid: received.append(cid))
        notifier._notif_to_conv[7] = "conv-alice"

        notifier._on_action_invoked_signal(7, "reply")

        assert received == ["conv-alice"], (
            f"'reply' action_id did not invoke on_action_invoked callback — "
            f"received: {received}"
        )

    def test_reply_action_id_does_not_fire_on_mark_read(self):
        """'reply' must NOT trigger the mark-read callback."""
        mark_read_calls = []
        notifier = DesktopNotifier(
            on_action_invoked=lambda cid: None,
            on_mark_read=lambda cid: mark_read_calls.append(cid),
        )
        notifier._notif_to_conv[7] = "conv-alice"

        notifier._on_action_invoked_signal(7, "reply")

        assert mark_read_calls == [], (
            f"'reply' action must not invoke on_mark_read — called with: {mark_read_calls}"
        )

    def test_on_notification_clicked_calls_raise(self, qtbot):
        """_on_notification_clicked calls raise_() to bring window to foreground."""
        win = _make_window(qtbot)
        with patch.object(win, "raise_") as mock_raise:
            win._on_notification_clicked("conv-alice")

        mock_raise.assert_called_once(), "raise_() must be called when notification is clicked"

    def test_on_notification_clicked_calls_activate_window(self, qtbot):
        """_on_notification_clicked calls activateWindow() to focus the application."""
        win = _make_window(qtbot)
        with patch.object(win, "activateWindow") as mock_activate:
            win._on_notification_clicked("conv-alice")

        mock_activate.assert_called_once(), (
            "activateWindow() must be called when notification is clicked"
        )

    def test_mark_read_action_fires_on_mark_read_not_focus(self):
        """'mark-read' action triggers on_mark_read callback, not on_action_invoked."""
        action_invoked_calls = []
        mark_read_calls = []
        notifier = DesktopNotifier(
            on_action_invoked=lambda cid: action_invoked_calls.append(cid),
            on_mark_read=lambda cid: mark_read_calls.append(cid),
        )
        notifier._notif_to_conv[5] = "conv-bob"

        notifier._on_action_invoked_signal(5, "mark-read")

        assert mark_read_calls == ["conv-bob"], (
            f"mark-read action must invoke on_mark_read — got: {mark_read_calls}"
        )
        assert action_invoked_calls == [], (
            f"mark-read must not invoke on_action_invoked — got: {action_invoked_calls}"
        )

    def test_mark_read_on_empty_conv_id_does_nothing(self):
        """mark-read for a notification with no conv_id must not call on_mark_read."""
        mark_read_calls = []
        notifier = DesktopNotifier(
            on_mark_read=lambda cid: mark_read_calls.append(cid),
        )
        notifier._notif_to_conv[9] = ""  # no conv_id (ANCS app notification)

        notifier._on_action_invoked_signal(9, "mark-read")

        assert mark_read_calls == [], (
            "mark-read with empty conv_id must not invoke on_mark_read"
        )


# ---------------------------------------------------------------------------
# §3  Send button enabled/disabled state
# ---------------------------------------------------------------------------

class TestSendButtonEnabledState:
    """Send button reflects messaging availability and conversation selection."""

    def test_no_conversation_selected_disables_send_button(self, qtbot):
        """Without a selected conversation the send button must be disabled."""
        win = MainWindow()
        qtbot.addWidget(win)
        # No _current_phone set — _sync_compose_state runs in __init__
        assert not win._compose.send_button.isEnabled(), (
            "Send button must be disabled when no conversation is selected"
        )

    def test_messaging_unavailable_disables_send_button(self, qtbot):
        """After _apply_capabilities(messages=False) the button is disabled."""
        win = _make_window(qtbot)
        assert win._compose.send_button.isEnabled(), "Precondition: button should be enabled"

        win._apply_capabilities({"messages": False, "ancs": False})

        assert not win._compose.send_button.isEnabled(), (
            "Send button must be disabled when messaging capability is unavailable"
        )

    def test_valid_conversation_with_dialable_phone_enables_button(self, qtbot):
        """With messaging_ok + conversation + dialable phone, button must be enabled."""
        win = _make_window(qtbot, messages_ok=True)

        assert win._compose.send_button.isEnabled(), (
            "Send button must be enabled when conversation is selected and messaging is OK"
        )

    def test_non_dialable_phone_disables_send_button(self, qtbot):
        """A conversation whose phone is not dialable disables the send button."""
        win = _make_window(qtbot)
        win._current_phone_dialable = False
        win._sync_compose_state()

        assert not win._compose.send_button.isEnabled(), (
            "Send button must be disabled when the conversation phone is not dialable"
        )

    def test_messaging_restored_reenables_send_button(self, qtbot):
        """After capabilities are restored the send button is re-enabled."""
        win = _make_window(qtbot)
        win._apply_capabilities({"messages": False, "ancs": False})
        assert not win._compose.send_button.isEnabled(), "Precondition: button should be off"

        win._apply_capabilities({"messages": True, "ancs": False})

        assert win._compose.send_button.isEnabled(), (
            "Send button must be re-enabled when messaging capability is restored"
        )


# ---------------------------------------------------------------------------
# §4  Contact list filters on keystroke
# ---------------------------------------------------------------------------

class TestContactListFilterOnKeystroke:
    """Conversation filter updates on real key events, not just programmatic setText."""

    def _make_list(self, qtbot, convs: list[ConversationData]) -> ConversationListWidget:
        w = ConversationListWidget()
        qtbot.addWidget(w)
        w.load_conversations(convs)
        return w

    def _visible_items(self, w: ConversationListWidget) -> list[ConversationData]:
        return [item._data for item in w._items if item.isVisible()]

    def test_keystrokes_on_search_field_filter_by_name(self, qtbot):
        """Typing characters into the search field via key events filters by name."""
        w = self._make_list(qtbot, [
            _make_conv("Alice", "+14155550001"),
            _make_conv("Bob", "+19175550002"),
        ])
        qtbot.keyClicks(w._search, "ali")

        visible = self._visible_items(w)
        assert len(visible) == 1, (
            f"Expected 1 visible conversation after typing 'ali', got {len(visible)}: "
            f"{[v.name for v in visible]}"
        )
        assert visible[0].name == "Alice"

    def test_keystrokes_on_search_field_filter_by_phone(self, qtbot):
        """Typing phone digits into the search field via key events filters by phone."""
        w = self._make_list(qtbot, [
            _make_conv("Alice", "+14155550001"),
            _make_conv("Bob", "+19175550002"),
        ])
        qtbot.keyClicks(w._search, "917")

        visible = self._visible_items(w)
        assert len(visible) == 1, (
            f"Expected 1 visible conversation after typing '917', got {len(visible)}: "
            f"{[v.name for v in visible]}"
        )
        assert visible[0].name == "Bob"

    def test_backspace_widens_filter(self, qtbot):
        """Pressing Backspace removes the last character and shows previously hidden items."""
        w = self._make_list(qtbot, [
            _make_conv("Alice", "+14155550001"),
            _make_conv("Bob", "+19175550002"),
        ])
        qtbot.keyClicks(w._search, "ali")
        assert len(self._visible_items(w)) == 1, "Precondition: 'ali' shows only Alice"

        qtbot.keyClick(w._search, Qt.Key.Key_Backspace)
        qtbot.keyClick(w._search, Qt.Key.Key_Backspace)
        qtbot.keyClick(w._search, Qt.Key.Key_Backspace)

        visible = self._visible_items(w)
        assert len(visible) == 2, (
            f"Backspace to empty should show all 2 conversations, got {len(visible)}"
        )

    def test_escape_key_clears_search_field(self, qtbot):
        """Pressing Escape clears the search input and shows all conversations."""
        w = self._make_list(qtbot, [
            _make_conv("Alice", "+14155550001"),
            _make_conv("Bob", "+19175550002"),
        ])
        qtbot.keyClicks(w._search, "ali")
        assert len(self._visible_items(w)) == 1, "Precondition: filter active"

        qtbot.keyClick(w._search, Qt.Key.Key_Escape)

        assert w._search.text() == "", (
            f"Escape must clear the search field, got: '{w._search.text()}'"
        )
        visible = self._visible_items(w)
        assert len(visible) == 2, (
            f"After Escape, all conversations must be visible, got {len(visible)}"
        )

    def test_no_match_keystrokes_shows_no_results_label(self, qtbot):
        """Typing a non-matching string via key events shows the no-results label."""
        w = self._make_list(qtbot, [_make_conv("Alice", "+14155550001")])
        qtbot.keyClicks(w._search, "zzz")

        assert w._no_results.isVisible(), (
            "No-results label must be visible when filter matches nothing"
        )

    def test_matching_keystrokes_hides_no_results_label(self, qtbot):
        """Typing a matching string after a non-match hides the no-results label."""
        w = self._make_list(qtbot, [_make_conv("Alice", "+14155550001")])
        qtbot.keyClicks(w._search, "zzz")
        assert w._no_results.isVisible(), "Precondition: no-results visible"

        qtbot.keyClick(w._search, Qt.Key.Key_Escape)  # clear "zzz"
        qtbot.keyClicks(w._search, "ali")

        assert not w._no_results.isVisible(), (
            "No-results label must be hidden when filter has a match"
        )


# ---------------------------------------------------------------------------
# §5  Date separator layout position
# ---------------------------------------------------------------------------

_TODAY = datetime.date(2026, 6, 5)
_YESTERDAY = _TODAY - datetime.timedelta(days=1)
_TWO_DAYS_AGO = _TODAY - datetime.timedelta(days=2)


class TestDateSeparatorLayoutPosition:
    """DateSeparator widgets must appear at the correct index in the layout.

    The separator for day D must come AFTER all messages from the previous day
    and BEFORE the first message from day D.
    """

    def _sep_and_bubble_indices(self, view: ThreadView):
        """Return (sep_indices, bubble_indices) by layout position."""
        from tincan_gui.thread_view import DateSeparatorWidget, MessageBubble
        seps = []
        bubbles = []
        for i, w in enumerate(_layout_items(view)):
            if isinstance(w, DateSeparatorWidget):
                seps.append(i)
            elif isinstance(w, MessageBubble):
                bubbles.append(i)
        return seps, bubbles

    def test_separator_index_less_than_new_day_first_message(self, qtbot):
        """Separator for day 2 must appear at a lower layout index than day-2's first message."""
        view = ThreadView()
        qtbot.addWidget(view)
        with patch("tincan_gui.thread_view._get_today", return_value=_TODAY):
            view.load_thread("Alice", "+1555", [
                _make_msg("old msg", _YESTERDAY),
                _make_msg("new msg", _TODAY),
            ])

        seps, bubbles = self._sep_and_bubble_indices(view)
        assert len(seps) == 1, f"Expected 1 separator, got {len(seps)}"
        assert len(bubbles) == 2, f"Expected 2 bubbles, got {len(bubbles)}"
        # Layout order must be: bubble(yesterday) < separator < bubble(today)
        assert seps[0] > bubbles[0], (
            f"Separator (index {seps[0]}) must come after yesterday's bubble "
            f"(index {bubbles[0]})"
        )
        assert seps[0] < bubbles[1], (
            f"Separator (index {seps[0]}) must come before today's bubble "
            f"(index {bubbles[1]})"
        )

    def test_separator_index_greater_than_previous_day_last_message(self, qtbot):
        """The separator must appear AFTER the last message from the previous day."""
        view = ThreadView()
        qtbot.addWidget(view)
        with patch("tincan_gui.thread_view._get_today", return_value=_TODAY):
            view.load_thread("Alice", "+1555", [
                _make_msg("msg1 yesterday", _YESTERDAY, 9),
                _make_msg("msg2 yesterday", _YESTERDAY, 10),
                _make_msg("msg1 today", _TODAY, 11),
            ])

        seps, bubbles = self._sep_and_bubble_indices(view)
        assert len(seps) == 1, f"Expected 1 separator, got {len(seps)}"
        # Layout: bubble(y9) < bubble(y10) < separator < bubble(t11)
        yesterday_bubble_indices = bubbles[:2]
        today_bubble_index = bubbles[2]
        sep_index = seps[0]
        assert all(sep_index > idx for idx in yesterday_bubble_indices), (
            f"Separator (index {sep_index}) must appear after both yesterday's "
            f"messages (indices {yesterday_bubble_indices})"
        )
        assert sep_index < today_bubble_index, (
            f"Separator (index {sep_index}) must appear before today's message "
            f"(index {today_bubble_index})"
        )

    def test_same_day_messages_have_no_separator_between_them(self, qtbot):
        """Multiple messages from the same day must have no separator in between."""
        view = ThreadView()
        qtbot.addWidget(view)
        with patch("tincan_gui.thread_view._get_today", return_value=_TODAY):
            view.load_thread("Alice", "+1555", [
                _make_msg("morning", _TODAY, 8),
                _make_msg("noon", _TODAY, 12),
                _make_msg("evening", _TODAY, 18),
            ])

        seps, bubbles = self._sep_and_bubble_indices(view)
        assert seps == [], (
            f"No separators expected for same-day messages, found at indices: {seps}"
        )
        assert len(bubbles) == 3

    def test_two_day_boundaries_produce_two_separators_in_order(self, qtbot):
        """Three messages spanning three days produce two separators in correct order."""
        view = ThreadView()
        qtbot.addWidget(view)
        with patch("tincan_gui.thread_view._get_today", return_value=_TODAY):
            view.load_thread("Alice", "+1555", [
                _make_msg("two days ago", _TWO_DAYS_AGO),
                _make_msg("yesterday", _YESTERDAY),
                _make_msg("today", _TODAY),
            ])

        seps, bubbles = self._sep_and_bubble_indices(view)
        assert len(seps) == 2, f"Expected 2 separators for 3-day span, got {len(seps)}"
        assert len(bubbles) == 3
        # Layout must be strictly interleaved:
        # bubble[0] < sep[0] < bubble[1] < sep[1] < bubble[2]
        assert bubbles[0] < seps[0] < bubbles[1], (
            f"First separator {seps[0]} must be between bubble[0]={bubbles[0]} "
            f"and bubble[1]={bubbles[1]}"
        )
        assert bubbles[1] < seps[1] < bubbles[2], (
            f"Second separator {seps[1]} must be between bubble[1]={bubbles[1]} "
            f"and bubble[2]={bubbles[2]}"
        )

    def test_append_message_separator_at_correct_index(self, qtbot):
        """append_message inserts separator immediately before the new-day bubble."""
        from tincan_gui.thread_view import DateSeparatorWidget, MessageBubble
        view = ThreadView()
        qtbot.addWidget(view)
        with patch("tincan_gui.thread_view._get_today", return_value=_TODAY):
            view.load_thread("Alice", "+1555", [_make_msg("yesterday msg", _YESTERDAY)])
            view.append_message(_make_msg("today msg", _TODAY))

        seps, bubbles = self._sep_and_bubble_indices(view)
        assert len(seps) == 1, f"Expected 1 separator after day-crossing append, got {len(seps)}"
        # The separator must be immediately before the last bubble
        assert seps[0] == bubbles[-1] - 1, (
            f"Separator index {seps[0]} should be immediately before last bubble "
            f"index {bubbles[-1]} (expected {bubbles[-1] - 1})"
        )
