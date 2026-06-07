"""Reproduction + regression guard for tincan-lcnyu (duplicate sent bubbles)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QSystemTrayIcon

from tincan_gui.conversation_list import ConversationData
from tincan_gui.dbus_client import TincandClient
from tincan_gui.main import MainWindow
from tincan_gui.message_cache import MessageCache


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


def _make_window(qtbot, *, tmp_path=None, phone="+15550001"):
    win = MainWindow()
    if tmp_path:
        win._msg_cache = MessageCache(cache_dir=tmp_path)
    qtbot.addWidget(win)
    win._dbus_client.send_message_async = MagicMock()
    win._conversations_by_id[phone] = ConversationData(
        id=phone, name=phone, phone=phone,
        preview="", timestamp="", preview_direction="inbound",
    )
    win._current_phone = phone
    win._current_phone_dialable = True
    win._messages_ok = True
    return win


def _outbound_bubbles(win):
    from tincan_gui.thread_view import MessageBubble
    layout = win._thread_view._messages_layout
    return [
        layout.itemAt(i).widget()._data.body
        for i in range(layout.count())
        if isinstance(layout.itemAt(i).widget(), MessageBubble)
        and layout.itemAt(i).widget()._data.body
    ]


PHONE = "+15550001"


class TestDivergentTimestampDuplicates:
    def test_daemon_echo_with_different_timestamp_duplicates_sent_bubble(self, qtbot, tmp_path):
        win = _make_window(qtbot, tmp_path=tmp_path)
        body = "Are you free tonight?"
        win._on_send(body)
        cached = win._msg_cache.get_messages(PHONE)
        optimistic_sk = cached[0]["sort_key"] if cached else "20260607T101500"
        divergent_ts = optimistic_sk[:-2] + f"{(int(optimistic_sk[-2:]) + 3) % 60:02d}"
        daemon_messages = [{
            "direction": "outbound", "body": body,
            "timestamp": divergent_ts, "conversation_id": PHONE, "sender": "",
        }]
        win._thread_view.load_thread(PHONE, PHONE, [], "SMS")
        with patch.object(win._dbus_client, "get_messages", return_value=daemon_messages):
            win._load_thread_messages(PHONE, PHONE)
        bubbles = _outbound_bubbles(win)
        assert bubbles.count(body) == 1, f"sent message duplicated on re-open: {bubbles}"

    def test_matching_timestamp_is_single_bubble_control(self, qtbot, tmp_path):
        win = _make_window(qtbot, tmp_path=tmp_path)
        body = "Matching control"
        win._on_send(body)
        cached = win._msg_cache.get_messages(PHONE)
        matching_sk = cached[0]["sort_key"] if cached else "20260607T101500"
        daemon_messages = [{
            "direction": "outbound", "body": body,
            "timestamp": matching_sk, "conversation_id": PHONE, "sender": "",
        }]
        win._thread_view.load_thread(PHONE, PHONE, [], "SMS")
        with patch.object(win._dbus_client, "get_messages", return_value=daemon_messages):
            win._load_thread_messages(PHONE, PHONE)
        assert _outbound_bubbles(win).count(body) == 1


class TestPersistentAccumulation:
    def test_map_poll_echoes_accumulate_in_persistent_cache(self, qtbot, tmp_path):
        win = _make_window(qtbot, tmp_path=tmp_path)
        body = "Accumulation probe"
        for ts in ("20260607T101500", "20260607T101503"):
            win._on_message_received({
                "direction": "outbound", "body": body,
                "conversation_id": PHONE, "sender": "", "timestamp": ts,
            })
        stored = [m for m in win._msg_cache.get_messages(PHONE) if m["body"] == body]
        assert len(stored) == 1, f"persistent cache accumulated {len(stored)} copies"


class TestIntentionalResendPreserved:
    def test_same_body_far_apart_stays_two_bubbles(self, qtbot, tmp_path):
        """A user re-sending identical text much later must still show 2 bubbles
        (the windowed collapse must NOT eat intentional re-sends)."""
        win = _make_window(qtbot, tmp_path=tmp_path)
        body = "ok"
        daemon_messages = [
            {"direction": "outbound", "body": body, "timestamp": "20260607T090000",
             "conversation_id": PHONE, "sender": ""},
            {"direction": "outbound", "body": body, "timestamp": "20260607T170000",
             "conversation_id": PHONE, "sender": ""},
        ]
        win._thread_view.load_thread(PHONE, PHONE, [], "SMS")
        with patch.object(win._dbus_client, "get_messages", return_value=daemon_messages):
            win._load_thread_messages(PHONE, PHONE)
        assert _outbound_bubbles(win).count(body) == 2
