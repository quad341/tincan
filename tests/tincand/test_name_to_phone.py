"""Tests: name-to-phone persistence + _current_phone_dialable.
Bead: tincan-jnls  (commit 43a2c6a)

Coverage:
  §1 _emit_messages _name_to_phone (bluez_map.py)
     - phone-keyed group populates _name_to_phone[display_name.lower()]
     - subsequent _emit_messages batch with only name-keyed msgs uses _name_to_phone for send_target
     - _name_to_phone cleared in connect()
     - name-keyed group with no phone-keyed counterpart and empty _name_to_phone -> send_target=''

  §2 _sync_compose_state _current_phone_dialable (main.py)
     - conv_data.phone non-dialable -> compose disabled with 'phone number unavailable'
     - conv_data.phone dialable -> compose enabled (when messages_ok)
     - conv_data=None (unknown conv) -> _current_phone_dialable=True -> compose enabled
     - _on_send with _current_phone_dialable=False -> show_send_error without send_message call
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QSystemTrayIcon

from tincan_gui.dbus_client import TincandClient
from tincan_gui.main import MainWindow
from tincan_gui.conversation_list import ConversationData
from tincand.backends.bluez_map import MapBackend


@pytest.fixture(autouse=True)
def _no_tray_show():
    with patch.object(QSystemTrayIcon, "show"):
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service():
    svc = MagicMock(name="TincanService")
    return svc


def _make_msg(sender: str, display_name: str | None = None, *,
              direction: str = "inbound", ts: str = "20260101T100000") -> dict:
    msg: dict = {
        "sender": sender,
        "body": "hi",
        "timestamp": ts,
        "read": True,
        "direction": direction,
    }
    if display_name is not None:
        msg["display_name"] = display_name
    return msg


def _make_window(qtbot) -> MainWindow:
    window = MainWindow()
    qtbot.addWidget(window)
    return window


def _make_conv_data(phone: str, name: str = "Alice") -> ConversationData:
    return ConversationData(
        id=phone, name=name, phone=phone,
        preview="", timestamp="10:00", unread=False, unread_count=0,
    )


# ---------------------------------------------------------------------------
# §1 _emit_messages _name_to_phone
# ---------------------------------------------------------------------------

class TestNameToPhonePopulation:
    """Phone-keyed messages populate _name_to_phone; cleared on connect()."""

    def _make_backend_with_service(self):
        backend = MapBackend()
        svc = _make_service()
        backend._service = svc
        return backend, svc

    def test_phone_keyed_group_populates_name_to_phone(self):
        backend, svc = self._make_backend_with_service()
        phone = "+15550001111"
        phone_norm = "5550001111"  # _norm_phone strips + and truncates to last 10 digits
        display = "Alice"
        msgs = [_make_msg(phone, display)]

        backend._emit_messages(msgs, notify=False)

        assert backend._name_to_phone.get(display.lower()) == phone_norm

    def test_name_key_is_lowercased(self):
        backend, svc = self._make_backend_with_service()
        phone = "+15550001111"
        msgs = [_make_msg(phone, "Alice Smith")]

        backend._emit_messages(msgs, notify=False)

        assert "alice smith" in backend._name_to_phone

    def test_subsequent_batch_name_keyed_uses_name_to_phone(self):
        backend, svc = self._make_backend_with_service()
        phone = "+15550001111"
        phone_norm = "5550001111"  # _norm_phone result; what _name_to_phone stores
        display = "Alice"
        # First batch: phone-keyed — populates _name_to_phone
        backend._emit_messages([_make_msg(phone, display)], notify=False)
        # Second batch: name-keyed only — should resolve send_target from _name_to_phone
        backend._emit_messages([_make_msg(display, display)], notify=False)

        # Second upsert_conversation call should have send_target == normalized phone
        calls = svc.upsert_conversation.call_args_list
        second_conv = calls[1][0][0]
        assert second_conv.send_target == phone_norm

    def test_name_to_phone_cleared_on_connect(self):
        backend = MapBackend()
        backend._name_to_phone["alice"] = "+15550001111"

        with patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface") as mock_iface, \
             patch.object(MapBackend, "_resolve_device_name", return_value="test-device"), \
             patch.object(MapBackend, "set_capability", None, create=True):
            mock_client = MagicMock()
            mock_client.CreateSession.return_value = "/session/path"
            mock_iface.return_value = mock_client
            try:
                backend.connect("AA:BB:CC:DD:EE:FF")
            except Exception:
                pass  # session details don't matter; we just need clear() to fire

        assert backend._name_to_phone == {}

    def test_name_keyed_with_empty_name_to_phone_gives_empty_send_target(self):
        backend, svc = self._make_backend_with_service()
        assert backend._name_to_phone == {}
        name_only = "Bob"
        msgs = [_make_msg(name_only, name_only)]

        backend._emit_messages(msgs, notify=False)

        conv = svc.upsert_conversation.call_args[0][0]
        assert conv.send_target == ""


# ---------------------------------------------------------------------------
# §2 _current_phone_dialable
# ---------------------------------------------------------------------------

class TestCurrentPhoneDialable:
    """_sync_compose_state uses _current_phone_dialable to gate compose."""

    def _select_conv(self, window: MainWindow, conv_data: ConversationData | None,
                     monkeypatch) -> None:
        """Simulate selecting a conversation without real D-Bus calls."""
        monkeypatch.setattr(TincandClient, "get_messages", lambda self, cid: [])
        monkeypatch.setattr(TincandClient, "fetch_contact_photo", lambda self, cid: None)
        window._messages_ok = True
        if conv_data:
            window._conversations_by_id[conv_data.id] = conv_data
        conv_id = conv_data.id if conv_data else "unknown-conv"
        window._on_conversation_selected(conv_id)

    def test_non_dialable_phone_disables_compose(self, qtbot, monkeypatch):
        window = _make_window(qtbot)
        conv = _make_conv_data(phone="iMessage group chat", name="Group")
        self._select_conv(window, conv, monkeypatch)

        assert not window._compose.send_button.isEnabled()

    def test_non_dialable_phone_shows_unavailable_tooltip(self, qtbot, monkeypatch):
        window = _make_window(qtbot)
        conv = _make_conv_data(phone="iMessage group chat", name="Group")
        self._select_conv(window, conv, monkeypatch)

        tooltip = window._compose.send_button.toolTip()
        assert "unavailable" in tooltip.lower()

    def test_dialable_phone_enables_compose(self, qtbot, monkeypatch):
        window = _make_window(qtbot)
        conv = _make_conv_data(phone="+15550001111", name="Alice")
        self._select_conv(window, conv, monkeypatch)

        assert window._compose.send_button.isEnabled()

    def test_unknown_conv_keeps_current_phone_dialable_true(self, qtbot, monkeypatch):
        window = _make_window(qtbot)
        self._select_conv(window, None, monkeypatch)

        assert window._current_phone_dialable is True

    def test_unknown_conv_compose_enabled(self, qtbot, monkeypatch):
        window = _make_window(qtbot)
        self._select_conv(window, None, monkeypatch)

        assert window._compose.send_button.isEnabled()

    def test_on_send_with_non_dialable_shows_error_no_send(self, qtbot, monkeypatch):
        calls = []
        monkeypatch.setattr(
            TincandClient, "send_message",
            lambda self, to, body: calls.append((to, body)) or "",
        )
        window = _make_window(qtbot)
        window._current_phone = "iMessage group"
        window._current_phone_dialable = False

        window._on_send("hello")

        assert calls == []
        assert not window._compose._error_bar.isHidden()

    def test_on_send_with_dialable_calls_send_message(self, qtbot, monkeypatch):
        calls = []
        monkeypatch.setattr(
            TincandClient, "send_message",
            lambda self, to, body: calls.append((to, body)) or "msg-id-1",
        )
        window = _make_window(qtbot)
        window._current_phone = "+15550001111"
        window._current_phone_dialable = True
        window._messages_ok = True

        window._on_send("hello")

        assert len(calls) == 1
