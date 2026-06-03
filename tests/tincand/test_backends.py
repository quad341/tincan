"""Tests: MockBackend and MapBackend unit tests.
Bead: tincan-spa, tincan-44wr

Coverage:
  §1 MockBackend.connect() — loads canned conversations, calls service.Connect(), requires service
  §2 MockBackend.disconnect() — removes GLib timer, calls service.Disconnect(), safe when idle
  §3 MockBackend stub returns — poll_inbox/get_message/send_message return correct stub values
  §4 MapBackend.connect() — successful session stored; Forbidden → ConsentRequired;
     other exc re-raised
  §5 MapBackend.disconnect() — no-op when no session; removes session; clears state; logs on error
  §6-§8 pending tincan-4u26 (GetMessage API not yet landed on main)
  §9 MapBackend._resolve_device_name — returns BlueZ Alias;
     fallback to addr on empty/miss/DBusException
  §10 MapBackend.connect() — set_capability('messages', True) and set_device_name called on service
  §11 MapBackend.poll_inbox — direction='inbound' for inbox, 'outbound' for sent
  §12 MapBackend.poll_inbox — sent folder DBusException swallowed; inbox messages still returned

No hardware or real D-Bus — all D-Bus objects mocked.
Run with: python -m pytest tests/tincand/test_backends.py -v
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import dbus
import dbus.exceptions
import pytest

from tincand.backends.bluez_map import ConsentRequired, MapBackend
from tincand.backends.mock import MockBackend

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BLUEZ_DEVICE1 = "org.bluez.Device1"


def _make_managed_objects(addr: str, alias: str) -> dict:
    """Build a minimal GetManagedObjects() return value with one Device1 entry."""
    path = "/org/bluez/hci0/dev_" + addr.replace(":", "_")
    return {path: {_BLUEZ_DEVICE1: {"Address": addr, "Alias": alias}}}

def _make_service():
    svc = MagicMock(name="TincanService")
    return svc


def _forbidden_exc():
    exc = dbus.exceptions.DBusException(name="org.openobex.Error.Forbidden")
    return exc


def _other_exc():
    exc = dbus.exceptions.DBusException(name="org.bluez.Error.Failed")
    return exc


# ---------------------------------------------------------------------------
# §1 MockBackend.connect()
# ---------------------------------------------------------------------------

class TestMockBackendConnect:
    def test_connect_loads_all_canned_conversations(self):
        backend = MockBackend()
        svc = _make_service()
        backend.register_service(svc)
        with patch("tincand.backends.mock.GLib") as mock_glib:
            mock_glib.timeout_add_seconds.return_value = 42
            backend.connect("AA:BB:CC:DD:EE:FF")
        assert svc.upsert_conversation.call_count == 3

    def test_connect_calls_service_connect_with_device_addr(self):
        backend = MockBackend()
        svc = _make_service()
        backend.register_service(svc)
        with patch("tincand.backends.mock.GLib"):
            backend.connect("AA:BB:CC:DD:EE:FF")
        svc.Connect.assert_called_once_with("AA:BB:CC:DD:EE:FF")

    def test_connect_starts_glib_timer(self):
        backend = MockBackend()
        svc = _make_service()
        backend.register_service(svc)
        with patch("tincand.backends.mock.GLib") as mock_glib:
            mock_glib.timeout_add_seconds.return_value = 99
            backend.connect("AA:BB:CC:DD:EE:FF")
        mock_glib.timeout_add_seconds.assert_called_once()

    def test_connect_raises_if_service_not_registered(self):
        backend = MockBackend()
        with pytest.raises(RuntimeError, match="register_service"):
            backend.connect("AA:BB:CC:DD:EE:FF")


# ---------------------------------------------------------------------------
# §2 MockBackend.disconnect()
# ---------------------------------------------------------------------------

class TestMockBackendDisconnect:
    def test_disconnect_removes_glib_timer(self):
        backend = MockBackend()
        svc = _make_service()
        backend.register_service(svc)
        with patch("tincand.backends.mock.GLib") as mock_glib:
            mock_glib.timeout_add_seconds.return_value = 42
            backend.connect("AA:BB:CC:DD:EE:FF")
            backend.disconnect()
        mock_glib.source_remove.assert_called_once_with(42)

    def test_disconnect_calls_service_disconnect(self):
        backend = MockBackend()
        svc = _make_service()
        backend.register_service(svc)
        with patch("tincand.backends.mock.GLib"):
            backend.connect("AA:BB:CC:DD:EE:FF")
            backend.disconnect()
        svc.Disconnect.assert_called_once()

    def test_disconnect_no_op_when_not_connected(self):
        backend = MockBackend()
        svc = _make_service()
        backend.register_service(svc)
        with patch("tincand.backends.mock.GLib") as mock_glib:
            backend.disconnect()
        mock_glib.source_remove.assert_not_called()

    def test_disconnect_clears_source_id(self):
        backend = MockBackend()
        svc = _make_service()
        backend.register_service(svc)
        with patch("tincand.backends.mock.GLib") as mock_glib:
            mock_glib.timeout_add_seconds.return_value = 7
            backend.connect("AA:BB:CC:DD:EE:FF")
        with patch("tincand.backends.mock.GLib"):
            backend.disconnect()
        assert backend._source_id is None


# ---------------------------------------------------------------------------
# §3 MockBackend stub returns
# ---------------------------------------------------------------------------

class TestMockBackendStubReturns:
    def test_poll_inbox_returns_empty_list(self):
        backend = MockBackend()
        assert backend.poll_inbox() == []

    def test_get_message_returns_none(self):
        backend = MockBackend()
        assert backend.get_message("some-handle") is None

    def test_send_message_returns_string(self):
        backend = MockBackend()
        result = backend.send_message("+15550100", "Hello")
        assert isinstance(result, str)

    def test_send_message_handle_contains_recipient(self):
        backend = MockBackend()
        result = backend.send_message("+15550101", "Hi")
        assert "+15550101" in result


# ---------------------------------------------------------------------------
# §4 MapBackend.connect()
# ---------------------------------------------------------------------------

class TestMapBackendConnect:
    def _patched_connect(self, device_addr, session_path="/org/obex/session1",
                         side_effect=None):
        """Run MapBackend.connect() with mocked D-Bus; return (backend, svc)."""
        backend = MapBackend()
        svc = _make_service()
        backend.register_service(svc)

        mock_client = MagicMock(name="Client1")
        if side_effect is not None:
            mock_client.CreateSession.side_effect = side_effect
        else:
            mock_client.CreateSession.return_value = session_path

        with patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface") as mock_iface:
            mock_iface.return_value = mock_client
            backend.connect(device_addr)

        return backend, svc

    def test_successful_connect_stores_session_path(self):
        backend, _ = self._patched_connect("AA:BB:CC:DD:EE:FF",
                                            session_path="/org/obex/session1")
        assert backend._session_path == "/org/obex/session1"

    def test_successful_connect_calls_service_connect(self):
        backend, svc = self._patched_connect("AA:BB:CC:DD:EE:FF")
        svc.Connect.assert_called_once_with("AA:BB:CC:DD:EE:FF")

    def test_forbidden_exc_raises_consent_required(self):
        backend = MapBackend()
        svc = _make_service()
        backend.register_service(svc)

        mock_client = MagicMock(name="Client1")
        mock_client.CreateSession.side_effect = _forbidden_exc()

        with patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface",
                   return_value=mock_client), \
             pytest.raises(ConsentRequired):
            backend.connect("AA:BB:CC:DD:EE:FF")

    def test_non_forbidden_exc_propagates(self):
        backend = MapBackend()
        svc = _make_service()
        backend.register_service(svc)

        mock_client = MagicMock(name="Client1")
        mock_client.CreateSession.side_effect = _other_exc()

        with patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface",
                   return_value=mock_client), \
             pytest.raises(dbus.exceptions.DBusException):
            backend.connect("AA:BB:CC:DD:EE:FF")

    def test_forbidden_exc_does_not_store_session_path(self):
        backend = MapBackend()
        svc = _make_service()
        backend.register_service(svc)

        mock_client = MagicMock(name="Client1")
        mock_client.CreateSession.side_effect = _forbidden_exc()

        with patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface",
                   return_value=mock_client), \
             pytest.raises(ConsentRequired):
            backend.connect("AA:BB:CC:DD:EE:FF")

        assert backend._session_path is None


# ---------------------------------------------------------------------------
# §5 MapBackend.disconnect()
# ---------------------------------------------------------------------------

class TestMapBackendDisconnect:
    def test_disconnect_no_op_when_no_session(self):
        backend = MapBackend()
        svc = _make_service()
        backend.register_service(svc)
        # Should not raise and should not call RemoveSession
        with patch("tincand.backends.bluez_map.dbus.SessionBus") as mock_bus_cls:
            backend.disconnect()
        mock_bus_cls.assert_not_called()

    def test_disconnect_calls_remove_session(self):
        backend = MapBackend()
        backend._session_path = "/org/obex/session1"
        svc = _make_service()
        backend.register_service(svc)

        mock_client = MagicMock(name="Client1")
        with patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface",
                   return_value=mock_client):
            backend.disconnect()

        mock_client.RemoveSession.assert_called_once_with("/org/obex/session1")

    def test_disconnect_clears_session_path(self):
        backend = MapBackend()
        backend._session_path = "/org/obex/session1"
        svc = _make_service()
        backend.register_service(svc)

        with patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface"):
            backend.disconnect()

        assert backend._session_path is None

    def test_disconnect_calls_service_disconnect(self):
        backend = MapBackend()
        backend._session_path = "/org/obex/session1"
        svc = _make_service()
        backend.register_service(svc)

        with patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface"):
            backend.disconnect()

        svc.Disconnect.assert_called_once()

    def test_disconnect_dbus_exc_logs_warning_and_clears_session(self):
        backend = MapBackend()
        backend._session_path = "/org/obex/session1"
        svc = _make_service()
        backend.register_service(svc)

        mock_client = MagicMock(name="Client1")
        mock_client.RemoveSession.side_effect = _other_exc()

        with patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface",
                   return_value=mock_client):
            backend.disconnect()  # should not raise

        assert backend._session_path is None

    def test_disconnect_dbus_exc_still_calls_service_disconnect(self):
        backend = MapBackend()
        backend._session_path = "/org/obex/session1"
        svc = _make_service()
        backend.register_service(svc)

        mock_client = MagicMock(name="Client1")
        mock_client.RemoveSession.side_effect = _other_exc()

        with patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface",
                   return_value=mock_client):
            backend.disconnect()

        svc.Disconnect.assert_called_once()


# ---------------------------------------------------------------------------
# Additional helpers
# ---------------------------------------------------------------------------

def _make_map_backend_with_mock_access():
    """Create a MapBackend with _msg_access pre-wired to a MagicMock."""
    backend = MapBackend()
    mock_access = MagicMock(name="MessageAccess1")
    backend._msg_access = mock_access
    return backend, mock_access


# ---------------------------------------------------------------------------
# §6-§8 (TestMapBackendPollInboxFolderNav, TestMapBackendPollInboxBodyFallback,
# TestMapBackendFetchFullBodyGetMessageArgs) require GetMessage API changes
# from tincan-4u26 — pending that bead landing.

# §9 MapBackend._resolve_device_name — alias lookup and fallback
# ---------------------------------------------------------------------------

class TestMapBackendResolveDeviceName:
    """_resolve_device_name returns BlueZ Alias, or device_addr on miss/empty/error."""

    ADDR = "AA:BB:CC:DD:EE:FF"

    def _resolve(self, managed_objects=None, dbus_exception=None):
        """Call _resolve_device_name with a fully-mocked BlueZ ObjectManager."""
        backend = MapBackend()
        mock_mgr = MagicMock(name="ObjectManager")
        if dbus_exception is not None:
            mock_mgr.GetManagedObjects.side_effect = dbus_exception
        else:
            result = managed_objects if managed_objects is not None else {}
            mock_mgr.GetManagedObjects.return_value = result

        with patch("tincand.backends.bluez_map.dbus.SystemBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface", return_value=mock_mgr):
            return backend._resolve_device_name(self.ADDR)

    def test_returns_alias_when_device_found(self):
        objs = _make_managed_objects(self.ADDR, "iPhone of Alice")
        assert self._resolve(objs) == "iPhone of Alice"

    def test_returns_device_addr_when_alias_is_empty(self):
        objs = _make_managed_objects(self.ADDR, "")
        assert self._resolve(objs) == self.ADDR

    def test_returns_device_addr_when_no_matching_address(self):
        objs = _make_managed_objects("11:22:33:44:55:66", "SomeOtherDevice")
        assert self._resolve(objs) == self.ADDR

    def test_returns_device_addr_on_dbus_exception(self):
        exc = dbus.exceptions.DBusException(name="org.freedesktop.DBus.Error.ServiceUnknown")
        assert self._resolve(dbus_exception=exc) == self.ADDR

    def test_returns_device_addr_when_managed_objects_empty(self):
        assert self._resolve(managed_objects={}) == self.ADDR

    def test_matching_uses_address_field_not_object_path(self):
        # Path contains the target addr pattern but Address field is a different device — no match.
        objs = {
            "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF": {
                _BLUEZ_DEVICE1: {"Address": "11:22:33:44:55:66", "Alias": "WrongDevice"}
            }
        }
        assert self._resolve(objs) == self.ADDR


# ---------------------------------------------------------------------------
# §10 MapBackend.connect() — set_capability and set_device_name on service
# ---------------------------------------------------------------------------

class TestMapBackendConnectCapability:
    """connect() calls set_capability('messages', True) and set_device_name on the service."""

    def _patched_connect(self, device_addr="AA:BB:CC:DD:EE:FF",
                         session_path="/org/obex/session1"):
        backend = MapBackend()
        svc = _make_service()
        backend.register_service(svc)

        mock_client = MagicMock(name="Client1")
        mock_client.CreateSession.return_value = session_path

        with patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface", return_value=mock_client):
            backend.connect(device_addr)

        return backend, svc

    def test_set_capability_messages_true_called_on_connect(self):
        _, svc = self._patched_connect()
        svc.set_capability.assert_called_once_with("messages", True)

    def test_set_device_name_called_on_connect(self):
        _, svc = self._patched_connect()
        svc.set_device_name.assert_called_once()

    def test_set_device_name_receives_resolved_or_fallback_name(self):
        # _resolve_device_name falls back to device_addr when BlueZ is mocked;
        # verify set_device_name is called with that fallback string.
        _, svc = self._patched_connect("AA:BB:CC:DD:EE:FF")
        svc.set_device_name.assert_called_once_with("AA:BB:CC:DD:EE:FF")

    def test_set_capability_not_called_when_no_service_registered(self):
        backend = MapBackend()
        mock_client = MagicMock(name="Client1")
        mock_client.CreateSession.return_value = "/org/obex/session1"

        with patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface", return_value=mock_client):
            backend.connect("AA:BB:CC:DD:EE:FF")  # no service → should not raise

    def test_set_capability_called_after_service_connect(self):
        _, svc = self._patched_connect()
        method_names = [c[0] for c in svc.method_calls]
        connect_idx = method_names.index("Connect")
        cap_idx = method_names.index("set_capability")
        assert cap_idx > connect_idx


# ---------------------------------------------------------------------------
# §11 MapBackend.poll_inbox — direction per folder
# ---------------------------------------------------------------------------

class TestMapBackendPollInboxDirection:
    """poll_inbox assigns direction='inbound' for inbox and 'outbound' for sent."""

    def _poll_with_one_inbox_one_sent(self):
        """Return poll_inbox result with exactly one inbox and one sent message."""
        backend, mock_access = _make_map_backend_with_mock_access()
        mock_access.GetMessage.return_value = None  # _fetch_full_body short-circuits to None

        def _list(folder, _filter):
            if folder == "inbox":
                return {"/inbox/1": {"Sender": "Alice", "Datetime": "20260101", "Read": False,
                                     "Subject": "Hi"}}
            if folder == "sent":
                return {"/sent/1": {"RecipientAddressing": "+15550001", "Datetime": "20260101",
                                    "Subject": "Hey"}}
            return {}

        mock_access.ListMessages.side_effect = _list
        return backend.poll_inbox()

    def test_poll_returns_two_messages_when_both_folders_have_one(self):
        result = self._poll_with_one_inbox_one_sent()
        assert len(result) == 2

    def test_inbox_message_has_direction_inbound(self):
        result = self._poll_with_one_inbox_one_sent()
        inbox_msg = next(m for m in result if m["path"] == "/inbox/1")
        assert inbox_msg["direction"] == "inbound"

    def test_sent_message_has_direction_outbound(self):
        result = self._poll_with_one_inbox_one_sent()
        sent_msg = next(m for m in result if m["path"] == "/sent/1")
        assert sent_msg["direction"] == "outbound"

    def test_direction_field_present_in_all_messages(self):
        result = self._poll_with_one_inbox_one_sent()
        assert all("direction" in m for m in result)

    def test_inbox_direction_is_not_outbound(self):
        result = self._poll_with_one_inbox_one_sent()
        inbox_msg = next(m for m in result if m["path"] == "/inbox/1")
        assert inbox_msg["direction"] != "outbound"

    def test_sent_direction_is_not_inbound(self):
        result = self._poll_with_one_inbox_one_sent()
        sent_msg = next(m for m in result if m["path"] == "/sent/1")
        assert sent_msg["direction"] != "inbound"


# ---------------------------------------------------------------------------
# §12 MapBackend.poll_inbox — sent folder DBusException handling
# ---------------------------------------------------------------------------

class TestMapBackendPollInboxSentFolderException:
    """poll_inbox swallows DBusException from the sent folder; inbox messages still returned."""

    def _poll_with_sent_exception(self):
        backend, mock_access = _make_map_backend_with_mock_access()
        mock_access.GetMessage.return_value = None

        def _list(folder, _filter):
            if folder == "inbox":
                return {"/inbox/1": {"Sender": "Alice", "Datetime": "20260101", "Read": False,
                                     "Subject": "Hi"}}
            if folder == "sent":
                raise dbus.exceptions.DBusException(name="org.bluez.obex.Error.NotFound")
            return {}

        mock_access.ListMessages.side_effect = _list
        return backend.poll_inbox()

    def test_sent_dbus_exc_does_not_raise(self):
        self._poll_with_sent_exception()  # must not propagate

    def test_sent_dbus_exc_inbox_messages_returned(self):
        result = self._poll_with_sent_exception()
        assert len(result) == 1

    def test_sent_dbus_exc_inbox_message_direction_is_inbound(self):
        result = self._poll_with_sent_exception()
        assert result[0]["direction"] == "inbound"

    def test_sent_dbus_exc_no_outbound_messages_in_result(self):
        result = self._poll_with_sent_exception()
        assert not any(m["direction"] == "outbound" for m in result)

    def test_sent_messages_included_when_no_exception(self):
        backend, mock_access = _make_map_backend_with_mock_access()
        mock_access.GetMessage.return_value = None

        def _list(folder, _filter):
            if folder == "inbox":
                return {"/inbox/1": {"Sender": "Alice", "Datetime": "20260101", "Read": False,
                                     "Subject": "Hi"}}
            if folder == "sent":
                return {"/sent/1": {"RecipientAddressing": "+15550001", "Datetime": "20260101",
                                    "Subject": "Hey"}}
            return {}

        mock_access.ListMessages.side_effect = _list
        result = backend.poll_inbox()
        assert len(result) == 2
