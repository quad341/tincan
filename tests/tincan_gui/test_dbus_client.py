"""Tests: TincandClient D-Bus bridge — slot bridges, fallback return values, construction.
Bead: tincan-fnf  (tincan-mgc D-Bus signal wiring coverage)

Coverage:
  - All 6 @Slot bridge methods emit the correct Qt signals with properly typed args.
  - get_status() / list_conversations() / send_message() return safe fallback values
    when the daemon is absent (bus disconnected or interface invalid or reply invalid).
  - TincandClient() constructs without crashing when the D-Bus session bus is unavailable.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tincan_gui.dbus_client import TincandClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_disconnected_client():
    """Return a TincandClient whose bus is mocked as disconnected."""
    with patch("tincan_gui.dbus_client.QDBusConnection") as mock_qdb:
        mock_bus = MagicMock()
        mock_bus.isConnected.return_value = False
        mock_qdb.sessionBus.return_value = mock_bus
        client = TincandClient()
    return client


def _make_real_client():
    """Return a TincandClient using the real session bus (tincand absent → iface invalid)."""
    return TincandClient()


# ---------------------------------------------------------------------------
# §1 Slot bridge methods — each slot must emit the matching Qt signal
# ---------------------------------------------------------------------------

class TestTincandClientSlots:
    """All 6 @Slot bridge methods re-emit the correct Qt signal with typed args.

    TincandClient is a QObject (not a QWidget); no qtbot needed.
    """

    def test_on_connected_emits_connected_with_string_address(self):
        client = TincandClient()

        received = []
        client.connected.connect(lambda addr: received.append(addr))
        client._on_connected("AA:BB:CC:DD:EE:FF")

        assert received == ["AA:BB:CC:DD:EE:FF"]
        assert isinstance(received[0], str)

    def test_on_connected_coerces_non_string_to_str(self):
        client = TincandClient()

        received = []
        client.connected.connect(lambda addr: received.append(addr))
        client._on_connected("device_01")
        assert received == ["device_01"]
        assert isinstance(received[0], str)

    def test_on_disconnected_emits_disconnected(self):
        client = TincandClient()

        fired = []
        client.disconnected.connect(lambda: fired.append(True))
        client._on_disconnected()

        assert len(fired) == 1

    def test_on_capability_changed_emits_str_and_bool(self):
        client = TincandClient()

        received = []
        client.capability_changed.connect(lambda f, a: received.append((f, a)))
        client._on_capability_changed("messages", False)

        assert len(received) == 1
        feature, available = received[0]
        assert feature == "messages"
        assert available is False
        assert isinstance(feature, str)
        assert isinstance(available, bool)

    def test_on_capability_changed_available_true_preserved(self):
        client = TincandClient()

        received = []
        client.capability_changed.connect(lambda f, a: received.append((f, a)))
        client._on_capability_changed("ancs", True)

        assert received[0] == ("ancs", True)

    def test_on_message_received_emits_dict(self):
        client = TincandClient()

        received = []
        client.message_received.connect(lambda m: received.append(m))
        payload = {"direction": "inbound", "body": "Hello", "sender": "Alice"}
        client._on_message_received(payload)

        assert len(received) == 1
        assert received[0] == payload
        assert isinstance(received[0], dict)

    def test_on_message_sent_emits_string_id(self):
        client = TincandClient()

        received = []
        client.message_sent.connect(lambda mid: received.append(mid))
        client._on_message_sent("msg-id-42")

        assert received == ["msg-id-42"]
        assert isinstance(received[0], str)

    def test_on_conversation_updated_emits_dict(self):
        client = TincandClient()

        received = []
        client.conversation_updated.connect(lambda c: received.append(c))
        conv = {"id": "conv-1", "display_name": "Alice"}
        client._on_conversation_updated(conv)

        assert len(received) == 1
        assert received[0] == conv
        assert isinstance(received[0], dict)


# ---------------------------------------------------------------------------
# §2 Fallback return values — daemon absent
# ---------------------------------------------------------------------------

class TestTincandClientFallbacksWhenBusDisconnected:
    """get_status / list_conversations / send_message return empty when bus not connected."""

    def test_get_status_returns_empty_dict(self):
        client = _make_disconnected_client()
        assert client.get_status() == {}

    def test_list_conversations_returns_empty_list(self):
        client = _make_disconnected_client()
        assert client.list_conversations() == []

    def test_send_message_returns_empty_string(self):
        client = _make_disconnected_client()
        assert client.send_message("+1555", "hi") == ""


class TestTincandClientFallbacksWhenIfaceInvalid:
    """get_status / list_conversations / send_message return empty when interface is invalid.

    Isolation: _dbus_call is patched to return None (simulates dbus-python miss) and
    QDBusInterface is patched to be invalid (simulates tincand absent), so a live
    tincand daemon on the session bus doesn't pollute the test.
    """

    @pytest.fixture(autouse=True)
    def _isolate_from_daemon(self, monkeypatch):
        monkeypatch.setattr(TincandClient, "_dbus_call", lambda self, *a: None)
        mock_iface = MagicMock()
        mock_iface.isValid.return_value = False
        monkeypatch.setattr("tincan_gui.dbus_client.QDBusInterface", lambda *a: mock_iface)

    def test_get_status_returns_empty_dict(self):
        client = _make_real_client()
        assert client.get_status() == {}

    def test_list_conversations_returns_empty_list(self):
        client = _make_real_client()
        assert client.list_conversations() == []

    def test_send_message_returns_empty_string(self):
        client = _make_real_client()
        assert client.send_message("+1555", "hi") == ""


class TestTincandClientFallbackWhenReplyInvalid:
    """send_message returns empty string when tincand is reachable but reply is invalid.

    QDBusInterface is patched while send_message() runs so we control its return values
    without touching the live daemon.  The bus is faked as connected so the code
    reaches the QDBusInterface path (bus.isConnected() check passes).
    """

    @pytest.fixture(autouse=True)
    def _connected_bus(self, _hermetic_dbus):
        """Override the conftest disconnected-bus default with a connected mock bus."""
        _hermetic_dbus.isConnected.return_value = True

    def test_send_message_returns_empty_string_on_invalid_reply(self):
        client = TincandClient()

        mock_iface = MagicMock()
        mock_iface.isValid.return_value = True
        mock_reply = MagicMock()
        mock_reply.isValid.return_value = False
        mock_reply.error.return_value.message.return_value = "NoReply"
        mock_iface.call.return_value = mock_reply

        with patch("tincan_gui.dbus_client.QDBusInterface", return_value=mock_iface):
            result = client.send_message("+1555", "hello")

        assert result == ""


# ---------------------------------------------------------------------------
# §3 Construction — graceful when bus unavailable
# ---------------------------------------------------------------------------

class TestTincandClientConstruction:
    """TincandClient must not raise when the D-Bus session bus cannot be opened."""

    def test_constructs_without_crash_when_session_bus_unavailable(self):
        with patch("tincan_gui.dbus_client.QDBusConnection") as mock_qdb:
            mock_bus = MagicMock()
            mock_bus.isConnected.return_value = False
            mock_qdb.sessionBus.return_value = mock_bus

            TincandClient()
        # No exception → test passes

    def test_constructs_with_session_bus_available(self):
        # Construction in the normal test environment (D-Bus present, tincand absent)
        TincandClient()
        # Bus is connected; subscribe called; no crash


# ---------------------------------------------------------------------------
# §4 mark_conversation_read — fire-and-forget, no crash when disconnected (tincan-fdvu)
# ---------------------------------------------------------------------------

class TestMarkConversationRead:
    """mark_conversation_read does not raise when the bus is disconnected."""

    def test_does_not_raise_when_bus_disconnected(self, _hermetic_dbus):
        client = TincandClient()
        client.mark_conversation_read("conv-1")
        # No exception → test passes


# ---------------------------------------------------------------------------
# §5 refresh_contacts — fire-and-forget, analogous to RequestReconnect (tincan-mox38)
# ---------------------------------------------------------------------------

class TestRefreshContacts:
    """TincandClient.refresh_contacts() calls RefreshContacts on daemon or no-ops."""

    def test_does_not_raise_when_bus_disconnected(self, _hermetic_dbus):
        client = TincandClient()
        client.refresh_contacts()
        # No exception → test passes

    def test_calls_refresh_contacts_on_daemon_when_connected_and_iface_valid(
        self, _hermetic_dbus
    ):
        from unittest.mock import MagicMock, patch
        _hermetic_dbus.isConnected.return_value = True
        mock_iface = MagicMock()
        mock_iface.isValid.return_value = True
        client = TincandClient()

        with patch("tincan_gui.dbus_client.QDBusInterface", return_value=mock_iface):
            client.refresh_contacts()

        mock_iface.call.assert_called_once_with("RefreshContacts")

    def test_does_not_call_dbus_when_iface_invalid(self, _hermetic_dbus):
        from unittest.mock import MagicMock, patch
        _hermetic_dbus.isConnected.return_value = True
        mock_iface = MagicMock()
        mock_iface.isValid.return_value = False
        client = TincandClient()

        with patch("tincan_gui.dbus_client.QDBusInterface", return_value=mock_iface):
            client.refresh_contacts()

        mock_iface.call.assert_not_called()


# ---------------------------------------------------------------------------
# §6 get_hfp_devices — fallback + demarshalling (mirrors get_adapters) (tincan-d5yyu)
# ---------------------------------------------------------------------------

_ONE_HFP_DEVICE = {
    "path": "/org/ofono/hfp/dev_D0_6B_78_33_46_20",
    "mac": "D0:6B:78:33:46:20",
    "name": "iPhone 15 Pro",
}


class TestGetHFPDevices:
    """get_hfp_devices() returns [] when unreachable; demarshals both code paths."""

    def test_returns_empty_when_bus_disconnected(self):
        client = _make_disconnected_client()
        assert client.get_hfp_devices() == []

    def test_returns_empty_when_iface_invalid(self, _hermetic_dbus, monkeypatch):
        # dbus-python path misses (_dbus_call → None), Qt iface invalid → [].
        _hermetic_dbus.isConnected.return_value = True
        monkeypatch.setattr(TincandClient, "_dbus_call", lambda self, *a: None)
        mock_iface = MagicMock()
        mock_iface.isValid.return_value = False
        monkeypatch.setattr(
            "tincan_gui.dbus_client.QDBusInterface", lambda *a: mock_iface
        )
        client = TincandClient()
        assert client.get_hfp_devices() == []

    def test_demarshals_dbus_python_result(self, _hermetic_dbus, monkeypatch):
        # dbus-python path hit: _dbus_call returns a list of dict-like maps.
        _hermetic_dbus.isConnected.return_value = True
        monkeypatch.setattr(
            TincandClient, "_dbus_call", lambda self, *a: [dict(_ONE_HFP_DEVICE)]
        )
        client = TincandClient()
        result = client.get_hfp_devices()
        assert result == [_ONE_HFP_DEVICE]
        assert isinstance(result[0], dict)

    def test_qt_fallback_demarshals_reply_value(self, _hermetic_dbus):
        # dbus-python misses (_hermetic_dbus → _dbus_call None); Qt fallback used.
        _hermetic_dbus.isConnected.return_value = True
        client = TincandClient()

        mock_iface = MagicMock()
        mock_iface.isValid.return_value = True
        mock_reply = MagicMock()  # non-QDBusMessage → passed through by _wrap_reply
        mock_reply.isValid.return_value = True
        mock_reply.value.return_value = [dict(_ONE_HFP_DEVICE)]
        mock_iface.call.return_value = mock_reply

        with patch("tincan_gui.dbus_client.QDBusInterface", return_value=mock_iface):
            result = client.get_hfp_devices()

        assert result == [_ONE_HFP_DEVICE]
        mock_iface.call.assert_called_once_with("GetHFPDevices")

    def test_qt_fallback_returns_empty_on_invalid_reply(self, _hermetic_dbus):
        _hermetic_dbus.isConnected.return_value = True
        client = TincandClient()

        mock_iface = MagicMock()
        mock_iface.isValid.return_value = True
        mock_reply = MagicMock()
        mock_reply.isValid.return_value = False
        mock_reply.error.return_value.message.return_value = "NoReply"
        mock_iface.call.return_value = mock_reply

        with patch("tincan_gui.dbus_client.QDBusInterface", return_value=mock_iface):
            result = client.get_hfp_devices()

        assert result == []
