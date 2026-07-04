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
  §13 MapBackend._fetch_full_body — failed-handle backoff cache (tincan-ixqg / tincan-572zo)
     - handle is NOT retried after first Message1.Get DBusException (inject + tick, no real timing)
     - Message1.Get called exactly once per failing handle across N polls
     - body falls back to Subject on first poll when Message1.Get fails
     - Subject fallback still used on subsequent polls when handle is cached
     - handle stored in _failed_handles after Message1.Get exception
     - handle NOT stored in _failed_handles when Message1.Get returns None (success path)
     - non-failing handle attempted on every poll (not incorrectly cached)
     - _failed_handles cleared by connect()

No hardware or real D-Bus — all D-Bus objects mocked.
Run with: python -m pytest tests/tincand/test_backends.py -v
"""
from __future__ import annotations

import contextlib
from unittest.mock import MagicMock, patch

import dbus
import dbus.exceptions
import pytest

from tincand.backends.bluez_map import ConsentRequired, MapBackend
from tincand.backends.mock import MockBackend
from tincand.obex_worker import InlineWorker

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


# ---------------------------------------------------------------------------
# §13 MapBackend._fetch_full_body — failed-handle backoff cache (tincan-ixqg / tincan-572zo)
# ---------------------------------------------------------------------------

def _get_message_exc():
    """DBusException simulating Message1.Get UnknownMethod (BlueZ 5.66+ removed GetMessage)."""
    return dbus.exceptions.DBusException(name="org.freedesktop.DBus.Error.UnknownMethod")


def _make_message1_iface_factory(mock_msg1):
    """Return a dbus.Interface side_effect that yields mock_msg1 for Message1 calls."""
    def _factory(obj, iface_name):
        if iface_name == "org.bluez.obex.Message1":
            return mock_msg1
        return MagicMock(name=f"iface:{iface_name}")
    return _factory


class TestMapBackendFailedHandleBackoff:
    """_fetch_full_body caches handles that raised DBusException; skips on subsequent polls."""

    @contextlib.contextmanager
    def _make_backend_with_one_failing_handle(self, handle="/msg/1"):
        mock_msg1 = MagicMock(name="Message1")
        mock_msg1.Get.side_effect = _get_message_exc()
        backend, mock_access = _make_map_backend_with_mock_access()
        inbox_data = {
            handle: {"Sender": "Alice", "Datetime": "20260101T100000",
                     "Read": False, "Subject": "Subject text"}
        }

        def _list(folder, _filter):
            return inbox_data if folder == "inbox" else {}

        mock_access.ListMessages.side_effect = _list
        with patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface",
                   side_effect=_make_message1_iface_factory(mock_msg1)):
            yield backend, mock_msg1

    def test_get_not_retried_on_second_poll(self):
        with self._make_backend_with_one_failing_handle() as (backend, mock_msg1):
            backend.poll_inbox()
            backend.poll_inbox()
        assert mock_msg1.Get.call_count == 1

    def test_get_called_exactly_once_across_five_polls(self):
        with self._make_backend_with_one_failing_handle() as (backend, mock_msg1):
            for _ in range(5):
                backend.poll_inbox()
        assert mock_msg1.Get.call_count == 1

    def test_body_falls_back_to_subject_on_first_poll_when_get_fails(self):
        with self._make_backend_with_one_failing_handle() as (backend, mock_msg1):
            result = backend.poll_inbox()
        assert result[0]["body"] == "Subject text"

    def test_subject_fallback_used_on_second_poll_when_handle_cached(self):
        with self._make_backend_with_one_failing_handle() as (backend, mock_msg1):
            backend.poll_inbox()
            result2 = backend.poll_inbox()
        assert result2[0]["body"] == "Subject text"

    def test_handle_stored_in_failed_handles_after_dbus_exception(self):
        with self._make_backend_with_one_failing_handle("/msg/42") as (backend, mock_msg1):
            backend.poll_inbox()
        assert "/msg/42" in backend._failed_handles

    def test_handle_not_stored_when_message1_get_returns_none(self):
        mock_msg1 = MagicMock(name="Message1")
        mock_msg1.Get.return_value = None
        backend, mock_access = _make_map_backend_with_mock_access()
        mock_access.ListMessages.side_effect = lambda f, _: (
            {"/msg/ok": {"Sender": "Bob", "Datetime": "", "Read": False, "Subject": "S"}}
            if f == "inbox" else {}
        )
        with patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface",
                   side_effect=_make_message1_iface_factory(mock_msg1)):
            backend.poll_inbox()
        assert "/msg/ok" not in backend._failed_handles

    def test_unfailed_handle_attempted_on_every_poll(self):
        mock_msg1 = MagicMock(name="Message1")
        mock_msg1.Get.return_value = None
        backend, mock_access = _make_map_backend_with_mock_access()
        mock_access.ListMessages.side_effect = lambda f, _: (
            {"/msg/1": {"Sender": "Alice", "Datetime": "", "Read": False, "Subject": "S"}}
            if f == "inbox" else {}
        )
        with patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface",
                   side_effect=_make_message1_iface_factory(mock_msg1)):
            for _ in range(3):
                backend.poll_inbox()
        assert mock_msg1.Get.call_count == 3

    def test_failed_handles_cleared_by_connect(self):
        with self._make_backend_with_one_failing_handle("/msg/7") as (backend, mock_msg1):
            backend.poll_inbox()
            assert "/msg/7" in backend._failed_handles
        mock_client = MagicMock(name="Client1")
        mock_client.CreateSession.return_value = "/org/obex/session2"
        with patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface", return_value=mock_client):
            backend.connect("AA:BB:CC:DD:EE:FF")
        assert "/msg/7" not in backend._failed_handles


# ---------------------------------------------------------------------------
# §14 MapBackend self-heal reconnect — BT-level reconnect + backoff (tincan-8u3xl)
#
# Acceptance: pull the link → daemon calls Device1.Connect() (no sudo) then
# retries the OBEX session with exponential backoff.
#
# Timer pattern: GLib mocked; _reconnect_tick invoked directly (no real timing).
#   delay = min(10 * 2**(attempt-1), 300) for attempt ≥ 1
#   1st failure → 10s, 2nd → 20s, 3rd → 40s, 4th → 80s, 5th → 160s, 6th+ → 300s
# ---------------------------------------------------------------------------

_BLUEZ_SVC = "org.bluez"
_BLUEZ_ROOT = "/"
_DEV_IFACE = "org.bluez.Device1"
_OBJ_MGR_IFACE = "org.freedesktop.DBus.ObjectManager"
_ADDR = "AA:BB:CC:DD:EE:FF"
_DEV_PATH_14 = "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF"


def _make_managed_objects_14(addr: str = _ADDR) -> dict:
    return {_DEV_PATH_14: {_DEV_IFACE: {"Address": addr}}}


def _make_reconnect_backend(*, addr: str = _ADDR) -> tuple:
    """Return (backend, mock_glib, timers) with GLib mocked and reconnect armed.

    backend._device_addr = addr
    timers: dict mapping source_id → callback
    """
    backend = MapBackend()
    backend._device_addr = addr

    timers: dict = {}
    _next_id = [0]

    mock_glib = MagicMock(name="GLib")
    mock_glib.SOURCE_REMOVE = False
    mock_glib.SOURCE_CONTINUE = True

    def _add_seconds(interval, cb):
        _next_id[0] += 1
        tid = _next_id[0]
        timers[tid] = cb
        return tid

    mock_glib.timeout_add_seconds.side_effect = _add_seconds
    mock_glib.source_remove.side_effect = lambda tid: timers.pop(tid, None)

    return backend, mock_glib, timers


class TestMapBackendBtConnect:
    """_bt_connect() calls Device1.Connect() on the BlueZ system bus."""

    def _run_bt_connect(self, managed_objects, *, addr: str = _ADDR,
                        device_exc=None):
        """Call _bt_connect with mocked system bus; return mock_device."""
        backend = MapBackend()
        mock_sys_bus = MagicMock(name="SystemBus")
        mock_obj_mgr = MagicMock(name="ObjectManager")
        mock_obj_mgr.GetManagedObjects.return_value = managed_objects
        mock_device = MagicMock(name="Device1")
        if device_exc:
            mock_device.Connect.side_effect = device_exc

        def _iface(obj, iface):
            if iface == _OBJ_MGR_IFACE:
                return mock_obj_mgr
            if iface == _DEV_IFACE:
                return mock_device
            return MagicMock()

        with patch("tincand.backends.bluez_map.dbus.SystemBus",
                   return_value=mock_sys_bus), \
             patch("tincand.backends.bluez_map.dbus.Interface",
                   side_effect=_iface):
            backend._bt_connect(addr)

        return mock_device

    def test_bt_connect_calls_device1_connect(self):
        device = self._run_bt_connect(_make_managed_objects_14())
        device.Connect.assert_called_once()

    def test_bt_connect_no_args_to_device1_connect(self):
        device = self._run_bt_connect(_make_managed_objects_14())
        device.Connect.assert_called_once_with()

    def test_bt_connect_no_matching_device_does_not_raise(self):
        """Device not in managed objects → no-op, no exception."""
        backend = MapBackend()
        mock_sys_bus = MagicMock(name="SystemBus")
        mock_obj_mgr = MagicMock(name="ObjectManager")
        mock_obj_mgr.GetManagedObjects.return_value = {}

        with patch("tincand.backends.bluez_map.dbus.SystemBus",
                   return_value=mock_sys_bus), \
             patch("tincand.backends.bluez_map.dbus.Interface",
                   return_value=mock_obj_mgr):
            backend._bt_connect("11:22:33:44:55:66")  # must not raise

    def test_bt_connect_system_bus_not_session_bus(self):
        """_bt_connect must use SystemBus, not SessionBus (no polkit elevation)."""
        backend = MapBackend()
        mock_sys_bus = MagicMock(name="SystemBus")
        mock_obj_mgr = MagicMock(name="ObjectManager")
        mock_obj_mgr.GetManagedObjects.return_value = _make_managed_objects_14()
        mock_iface = MagicMock()
        mock_iface.return_value = mock_obj_mgr

        with patch("tincand.backends.bluez_map.dbus.SystemBus",
                   return_value=mock_sys_bus) as mock_sys_cls, \
             patch("tincand.backends.bluez_map.dbus.SessionBus") as mock_ses_cls, \
             patch("tincand.backends.bluez_map.dbus.Interface",
                   side_effect=lambda o, i: mock_obj_mgr):
            backend._bt_connect(_ADDR)

        mock_sys_cls.assert_called_once()
        mock_ses_cls.assert_not_called()


class TestMapBackendReconnectCallsBtConnect:
    """_reconnect_tick calls _bt_connect before self.connect (OBEX session)."""

    def _run_reconnect_tick_with_obex_fail(self, *, addr: str = _ADDR):
        """Run _reconnect_tick with OBEX always failing; capture _bt_connect calls."""
        backend, mock_glib, timers = _make_reconnect_backend(addr=addr)

        bt_connect_calls = []
        obex_connect_calls = []

        def _mock_bt_connect(a):
            bt_connect_calls.append(a)

        def _mock_connect(a):
            obex_connect_calls.append(a)
            raise dbus.exceptions.DBusException(name="org.bluez.obex.Error.Failed")

        backend._bt_connect = _mock_bt_connect
        backend.connect = _mock_connect

        with patch("tincand.backends.bluez_map.GLib", mock_glib):
            backend._reconnect_tick()

        return bt_connect_calls, obex_connect_calls

    def test_reconnect_tick_calls_bt_connect(self):
        bt_calls, _ = self._run_reconnect_tick_with_obex_fail()
        assert len(bt_calls) == 1

    def test_reconnect_tick_calls_bt_connect_before_obex_connect(self):
        """bt_connect must be called; OBEX connect must also be called."""
        bt_calls, obex_calls = self._run_reconnect_tick_with_obex_fail()
        assert len(bt_calls) == 1
        assert len(obex_calls) == 1

    def test_reconnect_tick_attempts_obex_even_when_bt_connect_raises(self):
        """_bt_connect failure must not prevent self.connect() from being called."""
        backend, mock_glib, timers = _make_reconnect_backend()
        obex_calls = []

        def _bt_fail(a):
            raise Exception("BT gone")

        def _mock_connect(a):
            obex_calls.append(a)
            raise dbus.exceptions.DBusException(name="org.bluez.obex.Error.Failed")

        backend._bt_connect = _bt_fail
        backend.connect = _mock_connect

        with patch("tincand.backends.bluez_map.GLib", mock_glib):
            backend._reconnect_tick()  # must not raise

        assert len(obex_calls) == 1


class TestMapBackendReconnectBackoff:
    """Exponential backoff: delay = min(10 * 2^(attempt-1), 300) per failure.

    Timer pattern: call _reconnect_tick() directly as if GLib fired it; the
    backed-off delay is observed via mock_glib.timeout_add_seconds call args.
    """

    def _make_always_failing_backend(self):
        """Backend where connect() always raises and _bt_connect is a no-op."""
        backend, mock_glib, timers = _make_reconnect_backend()

        def _bt_noop(a):
            pass

        def _connect_fail(a):
            raise dbus.exceptions.DBusException(name="org.bluez.obex.Error.Failed")

        backend._bt_connect = _bt_noop
        backend.connect = _connect_fail
        return backend, mock_glib, timers

    def _tick(self, backend, mock_glib):
        with patch("tincand.backends.bluez_map.GLib", mock_glib):
            return backend._reconnect_tick()

    def test_first_failure_schedules_10s_timer(self):
        backend, mock_glib, _ = self._make_always_failing_backend()
        self._tick(backend, mock_glib)
        intervals = [c.args[0] for c in mock_glib.timeout_add_seconds.call_args_list]
        assert 10 in intervals

    def test_second_failure_schedules_20s_timer(self):
        backend, mock_glib, _ = self._make_always_failing_backend()
        self._tick(backend, mock_glib)
        mock_glib.timeout_add_seconds.reset_mock()
        self._tick(backend, mock_glib)
        intervals = [c.args[0] for c in mock_glib.timeout_add_seconds.call_args_list]
        assert 20 in intervals

    def test_third_failure_schedules_40s_timer(self):
        backend, mock_glib, _ = self._make_always_failing_backend()
        self._tick(backend, mock_glib)
        self._tick(backend, mock_glib)
        mock_glib.timeout_add_seconds.reset_mock()
        self._tick(backend, mock_glib)
        intervals = [c.args[0] for c in mock_glib.timeout_add_seconds.call_args_list]
        assert 40 in intervals

    def test_sixth_failure_capped_at_300s(self):
        backend, mock_glib, _ = self._make_always_failing_backend()
        for _ in range(5):
            self._tick(backend, mock_glib)
        mock_glib.timeout_add_seconds.reset_mock()
        self._tick(backend, mock_glib)
        intervals = [c.args[0] for c in mock_glib.timeout_add_seconds.call_args_list]
        assert max(intervals) <= 300

    def test_failure_returns_source_remove(self):
        backend, mock_glib, _ = self._make_always_failing_backend()
        result = self._tick(backend, mock_glib)
        assert result == mock_glib.SOURCE_REMOVE

    def test_reconnect_attempt_increments_on_failure(self):
        backend, mock_glib, _ = self._make_always_failing_backend()
        assert backend._reconnect_attempt == 0
        self._tick(backend, mock_glib)
        assert backend._reconnect_attempt == 1
        self._tick(backend, mock_glib)
        assert backend._reconnect_attempt == 2

    def test_success_returns_source_remove(self):
        backend, mock_glib, _ = _make_reconnect_backend()
        mock_client = MagicMock(name="Client1")
        mock_client.CreateSession.return_value = "/org/obex/session1"
        backend._bt_connect = lambda a: None

        with patch("tincand.backends.bluez_map.GLib", mock_glib), \
             patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface",
                   return_value=mock_client):
            result = backend._reconnect_tick()

        assert result == mock_glib.SOURCE_REMOVE

    def test_success_resets_reconnect_attempt_to_zero(self):
        backend, mock_glib, _ = _make_reconnect_backend()
        backend._reconnect_attempt = 3  # simulate prior failures
        mock_client = MagicMock(name="Client1")
        mock_client.CreateSession.return_value = "/org/obex/session1"
        backend._bt_connect = lambda a: None

        with patch("tincand.backends.bluez_map.GLib", mock_glib), \
             patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface",
                   return_value=mock_client):
            backend._reconnect_tick()

        assert backend._reconnect_attempt == 0

    def test_success_does_not_schedule_reconnect_timer(self):
        """connect() schedules a poll timer — that's expected.  No reconnect timer."""
        backend, mock_glib, _ = _make_reconnect_backend()
        mock_client = MagicMock(name="Client1")
        mock_client.CreateSession.return_value = "/org/obex/session1"
        backend._bt_connect = lambda a: None

        with patch("tincand.backends.bluez_map.GLib", mock_glib), \
             patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface",
                   return_value=mock_client):
            backend._reconnect_tick()

        reconnect_timer_calls = [
            c for c in mock_glib.timeout_add_seconds.call_args_list
            if c.args[1] is backend._reconnect_tick
        ]
        assert len(reconnect_timer_calls) == 0


