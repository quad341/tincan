"""Tests: MockBackend and MapBackend unit tests.
Bead: tincan-spa, tincan-44wr, tincan-kf1k, tincan-br25

Coverage:
  §1 MockBackend.connect() — loads canned conversations, calls service.Connect(), requires service
  §2 MockBackend.disconnect() — removes GLib timer, calls service.Disconnect(), safe when idle
  §3 MockBackend stub returns — poll_inbox/get_message/send_message return correct stub values
  §4 MapBackend.connect() — successful session stored; Forbidden → ConsentRequired; other exc re-raised
  §5 MapBackend.disconnect() — no-op when no session; removes session; clears state; logs on error
  §9 MapBackend._resolve_device_name — returns BlueZ Alias; fallback to addr on empty/miss/DBusException
  §10 MapBackend.connect() — set_capability('messages', True) and set_device_name called on service
  §11 MapBackend.poll_inbox — direction='inbound' for inbox, 'outbound' for sent
  §12 MapBackend.poll_inbox — sent folder DBusException swallowed; inbox messages still returned
  §14 MapBackend — dead-session detection + reconnect (tincan-kf1k)
     _poll_tick: UnknownObject → _handle_session_dead() + SOURCE_REMOVE; other exceptions → SOURCE_CONTINUE
     _handle_session_dead: svc.Disconnect() called; poll timer not double-removed; reconnect timer scheduled
     _reconnect_tick: success → connect() + SOURCE_REMOVE; failure → SOURCE_CONTINUE; empty addr → SOURCE_REMOVE
     connect(): _device_addr stored; pending reconnect timer cancelled
     disconnect(): reconnect timer cancelled
  §15 MapBackend.poll_inbox — sent folder fallback to outbox (tincan-br25)
     - 'sent' raises DBusException, 'outbox' succeeds: outbox messages returned
     - both 'sent' and 'outbox' raise DBusException: WARNING logged, no outbound messages
     - both fail: inbox messages still returned

No hardware or real D-Bus — all D-Bus objects mocked.
Run with: python -m pytest tests/tincand/test_backends.py -v
"""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import dbus.exceptions
import pytest

import dbus

from tincand.backends.base import BackendInterface
from tincand.backends.mock import MockBackend
from tincand.backends.bluez_map import ConsentRequired, MapBackend


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

        with patch("tincand.backends.bluez_map.dbus.SessionBus") as mock_bus_cls, \
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
# §6 MapBackend.poll_inbox — SetFolder navigation to telecom/msg
# ---------------------------------------------------------------------------

class TestMapBackendPollInboxFolderNav:
    """poll_inbox ascends twice then descends telecom→msg before listing."""

    def _run_poll(self, set_folder_side_effect=None):
        backend, mock_access = _make_map_backend_with_mock_access()
        if set_folder_side_effect is not None:
            mock_access.SetFolder.side_effect = set_folder_side_effect
        mock_access.ListMessages.return_value = {}
        backend.poll_inbox()
        return mock_access

    def test_poll_inbox_returns_empty_when_msg_access_is_none(self):
        backend = MapBackend()
        assert backend.poll_inbox() == []

    def test_set_folder_called_four_times_total(self):
        mock_access = self._run_poll()
        assert mock_access.SetFolder.call_count == 4

    def test_set_folder_first_two_calls_are_ascend(self):
        mock_access = self._run_poll()
        calls = mock_access.SetFolder.call_args_list
        assert calls[0] == call("") and calls[1] == call("")

    def test_set_folder_third_call_is_telecom(self):
        mock_access = self._run_poll()
        calls = mock_access.SetFolder.call_args_list
        assert calls[2] == call("telecom")

    def test_set_folder_fourth_call_is_msg(self):
        mock_access = self._run_poll()
        calls = mock_access.SetFolder.call_args_list
        assert calls[3] == call("msg")

    def test_set_folder_full_order_is_ascend_ascend_telecom_msg(self):
        mock_access = self._run_poll()
        args_seq = [c[0][0] for c in mock_access.SetFolder.call_args_list]
        assert args_seq == ["", "", "telecom", "msg"]

    def test_dbus_exc_on_ascend_is_swallowed_and_descent_proceeds(self):
        def _raise_for_empty(arg):
            if arg == "":
                raise dbus.exceptions.DBusException(
                    name="org.bluez.obex.Error.NotFound"
                )

        mock_access = self._run_poll(set_folder_side_effect=_raise_for_empty)
        descent_args = [
            c[0][0] for c in mock_access.SetFolder.call_args_list if c[0][0] != ""
        ]
        assert descent_args == ["telecom", "msg"]

    def test_list_messages_called_with_inbox_and_empty_filter(self):
        mock_access = self._run_poll()
        mock_access.ListMessages.assert_called_once_with("inbox", {})


