"""Qt-free synchronous D-Bus client for tincand MCP server (Phase 1).

Wraps the im.tincan.Daemon and im.tincan.Messages D-Bus interfaces, converts
dbus-python typed objects to plain Python, and maps D-Bus exceptions to
structured bridge exceptions.
"""
from __future__ import annotations

import dbus
import dbus.exceptions  # noqa: F401 (dbus.exceptions must be imported for the submodule)

# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class TincandNotRunning(Exception):
    """tincand D-Bus service is not available on the session bus."""


class TincandNotConnected(Exception):
    """tincand is running but not connected to a Bluetooth device."""


class TincandInvalidArgument(Exception):
    """A method argument was rejected by tincand."""


class TincandError(Exception):
    """Unclassified tincand D-Bus error."""

    def __init__(self, message: str, dbus_name: str) -> None:
        super().__init__(message)
        self.dbus_name = dbus_name


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _translate(exc: dbus.exceptions.DBusException) -> None:
    name = exc.get_dbus_name()
    msg = str(exc)
    if name in (
        "org.freedesktop.DBus.Error.ServiceUnknown",
        "org.freedesktop.DBus.Error.NoReply",
    ):
        raise TincandNotRunning("tincand is not running") from exc
    if name == "im.tincan.Error.NotConnected":
        raise TincandNotConnected("tincand is not connected to a device") from exc
    if name == "im.tincan.Error.InvalidArgument":
        raise TincandInvalidArgument(msg) from exc
    raise TincandError(msg, name) from exc


def _strip_dbus(obj):
    """Recursively convert dbus-python typed objects to plain Python types."""
    if isinstance(obj, dbus.Dictionary):
        return {_strip_dbus(k): _strip_dbus(v) for k, v in obj.items()}
    if isinstance(obj, (dbus.Array, list)):
        return [_strip_dbus(i) for i in obj]
    if isinstance(obj, dbus.Boolean):
        return bool(obj)
    if isinstance(obj, dbus.String):
        return str(obj)
    if isinstance(obj, (dbus.Int32, dbus.UInt32, dbus.Int64, dbus.UInt64)):
        return int(obj)
    return obj


# ---------------------------------------------------------------------------
# Bridge class
# ---------------------------------------------------------------------------


class TincandDBusBridge:
    """Synchronous thin wrapper over the tincand D-Bus service.

    Each public method opens a fresh session bus connection, makes one
    synchronous call, strips dbus-python types, and returns plain Python.
    """

    BUS_NAME = "im.tincan.Daemon"
    OBJECT = "/im/tincan"
    IFACE_DAEMON = "im.tincan.Daemon"
    IFACE_MESSAGES = "im.tincan.Messages"

    def _bus(self) -> dbus.SessionBus:
        return dbus.SessionBus()

    def _obj(self) -> dbus.proxies.ProxyObject:
        return self._bus().get_object(self.BUS_NAME, self.OBJECT)

    def _iface(self, name: str) -> dbus.Interface:
        return dbus.Interface(self._obj(), dbus_interface=name)

    # ------------------------------------------------------------------
    # Daemon interface
    # ------------------------------------------------------------------

    def get_status(self) -> dict:
        """Return tincand status dict with connected, device_address, etc."""
        try:
            raw = self._iface(self.IFACE_DAEMON).GetStatus()
            return _strip_dbus(raw)
        except dbus.exceptions.DBusException as e:
            _translate(e)

    def get_contacts(self) -> list[dict]:
        """Return [{phone, name}] for all known contacts."""
        try:
            raw = self._iface(self.IFACE_DAEMON).GetContacts()
            return _strip_dbus(raw)
        except dbus.exceptions.DBusException as e:
            _translate(e)

    def get_notification_filter(self) -> dict:
        """Return {enabled, apps: {app_id: action}}."""
        try:
            raw = self._iface(self.IFACE_DAEMON).GetNotificationFilter()
            return _strip_dbus(raw)
        except dbus.exceptions.DBusException as e:
            _translate(e)

    def set_notifications_enabled(self, enabled: bool) -> None:
        """Enable or disable ANCS notification mirroring globally."""
        try:
            self._iface(self.IFACE_DAEMON).SetNotificationsEnabled(enabled)
        except dbus.exceptions.DBusException as e:
            _translate(e)

    def set_app_filter(self, app_id: str, action: str) -> None:
        """Set allow/deny for *app_id*. Raises TincandInvalidArgument on bad action."""
        try:
            self._iface(self.IFACE_DAEMON).SetAppFilter(app_id, action)
        except dbus.exceptions.DBusException as e:
            _translate(e)

    def get_seen_apps(self) -> list[dict]:
        """Return [{app_id, label_hint}] for all apps that have sent notifications."""
        try:
            raw = self._iface(self.IFACE_DAEMON).GetSeenApps()
            return _strip_dbus(raw)
        except dbus.exceptions.DBusException as e:
            _translate(e)

    # ------------------------------------------------------------------
    # Messages interface
    # ------------------------------------------------------------------

    def list_conversations(self) -> list[dict]:
        """Return conversation summary list."""
        try:
            raw = self._iface(self.IFACE_MESSAGES).ListConversations()
            return _strip_dbus(raw)
        except dbus.exceptions.DBusException as e:
            _translate(e)

    def get_messages(self, conv_id: str) -> list[dict]:
        """Return messages for *conv_id* in chronological order."""
        try:
            raw = self._iface(self.IFACE_MESSAGES).GetMessages(conv_id)
            return _strip_dbus(raw)
        except dbus.exceptions.DBusException as e:
            _translate(e)

    def send_message(self, to: str, body: str) -> str:
        """Send *body* to *to* (phone number). Returns message_id."""
        try:
            raw = self._iface(self.IFACE_MESSAGES).SendMessage(to, body)
            return _strip_dbus(raw)
        except dbus.exceptions.DBusException as e:
            _translate(e)

    def send_group_message(self, recipients: list[str], body: str) -> str:
        """Send *body* to all *recipients*. Returns conversation_id."""
        try:
            raw = self._iface(self.IFACE_MESSAGES).SendMessageToRecipients(recipients, body)
            return _strip_dbus(raw)
        except dbus.exceptions.DBusException as e:
            _translate(e)

    def mark_conversation_read(self, conv_id: str) -> None:
        """Mark all messages in *conv_id* as read."""
        try:
            self._iface(self.IFACE_MESSAGES).MarkConversationRead(conv_id)
        except dbus.exceptions.DBusException as e:
            _translate(e)
