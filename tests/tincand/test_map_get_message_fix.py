"""Behavior tests: MAP body retrieval via Message1.Get() (tincan-572zo).

BlueZ 5.66+ removed GetMessage from MessageAccess1.  The correct path is
org.bluez.obex.Message1.Get(targetfile, attachment) on each message's own
D-Bus object, not MessageAccess1.GetMessage(handle, targetfile, options).

Coverage:
  - _fetch_raw_bmsg calls Message1.Get("", False) — not GetMessage
  - _fetch_raw_bmsg does NOT call MessageAccess1.GetMessage at all
  - The message's D-Bus object is fetched by path (not by handle extraction)
  - Failed Get() is cached in _failed_handles — same backoff as before
  - poll_inbox falls back to Subject field when Message1.Get() fails
  - Multiple polls don't retry a cached-failed handle
"""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import dbus
import dbus.exceptions
import pytest

from tincand.backends.bluez_map import MapBackend


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_OBEX_CLIENT = "org.bluez.obex"
_MSG_PATH = "/org/bluez/obex/client/session1/message676711970505987269"


def _make_backend_with_mock_access():
    backend = MapBackend()
    mock_access = MagicMock(name="MessageAccess1")
    backend._msg_access = mock_access
    return backend, mock_access


def _dbus_unknown_method():
    """Simulate the live error: GetMessage with signature ssa{sv} doesn't exist."""
    return dbus.exceptions.DBusException(
        name="org.freedesktop.DBus.Error.UnknownMethod"
    )


# ---------------------------------------------------------------------------
# §1 _fetch_raw_bmsg — calls Message1.Get(), NOT GetMessage (tincan-572zo)
# ---------------------------------------------------------------------------

class TestFetchRawBmsgUsesMessage1Get:
    """_fetch_raw_bmsg must use org.bluez.obex.Message1.Get(), not GetMessage."""

    @pytest.fixture()
    def _patched(self):
        """Yield (backend, mock_access, mock_msg1) with dbus.Interface mocked.

        mock_access.GetMessage is configured to return a valid (path, {}) tuple
        so the OLD code doesn't crash on unpacking — tests must fail on assertions
        not on ValueError.
        """
        backend, mock_access = _make_backend_with_mock_access()
        mock_access.GetMessage.return_value = ("/old/transfer", {})
        mock_msg1 = MagicMock(name="Message1")
        mock_msg1.Get.return_value = ("/transfer/1", {})
        with patch("tincand.backends.bluez_map.dbus.SessionBus") as mock_bus_cls, \
             patch("tincand.backends.bluez_map.dbus.Interface", return_value=mock_msg1), \
             patch.object(backend, "_wait_transfer_recv_raw", return_value=None):
            mock_bus_cls.return_value.get_object.return_value = MagicMock()
            yield backend, mock_access, mock_msg1

    def test_message1_get_is_called(self, _patched):
        backend, _access, mock_msg1 = _patched
        backend._fetch_raw_bmsg(_MSG_PATH)
        assert mock_msg1.Get.called, "Message1.Get() must be called to fetch body"

    def test_message1_get_called_with_empty_targetfile(self, _patched):
        backend, _access, mock_msg1 = _patched
        backend._fetch_raw_bmsg(_MSG_PATH)
        assert mock_msg1.Get.called, "Message1.Get() must have been called"
        args = mock_msg1.Get.call_args
        assert args[0][0] == "", "targetfile must be empty string (obexd picks path)"

    def test_message1_get_called_with_attachment_false(self, _patched):
        backend, _access, mock_msg1 = _patched
        backend._fetch_raw_bmsg(_MSG_PATH)
        assert mock_msg1.Get.called, "Message1.Get() must have been called"
        args = mock_msg1.Get.call_args
        assert bool(args[0][1]) is False, "attachment flag must be False"

    def test_get_message_on_msg_access_not_called(self, _patched):
        backend, mock_access, _msg1 = _patched
        backend._fetch_raw_bmsg(_MSG_PATH)
        mock_access.GetMessage.assert_not_called()

    def test_message_object_fetched_by_path(self):
        """dbus.SessionBus().get_object must be called with the full msg_path."""
        backend, mock_access = _make_backend_with_mock_access()
        mock_access.GetMessage.return_value = ("/old/transfer", {})
        mock_msg1 = MagicMock(name="Message1")
        mock_msg1.Get.return_value = ("/transfer/1", {})
        mock_bus = MagicMock(name="bus")
        mock_bus.get_object.return_value = MagicMock()
        with patch("tincand.backends.bluez_map.dbus.SessionBus", return_value=mock_bus), \
             patch("tincand.backends.bluez_map.dbus.Interface", return_value=mock_msg1), \
             patch.object(backend, "_wait_transfer_recv_raw", return_value=None):
            backend._fetch_raw_bmsg(_MSG_PATH)
        mock_bus.get_object.assert_called_once_with(_OBEX_CLIENT, _MSG_PATH)