# ---------------------------------------------------------------------------
# §7 MapBackend.poll_inbox — body fallback chain Text → Subject → "New message"
# ---------------------------------------------------------------------------

class TestMapBackendPollInboxBodyFallback:
    """Body is read from Text, then Subject, then the literal 'New message'."""

    def _poll_body(self, **props):
        """Run poll_inbox with a single message carrying the given props."""
        backend, mock_access = _make_map_backend_with_mock_access()
        mock_access.ListMessages.return_value = {"/msg/1": props}
        result = backend.poll_inbox()
        return result[0]["body"] if result else None

    def test_text_present_uses_text(self):
        assert self._poll_body(Text="Hello text", Subject="subj",
                               Sender="A", Datetime="", Read=False) == "Hello text"

    def test_text_empty_subject_present_uses_subject(self):
        assert self._poll_body(Text="", Subject="Hello subject",
                               Sender="A", Datetime="", Read=False) == "Hello subject"

    def test_text_absent_subject_present_uses_subject(self):
        assert self._poll_body(Subject="Subject only",
                               Sender="A", Datetime="", Read=False) == "Subject only"

    def test_text_whitespace_only_falls_through_to_subject(self):
        assert self._poll_body(Text="   ", Subject="Subj wins",
                               Sender="A", Datetime="", Read=False) == "Subj wins"

    def test_text_empty_subject_empty_uses_new_message(self):
        assert self._poll_body(Text="", Subject="",
                               Sender="A", Datetime="", Read=False) == "New message"

    def test_text_absent_subject_absent_uses_new_message(self):
        assert self._poll_body(Sender="A", Datetime="", Read=False) == "New message"

    def test_text_whitespace_subject_whitespace_uses_new_message(self):
        assert self._poll_body(Text="  ", Subject="  ",
                               Sender="A", Datetime="", Read=False) == "New message"

    def test_text_wins_over_subject_when_both_non_empty(self):
        assert self._poll_body(Text="Text body", Subject="Subject body",
                               Sender="A", Datetime="", Read=False) == "Text body"

    def test_text_is_stripped(self):
        assert self._poll_body(Text="  stripped  ", Subject="subj",
                               Sender="A", Datetime="", Read=False) == "stripped"

    def test_subject_is_stripped_when_text_absent(self):
        assert self._poll_body(Text="", Subject="  also stripped  ",
                               Sender="A", Datetime="", Read=False) == "also stripped"


# ---------------------------------------------------------------------------
# §8 MapBackend._fetch_full_body — GetMessage called with 3 args
# ---------------------------------------------------------------------------

