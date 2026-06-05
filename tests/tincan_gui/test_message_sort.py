"""Tests: message sort uses full date+seconds (tincan-93fha).

Coverage:
  - _parse_map_datetime returns full sortable YYYYMMDDTHHMMSS, not HH:MM.
  - MessageData has a sort_key field for full-datetime ordering.
  - _msg_dict_to_data stores full timestamp in sort_key, HH:MM in timestamp.
  - _msg_dict_to_data extracts HH:MM display from a full YYYYMMDDTHHMMSS timestamp.
  - Messages sort cross-day: earlier date before later date regardless of time-of-day.
  - Messages sort by seconds within same minute.
  - Outbound sent messages receive a sort_key derived from current datetime.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QSystemTrayIcon

from tincan_gui.main import MainWindow
from tincan_gui.thread_view import BubbleType, MessageData
from tincand.backends.bluez_map import _parse_map_datetime


@pytest.fixture(autouse=True)
def _no_tray_show():
    with patch.object(QSystemTrayIcon, "show"):
        yield


# ---------------------------------------------------------------------------
# §1 _parse_map_datetime — returns full sortable datetime (not HH:MM)
# ---------------------------------------------------------------------------

class TestParseMapDatetimeFullFormat:
    """_parse_map_datetime must return the full YYYYMMDDTHHMMSS, not just HH:MM."""

    def test_returns_full_datetime_not_hhmm(self):
        result = _parse_map_datetime("20260101T100000")
        assert result == "20260101T100000"

    def test_strips_timezone_offset(self):
        result = _parse_map_datetime("20260601T143022+0500")
        assert result == "20260601T143022"

    def test_strips_negative_timezone_offset(self):
        result = _parse_map_datetime("20260601T143022-0700")
        assert result == "20260601T143022"

    def test_empty_input_returns_empty(self):
        assert _parse_map_datetime("") == ""

    def test_malformed_no_T_returns_empty(self):
        assert _parse_map_datetime("20260601") == ""

    def test_truncated_time_returns_empty(self):
        # Only T + 4 chars: not enough for HHMMSS
        assert _parse_map_datetime("20260601T1030") == ""

    def test_result_is_lexicographically_sortable(self):
        earlier = _parse_map_datetime("20261204T153000")
        later = _parse_map_datetime("20261205T100000")
        assert earlier < later, "earlier date must sort before later date"

    def test_same_day_seconds_are_preserved(self):
        first = _parse_map_datetime("20260101T100000")
        second = _parse_map_datetime("20260101T100059")
        assert first < second


# ---------------------------------------------------------------------------
# §2 MessageData.sort_key — field exists and defaults empty
# ---------------------------------------------------------------------------

class TestMessageDataSortKey:
    """MessageData must have a sort_key field (default '') for datetime ordering."""

    def test_sort_key_field_exists_with_default_empty(self):
        msg = MessageData(BubbleType.OUTBOUND, "hi", "", "10:00")
        assert hasattr(msg, "sort_key")
        assert msg.sort_key == ""

    def test_sort_key_can_be_set_explicitly(self):
        msg = MessageData(BubbleType.INBOUND, "hi", "+1", "10:00", sort_key="20260101T100000")
        assert msg.sort_key == "20260101T100000"


# ---------------------------------------------------------------------------
# §3 _msg_dict_to_data — populates sort_key and display timestamp correctly
# ---------------------------------------------------------------------------

class TestMsgDictToData:
    """_msg_dict_to_data must store full timestamp in sort_key and HH:MM in timestamp."""

    @pytest.fixture(autouse=True)
    def _no_daemon(self, monkeypatch):
        from tincan_gui.dbus_client import TincandClient
        monkeypatch.setattr(TincandClient, "get_status", lambda self: {})
        monkeypatch.setattr(TincandClient, "get_messages", lambda self, cid: [])
        monkeypatch.setattr(TincandClient, "list_conversations", lambda self: [])

    def _dict_to_data(self, qtbot, msg_dict):
        window = MainWindow()
        qtbot.addWidget(window)
        return window._msg_dict_to_data(msg_dict)

    def test_sort_key_stores_full_datetime(self, qtbot):
        msg = {"direction": "inbound", "body": "hi", "from": "+1", "timestamp": "20260601T143022"}
        data = self._dict_to_data(qtbot, msg)
        assert data.sort_key == "20260601T143022"

    def test_timestamp_stores_hhmm_display(self, qtbot):
        msg = {"direction": "inbound", "body": "hi", "from": "+1", "timestamp": "20260601T143022"}
        data = self._dict_to_data(qtbot, msg)
        assert data.timestamp == "14:30"

    def test_empty_timestamp_gives_empty_sort_key(self, qtbot):
        msg = {"direction": "inbound", "body": "hi", "from": "+1", "timestamp": ""}
        data = self._dict_to_data(qtbot, msg)
        assert data.sort_key == ""
        assert data.timestamp == ""


# ---------------------------------------------------------------------------
# §4 Sort order — messages sort by full datetime (cross-day + seconds)
# ---------------------------------------------------------------------------

class TestMessageSortOrder:
    """After _load_thread_messages sorts messages, cross-day ordering must be correct."""

    @pytest.fixture(autouse=True)
    def _no_daemon(self, monkeypatch):
        from tincan_gui.dbus_client import TincandClient
        monkeypatch.setattr(TincandClient, "get_status", lambda self: {})
        monkeypatch.setattr(TincandClient, "list_conversations", lambda self: [])

    def _make_inbound(self, qtbot, raw_ts: str) -> MessageData:
        from tincan_gui.main import MainWindow
        window = MainWindow()
        qtbot.addWidget(window)
        return window._msg_dict_to_data(
            {"direction": "inbound", "body": "x", "from": "+1", "timestamp": raw_ts}
        )

    def test_cross_day_earlier_date_sorts_first(self, qtbot):
        """Message from yesterday at 15:30 must sort before today's message at 10:00."""
        yesterday = self._make_inbound(qtbot, "20261204T153000")
        today = self._make_inbound(qtbot, "20261205T100000")
        key = lambda m: m.sort_key or m.timestamp  # noqa: E731
        assert sorted([today, yesterday], key=key) == [yesterday, today]

    def test_same_minute_seconds_determine_order(self, qtbot):
        first = self._make_inbound(qtbot, "20261205T100000")
        second = self._make_inbound(qtbot, "20261205T100059")
        key = lambda m: m.sort_key or m.timestamp  # noqa: E731
        assert sorted([second, first], key=key) == [first, second]