# ---------------------------------------------------------------------------
# §2 _failed_handles backoff — Message1.Get failure caches the handle
# ---------------------------------------------------------------------------

class TestMessage1GetBackoffCache:
    """When Message1.Get raises DBusException, handle is cached; no retry on subsequent polls."""

    def _make_backend_with_failing_get(self, handle=_MSG_PATH):
        """Backend whose Message1.Get raises UnknownMethod; Properties mock is separate."""
        backend, mock_access = _make_backend_with_mock_access()
        mock_access.GetMessage.return_value = ("/old/transfer", {})
        mock_access.ListMessages.return_value = {
            handle: {
                "Sender": "Alice", "Datetime": "20260605T100000",
                "Read": False, "Subject": "Subject body",
            }
        }
        mock_msg1 = MagicMock(name="Message1")
        mock_msg1.Get.side_effect = _dbus_unknown_method()
        mock_props = MagicMock(name="Properties")
        mock_props.Get.return_value = "error"  # transfer polling returns "error"

        def _iface_factory(obj, iface_name):
            if iface_name == "org.bluez.obex.Message1":
                return mock_msg1
            return mock_props  # Properties interface for transfer polling

        return backend, mock_msg1, _iface_factory

    def test_message1_get_called_exactly_once_across_two_polls(self):
        """After a failed Get, handle is cached — no second Get on re-poll."""
        backend, mock_msg1, iface_factory = self._make_backend_with_failing_get()
        with patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface", side_effect=iface_factory):
            backend.poll_inbox()
            backend.poll_inbox()
        assert mock_msg1.Get.call_count == 1

    def test_message1_get_called_once_across_five_polls(self):
        backend, mock_msg1, iface_factory = self._make_backend_with_failing_get()
        with patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface", side_effect=iface_factory):
            for _ in range(5):
                backend.poll_inbox()
        assert mock_msg1.Get.call_count == 1

    def test_subject_used_as_fallback_when_message1_get_fails(self):
        backend, mock_msg1, iface_factory = self._make_backend_with_failing_get()
        with patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface", side_effect=iface_factory):
            result = backend.poll_inbox()
        assert result[0]["body"] == "Subject body"

    def test_subject_fallback_on_second_poll_when_handle_cached(self):
        backend, mock_msg1, iface_factory = self._make_backend_with_failing_get()
        with patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface", side_effect=iface_factory):
            backend.poll_inbox()
            result = backend.poll_inbox()
        assert result[0]["body"] == "Subject body"


# ---------------------------------------------------------------------------
# §3 End-to-end: real BlueZ 5.66+ scenario — GetMessage=UnknownMethod (tincan-taa2x)
# ---------------------------------------------------------------------------

_TRANSFER_PATH = "/org/bluez/obex/client/session1/transfer42"

_INBOX_PROPS = {
    "Sender": "Alice",
    "SenderAddressing": "+12025551234",
    "Datetime": "20260605T100000",
    "Read": False,
    "Subject": "Subject fallback",
}

_SINGLE_BMSG = "BEGIN:MSG\r\nHello from live device\r\nEND:MSG\r\n"
_MULTI_BMSG = (
    "BEGIN:MSG\r\n"
    "Segment one of long SMS\r\n"
    "END:MSG\r\n"
    "BEGIN:MSG\r\n"
    "segment two continues here\r\n"
    "END:MSG\r\n"
)