class TestMapBackendFetchFullBodyGetMessageArgs:
    """_fetch_full_body passes (handle, '', {Attachment: False}) to GetMessage."""

    def _call_fetch(self, handle="/msg/handle1"):
        backend, mock_access = _make_map_backend_with_mock_access()
        mock_access.GetMessage.return_value = None  # triggers early-return path
        backend._fetch_full_body(handle)
        return mock_access

    def test_fetch_full_body_returns_none_when_msg_access_is_none(self):
        backend = MapBackend()
        assert backend._fetch_full_body("/msg/1") is None

    def test_get_message_called_once(self):
        mock_access = self._call_fetch()
        assert mock_access.GetMessage.call_count == 1

    def test_get_message_called_with_three_positional_args(self):
        mock_access = self._call_fetch()
        args = mock_access.GetMessage.call_args[0]
        assert len(args) == 3

    def test_get_message_first_arg_is_handle(self):
        mock_access = self._call_fetch("/msg/handle1")
        args = mock_access.GetMessage.call_args[0]
        assert args[0] == "/msg/handle1"

    def test_get_message_second_arg_is_empty_string(self):
        mock_access = self._call_fetch()
        args = mock_access.GetMessage.call_args[0]
        assert args[1] == ""

    def test_get_message_third_arg_has_attachment_key(self):
        mock_access = self._call_fetch()
        args = mock_access.GetMessage.call_args[0]
        assert "Attachment" in args[2]

    def test_get_message_attachment_value_is_false(self):
        mock_access = self._call_fetch()
        args = mock_access.GetMessage.call_args[0]
        assert not args[2]["Attachment"]


# ---------------------------------------------------------------------------
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
            mock_mgr.GetManagedObjects.return_value = managed_objects if managed_objects is not None else {}

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
# §14 MapBackend — dead-session detection + reconnect (tincan-kf1k)
# ---------------------------------------------------------------------------

_RECONNECT_INTERVAL = 10  # must match _RECONNECT_INTERVAL_SECONDS in bluez_map.py


def _unknown_object_exc():
    """Dead MAP session: org.freedesktop.DBus.Error.UnknownObject."""
    return dbus.exceptions.DBusException(name="org.freedesktop.DBus.Error.UnknownObject")


def _unknown_method_exc():
    """BlueZ API gap (NOT dead session): org.freedesktop.DBus.Error.UnknownMethod."""
    return dbus.exceptions.DBusException(name="org.freedesktop.DBus.Error.UnknownMethod")


def _make_backend_with_update_inbox_exc(exc):
    """MapBackend with _msg_access wired to raise *exc* on UpdateInbox."""
    backend = MapBackend()
    mock_access = MagicMock(name="MessageAccess1")
    mock_access.UpdateInbox.side_effect = exc
    backend._msg_access = mock_access
    return backend


class TestMapBackendPollTickDeadSession:
    """_poll_tick: UnknownObject → recovery; other exceptions → SOURCE_CONTINUE."""

    def _run_poll_tick(self, exc, device_addr="AA:BB:CC:DD:EE:FF"):
        """Run _poll_tick() with UpdateInbox raising *exc*; return (result, mock_glib, svc)."""
        backend = _make_backend_with_update_inbox_exc(exc)
        backend._device_addr = device_addr
        backend._session_path = "/org/obex/session1"
        svc = _make_service()
        backend.register_service(svc)

        with patch("tincand.backends.bluez_map.GLib") as mock_glib, \
             patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface"):
            mock_glib.SOURCE_REMOVE = False
            mock_glib.SOURCE_CONTINUE = True
            mock_glib.timeout_add_seconds.return_value = 77
            result = backend._poll_tick()

        return result, mock_glib, svc

    def test_unknown_object_returns_source_remove(self):
        result, _, _ = self._run_poll_tick(_unknown_object_exc())
        assert result is False

    def test_unknown_object_calls_service_disconnect(self):
        _, _, svc = self._run_poll_tick(_unknown_object_exc())
        svc.Disconnect.assert_called_once()

    def test_unknown_object_schedules_reconnect_timer(self):
        _, mock_glib, _ = self._run_poll_tick(_unknown_object_exc())
        mock_glib.timeout_add_seconds.assert_called_once()

    def test_unknown_object_reconnect_timer_uses_reconnect_interval(self):
        _, mock_glib, _ = self._run_poll_tick(_unknown_object_exc())
        interval = mock_glib.timeout_add_seconds.call_args[0][0]
        assert interval == _RECONNECT_INTERVAL

    def test_non_dead_dbus_exc_returns_source_continue(self):
        result, _, _ = self._run_poll_tick(_unknown_method_exc())
        assert result is True

    def test_non_dead_dbus_exc_does_not_schedule_reconnect(self):
        _, mock_glib, _ = self._run_poll_tick(_unknown_method_exc())
        mock_glib.timeout_add_seconds.assert_not_called()

    def test_non_dead_dbus_exc_does_not_call_service_disconnect(self):
        _, _, svc = self._run_poll_tick(_unknown_method_exc())
        svc.Disconnect.assert_not_called()

    def test_generic_exception_returns_source_continue(self):
        backend = _make_backend_with_update_inbox_exc(RuntimeError("boom"))
        backend._device_addr = "AA:BB:CC:DD:EE:FF"

        with patch("tincand.backends.bluez_map.GLib") as mock_glib:
            mock_glib.SOURCE_CONTINUE = True
            result = backend._poll_tick()

        assert result is True

    def test_generic_exception_does_not_schedule_reconnect(self):
        backend = _make_backend_with_update_inbox_exc(RuntimeError("boom"))
        backend._device_addr = "AA:BB:CC:DD:EE:FF"

        with patch("tincand.backends.bluez_map.GLib") as mock_glib:
            mock_glib.SOURCE_CONTINUE = True
            backend._poll_tick()

        mock_glib.timeout_add_seconds.assert_not_called()