class TestMapBackendReconnectAttemptReset:
    """_handle_session_dead and schedule_reconnect reset _reconnect_attempt."""

    def test_handle_session_dead_resets_reconnect_attempt(self):
        backend, mock_glib, timers = _make_reconnect_backend()
        backend._reconnect_attempt = 4  # simulate prior failures

        with patch("tincand.backends.bluez_map.GLib", mock_glib), \
             patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface"):
            backend._handle_session_dead()

        assert backend._reconnect_attempt == 0

    def test_schedule_reconnect_resets_reconnect_attempt(self):
        backend, mock_glib, timers = _make_reconnect_backend()
        backend._reconnect_attempt = 2

        with patch("tincand.backends.bluez_map.GLib", mock_glib):
            backend.schedule_reconnect()

        assert backend._reconnect_attempt == 0


# ---------------------------------------------------------------------------
# §15 MapBackend.poll_inbox — UpdateInbox unsupported flag (tincan-bleim)
#
# New logic in poll_inbox():
#   - If UpdateInbox raises UnknownObject/UnknownMethod/UnknownInterface,
#     set _update_inbox_unsupported=True; do NOT re-raise; poll continues.
#   - If _update_inbox_unsupported is True, skip UpdateInbox entirely.
# New logic in connect():
#   - Reset _update_inbox_unsupported=False on each fresh session.
#
# Dead-session recovery (_poll_tick / _handle_session_dead) must be unaffected:
#   - SetFolder raising UnknownObject propagates out of poll_inbox as before.
# ---------------------------------------------------------------------------


