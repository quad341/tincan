"""Behavioral integration tests: user-visible flows (tincan-iplg1, tincan-0an0b).

These tests assert user-visible behavior for flows that were shipping broken.
Each test uses FakeMapBackend-compatible patterns and targets the GUI component
boundaries WITHOUT a real D-Bus connection.

ALL tests in this file must FAIL against the current branch code and become
regression guards once the bugs are fixed.

Coverage (acceptance criteria from tincan-iplg1):
  §1 cache-as-source     — sent message appears in thread after reload
  §2 self-convo-live     — self-message shows BOTH sent bubble AND inbound bubble
  §3 send-fail-status    — failed send shows '⚠ Failed' in thread immediately
  §4 send-fail-reload    — '⚠ Failed' state preserved after thread navigation
  §5 failed-notif-scope  — send-error bar is scoped to its conversation
  §6 contact-names       — contact name resolved via ConversationUpdated shows in header
  §7 inline-image        — MMS attachment produces image or download affordance
  §8 no-duplicate-reload — ISO-ts daemon echo is deduped to 1 bubble (tincan-0an0b)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QLabel, QPushButton, QSystemTrayIcon

from tincan_gui.conversation_list import ConversationData
from tincan_gui.dbus_client import TincandClient
from tincan_gui.main import MainWindow
from tincan_gui.message_cache import MessageCache


# ---------------------------------------------------------------------------
# Fixtures and helpers
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


def _make_window(qtbot, *, tmp_path=None, phone: str = "+15550001") -> MainWindow:
    """Create a MainWindow with one conversation loaded and selected."""
    win = MainWindow()
    if tmp_path:
        win._msg_cache = MessageCache(cache_dir=tmp_path)
    qtbot.addWidget(win)
    win._dbus_client.send_message_async = MagicMock()
    data = ConversationData(
        id=phone, name=phone, phone=phone,
        preview="", timestamp="", preview_direction="inbound",
    )
    win._conversations_by_id[phone] = data
    win._current_phone = phone
    win._current_phone_dialable = True
    win._messages_ok = True
    return win


def _visible_bubble_texts(win: MainWindow) -> list[str]:
    """Return meta-label text for every MessageBubble in the thread view."""
    from tincan_gui.thread_view import MessageBubble
    layout = win._thread_view._messages_layout
    texts = []
    for i in range(layout.count()):
        w = layout.itemAt(i).widget()
        if isinstance(w, MessageBubble):
            texts.append(w._meta_label.text())
    return texts


def _bubble_widgets(win: MainWindow):
    """Return all MessageBubble widgets in the thread view."""
    from tincan_gui.thread_view import MessageBubble
    layout = win._thread_view._messages_layout
    return [
        layout.itemAt(i).widget()
        for i in range(layout.count())
        if isinstance(layout.itemAt(i).widget(), MessageBubble)
    ]


# ---------------------------------------------------------------------------
# §1  cache-as-source — sent message appears in thread after reload
# ---------------------------------------------------------------------------

class TestCacheAsSource:
    """Sent messages must appear in thread after navigation (cache is the source)."""

    def test_sent_message_appears_after_thread_reload(self, qtbot, tmp_path):
        """After sending, navigating away and back should show the sent message."""
        win = _make_window(qtbot, tmp_path=tmp_path)

        win._on_send("Hello from cache test")
        assert len(_bubble_widgets(win)) >= 1, "optimistic bubble not appended on send"

        # Simulate navigating away by loading an empty thread
        win._thread_view.load_thread("+15550001", "+15550001", [], "SMS")
        assert _bubble_widgets(win) == [], "thread should be empty after clearing"

        # Reload from cache (what _on_conversation_selected deferred calls)
        win._load_thread_messages("+15550001", "+15550001")

        bubbles = _bubble_widgets(win)
        bodies = [b._data.body for b in bubbles]
        assert "Hello from cache test" in bodies, (
            f"sent message not visible after reload — bubbles: {bodies}"
        )


# ---------------------------------------------------------------------------
# §2  self-convo-live — self-message shows BOTH sent AND inbound bubbles
# ---------------------------------------------------------------------------

class TestSelfConversationLive:
    """Sending to self must show both the sent bubble and the inbound echo."""

    def test_self_echo_shows_inbound_bubble(self, qtbot, tmp_path):
        """iOS MAP delivers a copy of self-sent messages to inbox as 'inbound'.
        The GUI must show this inbound copy so the thread shows both sides.
        """
        win = _make_window(qtbot, tmp_path=tmp_path)

        win._on_send("Hey myself")
        sent_count = len(_bubble_widgets(win))

        # Simulate the iOS MAP echo arriving as an inbound message
        win._on_message_received({
            "direction": "inbound",
            "body": "Hey myself",
            "conversation_id": "+15550001",
            "sender": "+15550001",
            "timestamp": "20260606T120001",
        })

        all_bubbles = _bubble_widgets(win)
        assert len(all_bubbles) > sent_count, (
            f"inbound self-echo was suppressed — still {len(all_bubbles)} bubble(s), "
            f"expected {sent_count + 1}"
        )

    def test_self_echo_inbound_bubble_type(self, qtbot, tmp_path):
        """The echo bubble must be INBOUND so the conversation looks like two sides."""
        from tincan_gui.thread_view import BubbleType
        win = _make_window(qtbot, tmp_path=tmp_path)

        win._on_send("Ping")
        win._on_message_received({
            "direction": "inbound",
            "body": "Ping",
            "conversation_id": "+15550001",
            "sender": "+15550001",
            "timestamp": "20260606T120001",
        })

        types = [b._data.bubble_type for b in _bubble_widgets(win)]
        assert BubbleType.INBOUND in types, (
            f"no INBOUND bubble after self-echo — types: {types}"
        )


# ---------------------------------------------------------------------------
# §3  send-fail-status — failed send shows '⚠ Failed' immediately
# ---------------------------------------------------------------------------

class TestSendFailStatus:
    """After a send failure, the last outbound bubble must show '⚠ Failed'."""

    def test_failed_bubble_shows_failed_marker(self, qtbot, tmp_path):
        win = _make_window(qtbot, tmp_path=tmp_path)

        win._on_send("Will fail")
        win._on_send_failed("+15550001", "Will fail")

        texts = _visible_bubble_texts(win)
        assert any("Failed" in t for t in texts), (
            f"⚠ Failed not visible in bubbles after send failure — texts: {texts}"
        )

    def test_failed_bubble_not_marked_sent(self, qtbot, tmp_path):
        win = _make_window(qtbot, tmp_path=tmp_path)

        win._on_send("Will fail")
        win._on_send_failed("+15550001", "Will fail")

        texts = _visible_bubble_texts(win)
        # The bubble should NOT show "Sent ✓" after failure
        assert not any("Sent ✓" in t for t in texts), (
            f"bubble still shows 'Sent ✓' after send failure — texts: {texts}"
        )


# ---------------------------------------------------------------------------
# §4  send-fail-reload — failed state preserved after thread navigation
# ---------------------------------------------------------------------------

class TestSendFailAfterReload:
    """After a send failure, navigating away and back must still show ⚠ Failed."""

    def test_failed_state_visible_after_reload(self, qtbot, tmp_path):
        """The ⚠ Failed marker must survive load_thread (thread navigation).

        Current bug: load_thread rebuilds all bubbles from MessageData, which
        has no concept of 'failed' state.  The reloaded bubble shows 'Sent ✓'.
        """
        win = _make_window(qtbot, tmp_path=tmp_path)

        win._on_send("Failing message")
        win._on_send_failed("+15550001", "Failing message")

        # Simulate navigating away (load_thread clears all bubbles and _last_outbound)
        win._load_thread_messages("+15550001", "+15550001")

        texts = _visible_bubble_texts(win)
        assert any("Failed" in t for t in texts), (
            f"⚠ Failed lost after load_thread — texts: {texts}"
        )


# ---------------------------------------------------------------------------
# §5  failed-notif-scope — send-error bar does not bleed across conversations
# ---------------------------------------------------------------------------

class TestFailedNotifScope:
    """The send-error bar shown for a failed send must be hidden when switching."""

    def test_error_bar_hidden_when_switching_conversation(self, qtbot, tmp_path):
        """After a send failure in conv A, switching to conv B must clear the error.

        Current bug: _on_conversation_selected does not call hide_send_error,
        so the error bar persists to the next conversation.
        """
        win = _make_window(qtbot, tmp_path=tmp_path, phone="+15550001")

        # Register a second conversation
        phone_b = "+15550002"
        data_b = ConversationData(
            id=phone_b, name=phone_b, phone=phone_b,
            preview="", timestamp="", preview_direction="inbound",
        )
        win._conversations_by_id[phone_b] = data_b

        # Fail a send in conv A — use not isHidden() since window isn't shown on screen
        win._on_send_failed("+15550001", "failed text")
        assert not win._compose._error_bar.isHidden(), (
            "error bar should not be hidden after send failure"
        )

        # Switch to conv B — error bar must be hidden
        win._on_conversation_selected(phone_b)

        assert win._compose._error_bar.isHidden(), (
            "send-error bar from conv A is not hidden after switching to conv B "
            "(notification scope bleed)"
        )


# ---------------------------------------------------------------------------
# §6  contact-names — resolved name shows in thread header
# ---------------------------------------------------------------------------

class TestContactNamesResolve:
    """After PBAP resolves a contact name, the thread header must show the name."""

    def test_resolved_name_shown_in_thread_header(self, qtbot, tmp_path):
        """When ConversationUpdated fires with a resolved display_name, the open
        thread header must update to show the name (not the phone number).

        Current bug: _on_conversation_updated updates _conversations_by_id but
        does not call _thread_view to update the already-visible header.
        """
        win = _make_window(qtbot, tmp_path=tmp_path, phone="+15550001")

        # Load the thread with the phone number as name (before PBAP resolves it)
        win._thread_view.load_thread("+15550001", "+15550001", [], "SMS")
        header_before = win._thread_view._header._name_label.text()
        assert "+15550001" in header_before or header_before != "Alice", (
            "Expected phone number in header before name resolution"
        )

        # Simulate PBAP-resolved ConversationUpdated signal
        win._on_conversation_updated({
            "id": "+15550001",
            "display_name": "Alice",
            "last_message_preview": "",
            "last_message_at": "",
            "unread_count": 0,
            "last_message_direction": "",
        })

        header_after = win._thread_view._header._name_label.text()
        assert header_after == "Alice", (
            f"Thread header still shows '{header_after}' instead of 'Alice' "
            f"after ConversationUpdated (contact name not propagated to open thread)"
        )


# ---------------------------------------------------------------------------
# §7  inline-image — MMS attachment shows image or download affordance
# ---------------------------------------------------------------------------

class TestInlineImage:
    """MMS messages with image attachments must show an image or download button."""

    def test_mms_attachment_shows_affordance(self, qtbot, tmp_path):
        """A received MMS with an image attachment must render either an inline
        image OR a '↓ Save image' / download button.

        Current bug: MessageData has no 'attachments' field; _on_message_received
        ignores attachment data; MessageBubble._build() has no image rendering.
        Attachment is silently dropped — no visual affordance.
        """
        win = _make_window(qtbot, tmp_path=tmp_path)

        import base64
        # 1×1 white JPEG in base64
        tiny_jpeg_b64 = (
            "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8U"
            "HRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgN"
            "DRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL"
            "/wAARCAABAAEDASIAAhEBAxEB/8QAFgABAQEAAAAAAAAAAAAAAAAABgUEB"
            "/8QAIBAAAgIBBQEBAAAAAAAAAAAAAQIDBAUREiExQf/EABQBAQAAAAAAAAAAAAAAAAAAAAD"
            "/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCjlBp1x0m1D2WQPN0SVQY5"
            "ybWBz8gA//Z"
        )
        win._on_message_received({
            "direction": "inbound",
            "body": "",
            "conversation_id": "+15550001",
            "sender": "+15550002",
            "timestamp": "20260606T120000",
            "msg_type": "MMS",
            "attachments": [{"mime_type": "image/jpeg", "data": tiny_jpeg_b64}],
        })

        bubbles = _bubble_widgets(win)
        assert bubbles, "no bubble created for MMS message"

        bubble = bubbles[-1]

        # Check if there's either a QLabel with an image pixmap or a QPushButton
        # (download button). Either would be an acceptable affordance.
        has_image = any(
            isinstance(w, QLabel) and not w.pixmap().isNull()
            for w in bubble.findChildren(QLabel)
        )
        has_download_btn = any(
            isinstance(w, QPushButton) and ("save" in w.text().lower() or "↓" in w.text())
            for w in bubble.findChildren(QPushButton)
        )
        assert has_image or has_download_btn, (
            "MMS attachment produced no inline image and no download button — "
            "attachment data was silently dropped"
        )


# ---------------------------------------------------------------------------
# §8  no-duplicate-reload — ISO-ts daemon echo deduped to 1 bubble (tincan-0an0b)
# ---------------------------------------------------------------------------

class TestNoDuplicateAfterReload:
    """Daemon outbound echo with ISO sort_key matching cache must show exactly 1 bubble.

    Bug tincan-0an0b (root cause 1): daemon stored 'HH:MM' timestamps;
    _load_thread_messages _dk = (bubble_type, sort_key) produced different keys
    for the same logical message → both cache entry and daemon echo showed.
    """

    def test_single_bubble_when_daemon_echo_has_matching_sort_key(self, qtbot, tmp_path):
        """After send + thread reload with ISO-ts daemon echo: exactly 1 bubble."""
        win = _make_window(qtbot, tmp_path=tmp_path)
        phone = "+15550001"
        body = "No duplicate test"

        win._on_send(body)
        assert len(_bubble_widgets(win)) == 1, "should start with 1 optimistic bubble"

        cached = win._msg_cache.get_messages(phone)
        sort_key = cached[0]["sort_key"] if cached else "20260606T143000"

        daemon_messages = [{
            "direction": "outbound",
            "body": body,
            "timestamp": sort_key,
            "conversation_id": phone,
            "sender": "",
        }]

        win._thread_view.load_thread(phone, phone, [], "SMS")
        assert _bubble_widgets(win) == [], "thread should be empty after clearing"

        with patch.object(win._dbus_client, "get_messages", return_value=daemon_messages):
            win._load_thread_messages(phone, phone)

        bubbles = _bubble_widgets(win)
        assert len(bubbles) == 1, (
            f"Expected 1 bubble but got {len(bubbles)} — "
            f"daemon echo with matching ISO timestamp was not deduplicated.\n"
            f"Bodies: {[b._data.body for b in bubbles]}"
        )


# ---------------------------------------------------------------------------
# §9  long-unbroken-wrap — 200-char unbroken body wraps instead of clipping
# (tincan-schbs)
# ---------------------------------------------------------------------------

class TestLongUnbrokenWrap:
    """A 200-char unbroken string must wrap inside the bubble, not be clipped.

    Bug tincan-schbs: body_label.minimumSizeHint().width() returned the full
    natural text width (~1600px).  Qt layout honored that minimum, making the
    bubble wider than the viewport.  With horizontal scrollbar disabled, the
    overflow was clipped and the message body was invisible past a certain point.
    """

    def test_body_label_minimum_width_is_zero(self, qtbot, tmp_path):
        """body_label.minimumWidth() must be 0 so the layout can constrain it."""
        win = _make_window(qtbot, tmp_path=tmp_path)
        win._on_message_received({
            "direction": "inbound",
            "body": "a" * 200,
            "conversation_id": "+15550001",
            "sender": "+15550002",
            "timestamp": "20260606T120000",
        })
        bubbles = _bubble_widgets(win)
        assert bubbles, "no bubble created for 200-char message"
        body_label = bubbles[-1]._body_label
        assert body_label.minimumWidth() == 0, (
            f"body_label.minimumWidth() = {body_label.minimumWidth()}, expected 0.\n"
            f"Non-zero minimum width lets the bubble overflow the viewport → text clipped."
        )

    def test_body_label_wraps_at_narrow_width(self, qtbot, tmp_path):
        """heightForWidth(300) must be > single-line height for a 200-char body."""
        win = _make_window(qtbot, tmp_path=tmp_path)
        win._on_message_received({
            "direction": "inbound",
            "body": "a" * 200,
            "conversation_id": "+15550001",
            "sender": "+15550002",
            "timestamp": "20260606T120000",
        })
        bubbles = _bubble_widgets(win)
        assert bubbles, "no bubble created"
        body_label = bubbles[-1]._body_label
        h = body_label.heightForWidth(300)
        # At 300px, 200 'a's at 13pt should span 4+ lines; each line ≥ 15px → >45px
        assert h > 30, (
            f"heightForWidth(300) = {h}px — expected >30px for a 200-char body at 300px width.\n"
            f"Text is not wrapping; it will be clipped in the thread view."
        )