class TestMapBackendHandleSessionDead:
    """_handle_session_dead: teardown + GUI disconnect + reconnect timer scheduling."""

    def _run_handle_session_dead(self, device_addr="AA:BB:CC:DD:EE:FF"):
        """Invoke _handle_session_dead with pre-set state; return (backend, mock_glib, svc)."""
        backend = MapBackend()
        backend._device_addr = device_addr
        backend._session_path = "/org/obex/session1"
        backend._poll_source_id = 42  # non-None: verify NOT double-removed
        svc = _make_service()
        backend.register_service(svc)

        with patch("tincand.backends.bluez_map.GLib") as mock_glib, \
             patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface"):
            mock_glib.timeout_add_seconds.return_value = 77
            backend._handle_session_dead()

        return backend, mock_glib, svc

    def test_service_disconnect_called(self):
        _, _, svc = self._run_handle_session_dead()
        svc.Disconnect.assert_called_once()

    def test_poll_source_id_not_passed_to_source_remove(self):
        # _poll_source_id is set to None BEFORE disconnect() runs, so GLib.source_remove
        # is never called with the poll timer ID (GLib removes it by SOURCE_REMOVE return).
        _, mock_glib, _ = self._run_handle_session_dead()
        removed_ids = [c[0][0] for c in mock_glib.source_remove.call_args_list]
        assert 42 not in removed_ids

    def test_reconnect_timer_scheduled_with_correct_interval(self):
        _, mock_glib, _ = self._run_handle_session_dead()
        mock_glib.timeout_add_seconds.assert_called_once()
        assert mock_glib.timeout_add_seconds.call_args[0][0] == _RECONNECT_INTERVAL

    def test_reconnect_timer_callback_is_reconnect_tick(self):
        backend, mock_glib, _ = self._run_handle_session_dead()
        cb = mock_glib.timeout_add_seconds.call_args[0][1]
        assert cb == backend._reconnect_tick

    def test_reconnect_timer_stored_in_reconnect_source_id(self):
        backend, _, _ = self._run_handle_session_dead()
        assert backend._reconnect_source_id == 77

    def test_no_reconnect_timer_when_device_addr_empty(self):
        _, mock_glib, _ = self._run_handle_session_dead(device_addr="")
        mock_glib.timeout_add_seconds.assert_not_called()