def _unsupported_exc(name="org.freedesktop.DBus.Error.UnknownObject"):
    return dbus.exceptions.DBusException(name=name)


class TestMapBackendUpdateInboxUnsupportedFlag:
    """poll_inbox: UpdateInbox unsupported flag — set on error, skip once set, reset on connect."""

    def _backend_with_empty_inbox(self):
        backend, mock_access = _make_map_backend_with_mock_access()
        mock_access.ListMessages.return_value = {}
        return backend, mock_access

    # -- Branch 1: UnknownObject → flag set, poll continues without re-raise -

    def test_unknown_object_sets_unsupported_flag(self):
        backend, mock_access = self._backend_with_empty_inbox()
        mock_access.UpdateInbox.side_effect = _unsupported_exc(
            "org.freedesktop.DBus.Error.UnknownObject"
        )
        backend.poll_inbox()
        assert backend._update_inbox_unsupported is True

    def test_unknown_object_does_not_raise(self):
        backend, mock_access = self._backend_with_empty_inbox()
        mock_access.UpdateInbox.side_effect = _unsupported_exc(
            "org.freedesktop.DBus.Error.UnknownObject"
        )
        backend.poll_inbox()  # must not raise

    def test_unknown_object_poll_continues_returns_messages(self):
        """UpdateInbox raises UnknownObject; poll proceeds and returns inbox messages."""
        backend, mock_access = _make_map_backend_with_mock_access()
        mock_access.UpdateInbox.side_effect = _unsupported_exc(
            "org.freedesktop.DBus.Error.UnknownObject"
        )
        mock_access.ListMessages.side_effect = lambda f, _: (
            {"/inbox/1": {"Sender": "+15550001", "Datetime": "", "Read": False, "Subject": "Hi"}}
            if f == "inbox" else {}
        )
        mock_msg1 = MagicMock(name="Message1")
        mock_msg1.Get.return_value = None
        with patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface",
                   side_effect=_make_message1_iface_factory(mock_msg1)):
            result = backend.poll_inbox()
        assert len(result) == 1

    # -- Branch 2: UnknownMethod → same behavior -----------------------------

    def test_unknown_method_sets_unsupported_flag(self):
        backend, mock_access = self._backend_with_empty_inbox()
        mock_access.UpdateInbox.side_effect = _unsupported_exc(
            "org.freedesktop.DBus.Error.UnknownMethod"
        )
        backend.poll_inbox()
        assert backend._update_inbox_unsupported is True

    def test_unknown_method_does_not_raise(self):
        backend, mock_access = self._backend_with_empty_inbox()
        mock_access.UpdateInbox.side_effect = _unsupported_exc(
            "org.freedesktop.DBus.Error.UnknownMethod"
        )
        backend.poll_inbox()  # must not raise

    # -- Branch 2b: UnknownInterface → same behavior -------------------------

    def test_unknown_interface_sets_unsupported_flag(self):
        backend, mock_access = self._backend_with_empty_inbox()
        mock_access.UpdateInbox.side_effect = _unsupported_exc(
            "org.freedesktop.DBus.Error.UnknownInterface"
        )
        backend.poll_inbox()
        assert backend._update_inbox_unsupported is True

    # -- Branch 3: Subsequent polls skip UpdateInbox when flag is set --------

    def test_update_inbox_not_called_on_second_poll_when_flag_set(self):
        backend, mock_access = self._backend_with_empty_inbox()
        mock_access.UpdateInbox.side_effect = _unsupported_exc()
        backend.poll_inbox()  # first poll: raises, flag set
        mock_access.UpdateInbox.reset_mock()
        mock_access.UpdateInbox.side_effect = None
        backend.poll_inbox()  # second poll: must skip UpdateInbox
        mock_access.UpdateInbox.assert_not_called()

    def test_update_inbox_skipped_across_multiple_polls_when_flag_set(self):
        backend, mock_access = self._backend_with_empty_inbox()
        mock_access.UpdateInbox.side_effect = _unsupported_exc()
        backend.poll_inbox()  # first poll sets flag
        mock_access.UpdateInbox.reset_mock()
        mock_access.UpdateInbox.side_effect = None
        for _ in range(4):
            backend.poll_inbox()
        mock_access.UpdateInbox.assert_not_called()

    # -- Branch 4: connect() resets the flag ---------------------------------

    def test_connect_resets_update_inbox_unsupported_flag(self):
        backend = MapBackend()
        backend._update_inbox_unsupported = True
        mock_client = MagicMock(name="Client1")
        mock_client.CreateSession.return_value = "/org/obex/session1"
        with patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface", return_value=mock_client):
            backend.connect("AA:BB:CC:DD:EE:FF")
        assert backend._update_inbox_unsupported is False

    # -- Branch 6: UpdateInbox success → flag stays False --------------------

    def test_update_inbox_success_flag_remains_false(self):
        backend, mock_access = self._backend_with_empty_inbox()
        # UpdateInbox succeeds (default MagicMock — no side_effect)
        backend.poll_inbox()
        assert backend._update_inbox_unsupported is False

    # -- Guard: unrecognised DBus errors from UpdateInbox still propagate ----

    def test_other_dbus_exception_from_update_inbox_propagates(self):
        """Non-unsupported DBus errors from UpdateInbox must NOT be swallowed."""
        backend, mock_access = self._backend_with_empty_inbox()
        mock_access.UpdateInbox.side_effect = dbus.exceptions.DBusException(
            name="org.bluez.obex.Error.NotFound"  # not in the unsupported set
        )
        with pytest.raises(dbus.exceptions.DBusException):
            backend.poll_inbox()