# ---------------------------------------------------------------------------
# §5 Outbound sent messages get sort_key at send time
# ---------------------------------------------------------------------------

class TestOutboundSortKey:
    """_on_send must attach sort_key to the optimistic outbound MessageData."""

    @pytest.fixture(autouse=True)
    def _no_daemon(self, monkeypatch):
        from tincan_gui.dbus_client import TincandClient
        monkeypatch.setattr(TincandClient, "get_status", lambda self: {})
        monkeypatch.setattr(TincandClient, "get_messages", lambda self, cid: [])
        monkeypatch.setattr(TincandClient, "list_conversations", lambda self: [])

    def test_sent_message_has_nonempty_sort_key(self, qtbot, monkeypatch):
        from tincan_gui.dbus_client import TincandClient
        window = MainWindow()
        qtbot.addWidget(window)
        window._current_phone = "+15550001111"
        window._current_phone_dialable = True
        monkeypatch.setattr(TincandClient, "send_message_async", lambda self, *a: None)

        appended = []
        monkeypatch.setattr(
            window._thread_view, "append_message", lambda msg: appended.append(msg)
        )

        window._on_send("test sort key")

        assert appended, "append_message must be called"
        sent = appended[0]
        assert sent.sort_key, "outbound MessageData must have a non-empty sort_key"

    def test_sent_message_sort_key_is_full_datetime(self, qtbot, monkeypatch):
        from tincan_gui.dbus_client import TincandClient
        window = MainWindow()
        qtbot.addWidget(window)
        window._current_phone = "+15550001111"
        window._current_phone_dialable = True
        monkeypatch.setattr(TincandClient, "send_message_async", lambda self, *a: None)

        appended = []
        monkeypatch.setattr(
            window._thread_view, "append_message", lambda msg: appended.append(msg)
        )

        window._on_send("full datetime sort key")

        sent = appended[0]
        # sort_key must contain a 'T' separator and be longer than HH:MM (5 chars)
        assert "T" in sent.sort_key and len(sent.sort_key) > 5
