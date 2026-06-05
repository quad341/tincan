"""Tests: short-code recipients are accepted by _is_dialable (tincan-amar4).

Coverage:
  - _is_dialable returns True for 4-, 5-, and 6-digit short codes.
  - _is_dialable still returns True for regular 7+ digit phone numbers.
  - _is_dialable returns False for strings with fewer than 4 digits.
  - _on_send does NOT block when _current_phone is a short code.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QSystemTrayIcon

from tincan_gui.main import MainWindow, _is_dialable


@pytest.fixture(autouse=True)
def _no_tray_show():
    with patch.object(QSystemTrayIcon, "show"):
        yield


# ---------------------------------------------------------------------------
# §1 _is_dialable — short codes accepted
# ---------------------------------------------------------------------------

class TestIsDialableShortCodes:
    """_is_dialable must return True for 4-6 digit short codes."""

    def test_four_digit_short_code_is_dialable(self):
        assert _is_dialable("1555") is True

    def test_five_digit_short_code_is_dialable(self):
        assert _is_dialable("26666") is True

    def test_six_digit_short_code_is_dialable(self):
        assert _is_dialable("444444") is True

    def test_regular_ten_digit_number_still_dialable(self):
        assert _is_dialable("8005551234") is True

    def test_international_number_still_dialable(self):
        assert _is_dialable("+18005551234") is True

    def test_three_digit_not_dialable(self):
        assert _is_dialable("911") is False

    def test_two_digit_not_dialable(self):
        assert _is_dialable("42") is False

    def test_empty_not_dialable(self):
        assert _is_dialable("") is False

    def test_name_only_not_dialable(self):
        assert _is_dialable("Apple") is False

    def test_formatted_short_code_with_dashes_is_dialable(self):
        assert _is_dialable("26-666") is True  # 5 digits stripped of dash


# ---------------------------------------------------------------------------
# §2 _on_send — short code conversation allows sending
# ---------------------------------------------------------------------------

class TestOnSendShortCodeAllowed:
    """_on_send must not block when _current_phone is a short code."""

    @pytest.fixture(autouse=True)
    def _no_daemon(self, monkeypatch):
        from tincan_gui.dbus_client import TincandClient
        monkeypatch.setattr(TincandClient, "get_status", lambda self: {})
        monkeypatch.setattr(TincandClient, "get_messages", lambda self, cid: [])
        monkeypatch.setattr(TincandClient, "list_conversations", lambda self: [])

    def test_send_not_blocked_for_five_digit_short_code(self, qtbot, monkeypatch):
        from tincan_gui.dbus_client import TincandClient
        window = MainWindow()
        qtbot.addWidget(window)
        window._current_phone = "26666"
        window._current_phone_dialable = _is_dialable("26666")

        async_calls = []
        monkeypatch.setattr(
            TincandClient, "send_message_async", lambda self, *a: async_calls.append(a)
        )

        window._on_send("hello short code")

        assert async_calls, "_on_send must not block for short code"

    def test_send_not_blocked_for_four_digit_short_code(self, qtbot, monkeypatch):
        from tincan_gui.dbus_client import TincandClient
        window = MainWindow()
        qtbot.addWidget(window)
        window._current_phone = "1555"
        window._current_phone_dialable = _is_dialable("1555")

        async_calls = []
        monkeypatch.setattr(
            TincandClient, "send_message_async", lambda self, *a: async_calls.append(a)
        )

        window._on_send("test")

        assert async_calls, "_on_send must not block for 4-digit short code"

    def test_send_blocked_for_three_digit_number(self, qtbot, monkeypatch):
        from tincan_gui.dbus_client import TincandClient
        window = MainWindow()
        qtbot.addWidget(window)
        window._current_phone = "911"
        window._current_phone_dialable = _is_dialable("911")

        async_calls = []
        monkeypatch.setattr(
            TincandClient, "send_message_async", lambda self, *a: async_calls.append(a)
        )
        errors = []
        monkeypatch.setattr(window._compose, "show_send_error", lambda msg: errors.append(msg))

        window._on_send("emergency?")

        assert not async_calls, "_on_send must block for 3-digit number"