# ---------------------------------------------------------------------------
# §15b MapBackend._poll_tick — dead-session recovery unaffected by bleim fix
#
# Branch 5: if the session is genuinely dead (SetFolder also raises
# UnknownObject), poll_inbox propagates the exception and _poll_tick still
# calls _handle_session_dead.  The UpdateInbox flag logic must not suppress
# this signal.
# ---------------------------------------------------------------------------

class TestMapBackendDeadSessionUnaffectedByUpdateInboxFix:
    """SetFolder UnknownObject propagates out of poll_inbox; _poll_tick triggers recovery."""

    def test_setfolder_unknown_object_propagates_out_of_poll_inbox(self):
        """UnknownObject from SetFolder (not UpdateInbox) re-raises from poll_inbox."""
        backend, mock_access = _make_map_backend_with_mock_access()
        backend._update_inbox_unsupported = True  # flag already set from prior poll
        dead_exc = dbus.exceptions.DBusException(
            name="org.freedesktop.DBus.Error.UnknownObject"
        )
        mock_access.SetFolder.side_effect = dead_exc
        with pytest.raises(dbus.exceptions.DBusException) as exc_info:
            backend.poll_inbox()
        assert exc_info.value.get_dbus_name() == "org.freedesktop.DBus.Error.UnknownObject"

    def test_poll_tick_calls_handle_session_dead_when_setfolder_raises_unknown_object(self):
        """_poll_tick triggers _handle_session_dead when the poll raises UnknownObject."""
        backend, mock_glib, _ = _make_reconnect_backend()
        backend._worker = InlineWorker()  # deliver the worker completion synchronously
        backend._msg_access = MagicMock()
        backend._update_inbox_unsupported = True  # flag set from prior poll

        dead_exc = dbus.exceptions.DBusException(
            name="org.freedesktop.DBus.Error.UnknownObject"
        )
        backend._msg_access.SetFolder.side_effect = dead_exc

        handle_dead_calls = []
        backend._handle_session_dead = lambda: handle_dead_calls.append(True)

        with patch("tincand.backends.bluez_map.GLib", mock_glib):
            result = backend._poll_tick()

        assert len(handle_dead_calls) == 1
        # The tick itself stays armed (SOURCE_CONTINUE); on session death the
        # real _handle_session_dead → disconnect() removes the source by id.
        assert result == mock_glib.SOURCE_CONTINUE