class TestBlueZ566ForcedMessage1GetPath:
    """End-to-end: GetMessage=UnknownMethod (real BlueZ 5.66+), Message1.Get is the only path.

    Emulates real hardware per tincan-taa2x: MessageAccess1 does NOT expose
    GetMessage.  The daemon must route through Message1.Get and extract body —
    including multipart SMS with multiple BEGIN:MSG segments.
    """

    @pytest.fixture()
    def _success(self):
        backend = MapBackend()
        mock_access = MagicMock(name="MessageAccess1")
        mock_access.GetMessage.side_effect = _dbus_unknown_method()
        mock_access.ListMessages.side_effect = (
            lambda folder, opts={}: {_MSG_PATH: dict(_INBOX_PROPS)} if folder == "inbox" else {}
        )
        backend._msg_access = mock_access
        mock_msg1 = MagicMock(name="Message1")
        mock_msg1.Get.return_value = (_TRANSFER_PATH, {})
        yield backend, mock_access, mock_msg1

    def test_singlepart_body_retrieved(self, _success):
        backend, _, mock_msg1 = _success
        with patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface", return_value=mock_msg1), \
             patch.object(backend, "_wait_transfer_recv_raw", return_value=_SINGLE_BMSG):
            result = backend.poll_inbox()
        assert result, "poll_inbox must return at least one message"
        assert result[0]["body"] == "Hello from live device"

    def test_multipart_segments_joined(self, _success):
        """Two BEGIN:MSG segments must be concatenated into one body string."""
        backend, _, mock_msg1 = _success
        with patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface", return_value=mock_msg1), \
             patch.object(backend, "_wait_transfer_recv_raw", return_value=_MULTI_BMSG):
            result = backend.poll_inbox()
        assert result, "poll_inbox must return at least one message"
        body = result[0]["body"]
        assert "Segment one" in body
        assert "segment two" in body

    def test_get_message_not_called_on_bluez566(self, _success):
        """GetMessage must never be invoked when it raises UnknownMethod."""
        backend, mock_access, mock_msg1 = _success
        with patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface", return_value=mock_msg1), \
             patch.object(backend, "_wait_transfer_recv_raw", return_value=_SINGLE_BMSG):
            backend.poll_inbox()
        mock_access.GetMessage.assert_not_called()

    def test_failed_handles_not_polluted_on_success(self, _success):
        """Handle must NOT appear in _failed_handles after a successful Get."""
        backend, _, mock_msg1 = _success
        with patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface", return_value=mock_msg1), \
             patch.object(backend, "_wait_transfer_recv_raw", return_value=_SINGLE_BMSG):
            backend.poll_inbox()
        assert _MSG_PATH not in backend._failed_handles


# ---------------------------------------------------------------------------
# §4 _failed_handles doesn't block retrieval (tincan-taa2x)
# ---------------------------------------------------------------------------

class TestFailedHandlesDoesNotBlockRetrieval:
    """_failed_handles must not permanently prevent body retrieval.

    A transient Get failure caches the handle; connect() clears the cache so
    the next poll can succeed — 'check _failed_handles doesn't block it'.
    """

    def test_pre_populated_failed_handle_skips_get(self):
        """Handle in _failed_handles must short-circuit _fetch_raw_bmsg to None."""
        backend, _ = _make_backend_with_mock_access()
        backend._failed_handles.add(_MSG_PATH)
        mock_msg1 = MagicMock(name="Message1")
        with patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface", return_value=mock_msg1):
            result = backend._fetch_raw_bmsg(_MSG_PATH)
        assert result is None
        mock_msg1.Get.assert_not_called()

    def test_cleared_failed_handles_allows_successful_get(self):
        """After _failed_handles.clear() (connect()), body is retrieved normally."""
        backend, _ = _make_backend_with_mock_access()
        backend._failed_handles.add(_MSG_PATH)
        backend._failed_handles.clear()
        mock_msg1 = MagicMock(name="Message1")
        mock_msg1.Get.return_value = (_TRANSFER_PATH, {})
        bmsg = "BEGIN:MSG\r\nPost-reconnect body\r\nEND:MSG\r\n"
        with patch("tincand.backends.bluez_map.dbus.SessionBus"), \
             patch("tincand.backends.bluez_map.dbus.Interface", return_value=mock_msg1), \
             patch.object(backend, "_wait_transfer_recv_raw", return_value=bmsg):
            result = backend._fetch_raw_bmsg(_MSG_PATH)
        assert result == bmsg
        mock_msg1.Get.assert_called_once()