class TestMapBackendReconnectTick:
    """_reconnect_tick: retries connect(); SOURCE_REMOVE on success, SOURCE_CONTINUE on failure."""

    def test_success_calls_connect_with_device_addr(self):
        backend = MapBackend()
        backend._device_addr = "AA:BB:CC:DD:EE:FF"
        backend.connect = MagicMock()

        with patch("tincand.backends.bluez_map.GLib") as mock_glib:
            mock_glib.SOURCE_REMOVE = False
            backend._reconnect_tick()

        backend.connect.assert_called_once_with("AA:BB:CC:DD:EE:FF")

    def test_success_returns_source_remove(self):
        backend = MapBackend()
        backend._device_addr = "AA:BB:CC:DD:EE:FF"
        backend.connect = MagicMock()

        with patch("tincand.backends.bluez_map.GLib") as mock_glib:
            mock_glib.SOURCE_REMOVE = False
            result = backend._reconnect_tick()

        assert result is False

    def test_failure_returns_source_continue(self):
        backend = MapBackend()
        backend._device_addr = "AA:BB:CC:DD:EE:FF"
        backend.connect = MagicMock(side_effect=Exception("BT unavailable"))

        with patch("tincand.backends.bluez_map.GLib") as mock_glib:
            mock_glib.SOURCE_CONTINUE = True
            result = backend._reconnect_tick()

        assert result is True

    def test_failure_does_not_clear_reconnect_source_id(self):
        # SOURCE_CONTINUE means the timer keeps running; _reconnect_source_id stays set.
        backend = MapBackend()
        backend._device_addr = "AA:BB:CC:DD:EE:FF"
        backend._reconnect_source_id = 55
        backend.connect = MagicMock(side_effect=Exception("BT unavailable"))

        with patch("tincand.backends.bluez_map.GLib") as mock_glib:
            mock_glib.SOURCE_CONTINUE = True
            backend._reconnect_tick()

        assert backend._reconnect_source_id == 55

    def test_empty_device_addr_returns_source_remove(self):
        backend = MapBackend()
        backend._device_addr = ""
        backend.connect = MagicMock()

        with patch("tincand.backends.bluez_map.GLib") as mock_glib:
            mock_glib.SOURCE_REMOVE = False
            result = backend._reconnect_tick()

        assert result is False

    def test_empty_device_addr_does_not_call_connect(self):
        backend = MapBackend()
        backend._device_addr = ""
        backend.connect = MagicMock()

        with patch("tincand.backends.bluez_map.GLib") as mock_glib:
            mock_glib.SOURCE_REMOVE = False
            backend._reconnect_tick()

        backend.connect.assert_not_called()


class TestMapBackendConnectDisconnectTimers:
    """connect() stores _device_addr and cancels pending reconnect; disconnect() cancels reconnect."""

    def test_connect_stores_device_addr(self):
        backend = MapBackend()
        mock_client = MagicMock()
        mock_client.CreateSession.return_value = "/org/obex/session1"

        with patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface", return_value=mock_client), \
             patch("tincand.backends.bluez_map.GLib"):
            backend.connect("AA:BB:CC:DD:EE:FF")

        assert backend._device_addr == "AA:BB:CC:DD:EE:FF"

    def test_connect_cancels_pending_reconnect_timer(self):
        backend = MapBackend()
        backend._reconnect_source_id = 99
        mock_client = MagicMock()
        mock_client.CreateSession.return_value = "/org/obex/session1"

        with patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface", return_value=mock_client), \
             patch("tincand.backends.bluez_map.GLib") as mock_glib:
            backend.connect("AA:BB:CC:DD:EE:FF")

        mock_glib.source_remove.assert_any_call(99)

    def test_connect_clears_reconnect_source_id_after_cancel(self):
        backend = MapBackend()
        backend._reconnect_source_id = 99
        mock_client = MagicMock()
        mock_client.CreateSession.return_value = "/org/obex/session1"

        with patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface", return_value=mock_client), \
             patch("tincand.backends.bluez_map.GLib"):
            backend.connect("AA:BB:CC:DD:EE:FF")

        assert backend._reconnect_source_id is None

    def test_disconnect_cancels_reconnect_timer(self):
        backend = MapBackend()
        backend._reconnect_source_id = 55
        backend._session_path = "/org/obex/session1"

        with patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface"), \
             patch("tincand.backends.bluez_map.GLib") as mock_glib:
            backend.disconnect()

        mock_glib.source_remove.assert_any_call(55)

    def test_disconnect_clears_reconnect_source_id(self):
        backend = MapBackend()
        backend._reconnect_source_id = 55
        backend._session_path = None  # no session — early return after timer cancel

        with patch("tincand.backends.bluez_map.GLib"):
            backend.disconnect()

        assert backend._reconnect_source_id is None


