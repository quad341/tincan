"""MapBackend — obexd MAP backend for tincand.

Connects to an iPhone via the OBEX Message Access Profile (MAP) using the
org.bluez.obex.Client1 D-Bus interface exposed by obexd.

iOS consent gate: the first CreateSession call on an unconsented device always
returns D-Bus error org.openobex.Error.Forbidden (OBEX 0x43).  That refusal IS
what prompts iOS to show the 'Show Notifications' toggle.  We surface a
ConsentRequired exception so the caller can display a retry prompt rather than
treating the first attempt as fatal.
"""
from __future__ import annotations

import logging

import dbus

from tincand.backends.base import BackendInterface

_log = logging.getLogger(__name__)

_OBEX_CLIENT = "org.bluez.obex"
_OBEX_CLIENT_IFACE = "org.bluez.obex.Client1"
_OBEX_CLIENT_PATH = "/org/bluez/obex"

_FORBIDDEN_ERRORS = {
    "org.openobex.Error.Forbidden",
    "org.bluez.obex.Error.Forbidden",
}


class ConsentRequired(Exception):
    """Raised when iOS has not yet granted MAP access (OBEX 0x43 Forbidden).

    The caller should prompt the user to enable 'Show Notifications' on the
    iPhone, then retry connect().
    """


class MapBackend(BackendInterface):
    """MAP backend using obexd org.bluez.obex.Client1."""

    def __init__(self) -> None:
        self._service: object | None = None
        self._session_path: str | None = None

    # ------------------------------------------------------------------
    # BackendInterface
    # ------------------------------------------------------------------

    def connect(self, device_addr: str) -> None:
        """Create an obexd MAP session to *device_addr*.

        Raises:
            ConsentRequired: when obexd returns OBEX 0x43 Forbidden (iOS
                consent not yet granted).
            dbus.exceptions.DBusException: for other D-Bus / obexd errors.
        """
        bus = dbus.SessionBus()
        client = dbus.Interface(
            bus.get_object(_OBEX_CLIENT, _OBEX_CLIENT_PATH),
            _OBEX_CLIENT_IFACE,
        )
        try:
            session_path = client.CreateSession(
                device_addr,
                {"Target": dbus.String("map")},
            )
        except dbus.exceptions.DBusException as exc:
            if exc.get_dbus_name() in _FORBIDDEN_ERRORS:
                _log.info(
                    "MAP CreateSession returned Forbidden for %s — consent needed",
                    device_addr,
                )
                raise ConsentRequired(
                    f"iOS has not granted MAP access for {device_addr}. "
                    "Enable 'Show Notifications' on the iPhone, then retry."
                ) from exc
            raise

        self._session_path = str(session_path)
        _log.info("MAP session established: %s → %s", device_addr, self._session_path)

        if self._service is not None:
            self._service.Connect(device_addr)  # type: ignore[attr-defined]

    def disconnect(self) -> None:
        """Remove the obexd MAP session; silently no-ops if not connected."""
        if self._session_path is None:
            return
        try:
            bus = dbus.SessionBus()
            client = dbus.Interface(
                bus.get_object(_OBEX_CLIENT, _OBEX_CLIENT_PATH),
                _OBEX_CLIENT_IFACE,
            )
            client.RemoveSession(self._session_path)
            _log.info("MAP session removed: %s", self._session_path)
        except dbus.exceptions.DBusException as exc:
            _log.warning("RemoveSession failed (already gone?): %s", exc)
        finally:
            self._session_path = None
            if self._service is not None:
                self._service.Disconnect()  # type: ignore[attr-defined]

    def poll_inbox(self) -> list:
        """Return new MAP messages — not yet implemented."""
        return []

    def get_message(self, handle: str) -> object:
        """Fetch a MAP message by handle — not yet implemented."""
        return None

    def send_message(self, to: str, body: str) -> str:
        """Send a message via MAP — not yet implemented."""
        raise NotImplementedError("MAP send_message not yet implemented")