# ---------------------------------------------------------------------------
# §15 MapBackend.poll_inbox — sent folder fallback to outbox (tincan-br25)
# ---------------------------------------------------------------------------

def _dbus_exc(name="org.bluez.obex.Error.NotFound"):
    return dbus.exceptions.DBusException(name=name)


class TestMapBackendPollInboxOutboxFallback:
    """poll_inbox falls back to 'outbox' when 'sent' is unavailable."""

    def _make_backend_with_inbox_and_folders(self, sent_raises, outbox_raises):
        backend, mock_access = _make_map_backend_with_mock_access()
        mock_access.GetMessage.return_value = None

        def _list(folder, _filter):
            if folder == "inbox":
                return {"/inbox/1": {
                    "Sender": "Alice", "Datetime": "20260101T100000",
                    "Read": False, "Subject": "Hi",
                }}
            if folder == "sent":
                if sent_raises:
                    raise _dbus_exc()
                return {"/sent/1": {
                    "RecipientAddressing": "+15550001", "Datetime": "20260101T110000",
                    "Subject": "Hey",
                }}
            if folder == "outbox":
                if outbox_raises:
                    raise _dbus_exc()
                return {"/outbox/1": {
                    "RecipientAddressing": "+15550002", "Datetime": "20260101T120000",
                    "Subject": "From outbox",
                }}
            return {}

        mock_access.ListMessages.side_effect = _list
        return backend, mock_access

    def test_sent_success_does_not_try_outbox(self):
        backend, mock_access = self._make_backend_with_inbox_and_folders(
            sent_raises=False, outbox_raises=False
        )
        backend.poll_inbox()

        folders_tried = [c[0][0] for c in mock_access.ListMessages.call_args_list]
        assert "outbox" not in folders_tried

    def test_sent_fails_outbox_succeeds_returns_outbox_messages(self):
        backend, mock_access = self._make_backend_with_inbox_and_folders(
            sent_raises=True, outbox_raises=False
        )
        result = backend.poll_inbox()

        outbound = [m for m in result if m.get("direction") == "outbound"]
        assert len(outbound) == 1
        assert outbound[0]["path"] == "/outbox/1"

    def test_sent_fails_outbox_succeeds_inbox_also_returned(self):
        backend, mock_access = self._make_backend_with_inbox_and_folders(
            sent_raises=True, outbox_raises=False
        )
        result = backend.poll_inbox()

        inbound = [m for m in result if m.get("direction") == "inbound"]
        assert len(inbound) == 1

    def test_both_fail_no_outbound_messages(self):
        backend, mock_access = self._make_backend_with_inbox_and_folders(
            sent_raises=True, outbox_raises=True
        )
        result = backend.poll_inbox()

        outbound = [m for m in result if m.get("direction") == "outbound"]
        assert outbound == []

    def test_both_fail_inbox_messages_still_returned(self):
        backend, mock_access = self._make_backend_with_inbox_and_folders(
            sent_raises=True, outbox_raises=True
        )
        result = backend.poll_inbox()

        inbound = [m for m in result if m.get("direction") == "inbound"]
        assert len(inbound) == 1

    def test_both_fail_logs_warning(self, caplog):
        import logging
        backend, mock_access = self._make_backend_with_inbox_and_folders(
            sent_raises=True, outbox_raises=True
        )

        with caplog.at_level(logging.WARNING, logger="tincand.backends.bluez_map"):
            backend.poll_inbox()

        assert any(
            "sent folder unavailable" in r.message or "outbox" in r.message
            for r in caplog.records
        )

    def test_sent_fails_outbox_succeeds_sent_raw_not_none(self):
        """sent_raw is set from outbox — the sent_raw=None path is not entered."""
        backend, mock_access = self._make_backend_with_inbox_and_folders(
            sent_raises=True, outbox_raises=False
        )
        result = backend.poll_inbox()

        # If the None path were entered, outbound would be empty
        outbound = [m for m in result if m.get("direction") == "outbound"]
        assert len(outbound) == 1
