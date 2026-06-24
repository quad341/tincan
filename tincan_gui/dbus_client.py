"""TincandClient — PySide6.QtDBus subscriber for tincand D-Bus signals.

Bus name: im.tincan.Daemon  Object: /im/tincan
Gracefully no-ops when the daemon is not running; signals fire when it starts.
"""
from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtDBus import (
    QDBusArgument,
    QDBusConnection,
    QDBusInterface,
    QDBusMessage,
    QDBusPendingCallWatcher,
    QDBusReply,
)

from tincan_gui import trace as _trace

try:
    import dbus as _dbus
    _HAVE_DBUS = True
except ImportError:
    _HAVE_DBUS = False

_log = logging.getLogger(__name__)

_BUS_NAME = "im.tincan.Daemon"
_OBJECT = "/im/tincan"
_IFACE_DAEMON = "im.tincan.Daemon"
_IFACE_MESSAGES = "im.tincan.Messages"
# TODO(tincan-xohrx): confirm exact interface name with architect
_IFACE_CALLS = "im.tincan.Calls"


# ---------------------------------------------------------------------------
# QDBusArgument demarshalling helpers
# ---------------------------------------------------------------------------

def _read_dbus_value(arg: QDBusArgument):
    """Read the current value from a QDBusArgument, recursing for complex types.

    PySide6's asVariant() returns VoidPtr/None for nested complex types such as
    a{sb} inside an a{sv} variant slot.  Each ElementType case is handled
    explicitly so we never call asVariant() on MapType or ArrayType positions.
    """
    t = arg.currentType()
    if t == QDBusArgument.ElementType.MapType:
        inner: dict = {}
        try:
            arg.beginMap()
            while not arg.atEnd():
                arg.beginMapEntry()
                k = arg.asVariant()
                v = _read_dbus_value(arg)
                arg.endMapEntry()
                if k is not None:
                    inner[str(k)] = v
            arg.endMap()
        except Exception as exc:
            _log.debug("_read_dbus_value[Map] error: %s", exc)
        return inner
    if t == QDBusArgument.ElementType.ArrayType:
        items: list = []
        try:
            arg.beginArray()
            while not arg.atEnd():
                items.append(_read_dbus_value(arg))
            arg.endArray()
        except Exception as exc:
            _log.debug("_read_dbus_value[Array] error: %s", exc)
        return items
    if t == QDBusArgument.ElementType.VariantType:
        # VariantType: asVariant() dereferences the 'v' wrapper.  For types Qt
        # knows (bool, str, int) it returns a Python native.  For unregistered
        # compound types (e.g. a{sb}) it returns a QDBusArgument already
        # positioned at the inner data — recurse in that case.  Treat None /
        # VoidPtr as an empty dict (best-effort) without corrupting the cursor.
        try:
            v = arg.asVariant()
        except Exception:
            return {}
        if isinstance(v, QDBusArgument):
            return _read_dbus_value(v)
        return v if v is not None else {}
    # BasicType or unknown: asVariant() returns a Python native or QDBusArgument.
    try:
        v = arg.asVariant()
    except Exception:
        return None
    if isinstance(v, QDBusArgument):
        return _read_dbus_value(v)
    return v


def _demarshal_map(value) -> dict:
    """Demarshal a{sv} into a Python dict.

    Accepts a QDBusArgument (navigated directly), a plain dict (returned as-is,
    with QDBusArgument values recursed), or any other type (returns {}).
    """
    if isinstance(value, dict):
        # PySide6 may auto-convert a{sv} → dict but leave nested complex types
        # (e.g. a{sb}) as QDBusArgument values — recurse on those.
        result = {}
        for k, v in value.items():
            if isinstance(v, QDBusArgument):
                result[str(k)] = _read_dbus_value(v)
            else:
                result[str(k)] = v
        return result
    if not isinstance(value, QDBusArgument):
        return {}
    result: dict = {}
    try:
        value.beginMap()
        while not value.atEnd():
            value.beginMapEntry()
            k = value.asVariant()
            v = _read_dbus_value(value)
            value.endMapEntry()
            if k is not None:
                result[str(k)] = v
        value.endMap()
    except Exception as exc:
        _log.debug("_demarshal_map error: %s", exc)
    return result


def _demarshal_list_of_maps(value) -> list[dict]:
    """Demarshal aa{sv} into a list of dicts.

    Accepts a QDBusArgument, a plain list (items recursed), or any other type.
    """
    if isinstance(value, list):
        return [_demarshal_map(item) for item in value]
    if not isinstance(value, QDBusArgument):
        return []
    result: list[dict] = []
    try:
        value.beginArray()
        while not value.atEnd():
            result.append(_demarshal_map(value))
        value.endArray()
    except Exception as exc:
        _log.debug("_demarshal_list_of_maps error: %s", exc)
    return result


def _wrap_reply(msg):
    """Wrap a QDBusMessage in QDBusReply; pass through non-QDBusMessage values.

    iface.call() returns QDBusMessage in production but tests may inject mocks
    that already behave like QDBusReply (have .isValid() / .value()).  Only wrap
    when we actually have a QDBusMessage so we don't break mock-based tests.
    """
    if isinstance(msg, QDBusMessage):
        return QDBusReply(msg)
    return msg


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class TincandClient(QObject):
    """D-Bus client for tincand.  Emits Qt signals when daemon signals arrive."""

    # Daemon interface
    connected = Signal(str)           # device_address
    disconnected = Signal()
    capability_changed = Signal(str, bool)  # feature, available
    app_notification_received = Signal(dict)  # AppNotificationReceived a{sv} → dict

    # Messages interface
    message_received = Signal(dict)        # message a{sv} → dict
    message_sent = Signal(str)             # message_id
    conversation_updated = Signal(dict)    # conversation a{sv} → dict
    contact_photo_received = Signal(str, bytes)  # (conv_id, photo_bytes)

    # Async send outcome signals (to, body, message_id) / (to, body)
    message_send_accepted = Signal(str, str, str)
    message_send_failed = Signal(str, str)

    # Calls interface (HFP) — signals from im.tincan.Calls (tincan-xohrx pending)
    call_incoming = Signal(str, str)   # (caller_name, caller_number)
    call_connected = Signal()
    call_ended = Signal()
    audio_error = Signal(str)          # reason
    audio_restored = Signal()
    call_active = Signal(str, str)     # (call_id, number)
    call_held = Signal(str, str)       # (call_id, number)
    call_waiting = Signal(str, str, str)  # (call_id, number, name)
    call_removed = Signal(str)         # call_id

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._bus = QDBusConnection.sessionBus()
        if not self._bus.isConnected():
            _log.warning("tincan D-Bus: cannot connect to session bus — signals disabled")
            return
        self._subscribe()

    # ------------------------------------------------------------------
    # Signal subscription (daemon → Qt)
    # ------------------------------------------------------------------

    def _subscribe(self) -> None:
        b = self._bus
        _ok = [
            b.connect(_BUS_NAME, _OBJECT, _IFACE_DAEMON, "Connected",
                      self, "1_on_connected(QString)"),
            b.connect(_BUS_NAME, _OBJECT, _IFACE_DAEMON, "Disconnected",
                      self, "1_on_disconnected()"),
            b.connect(_BUS_NAME, _OBJECT, _IFACE_DAEMON, "CapabilityChanged",
                      self, "1_on_capability_changed(QString,bool)"),
            b.connect(_BUS_NAME, _OBJECT, _IFACE_DAEMON, "AppNotificationReceived",
                      self, "1_on_app_notification_received(QVariantMap)"),
            b.connect(_BUS_NAME, _OBJECT, _IFACE_MESSAGES, "MessageReceived",
                      self, "1_on_message_received(QVariantMap)"),
            b.connect(_BUS_NAME, _OBJECT, _IFACE_MESSAGES, "MessageSent",
                      self, "1_on_message_sent(QString)"),
            b.connect(_BUS_NAME, _OBJECT, _IFACE_MESSAGES, "ConversationUpdated",
                      self, "1_on_conversation_updated(QVariantMap)"),
            b.connect(_BUS_NAME, _OBJECT, _IFACE_MESSAGES, "ContactPhotoReceived",
                      self, "1_on_contact_photo_received(QString,QByteArray)"),
            # HFP call signals — interface subject to confirmation (tincan-xohrx)
            b.connect(_BUS_NAME, _OBJECT, _IFACE_CALLS, "IncomingCall",
                      self, "1_on_call_incoming(QString,QString)"),
            b.connect(_BUS_NAME, _OBJECT, _IFACE_CALLS, "CallConnected",
                      self, "1_on_call_connected()"),
            b.connect(_BUS_NAME, _OBJECT, _IFACE_CALLS, "CallEnded",
                      self, "1_on_call_ended()"),
            b.connect(_BUS_NAME, _OBJECT, _IFACE_CALLS, "AudioError",
                      self, "1_on_audio_error(QString)"),
            b.connect(_BUS_NAME, _OBJECT, _IFACE_CALLS, "AudioRestored",
                      self, "1_on_audio_restored()"),
            b.connect(_BUS_NAME, _OBJECT, _IFACE_CALLS, "CallActive",
                      self, "1_on_call_active(QString,QString)"),
            b.connect(_BUS_NAME, _OBJECT, _IFACE_CALLS, "CallHeld",
                      self, "1_on_call_held(QString,QString)"),
            b.connect(_BUS_NAME, _OBJECT, _IFACE_CALLS, "CallWaiting",
                      self, "1_on_call_waiting(QString,QString,QString)"),
            b.connect(_BUS_NAME, _OBJECT, _IFACE_CALLS, "CallRemoved",
                      self, "1_on_call_removed(QString)"),
        ]
        if not all(_ok):
            _log.warning("tincan D-Bus: some signal subscriptions failed: %s", _ok)
        else:
            _log.debug("tincan D-Bus: all 17 signal subscriptions registered")

    # ------------------------------------------------------------------
    # D-Bus signal → Qt signal bridges
    # ------------------------------------------------------------------

    @Slot(str)
    def _on_connected(self, device_address: str) -> None:
        _log.debug("tincand: Connected(%s)", device_address)
        self.connected.emit(str(device_address))

    @Slot()
    def _on_disconnected(self) -> None:
        _log.debug("tincand: Disconnected")
        self.disconnected.emit()

    @Slot(str, bool)
    def _on_capability_changed(self, feature: str, available: bool) -> None:
        _log.debug("tincand: CapabilityChanged(%s, %s)", feature, available)
        self.capability_changed.emit(str(feature), bool(available))

    @Slot("QVariantMap")
    def _on_app_notification_received(self, payload) -> None:
        _log.debug("tincand: AppNotificationReceived")
        self.app_notification_received.emit(_demarshal_map(payload))

    @Slot("QVariantMap")
    def _on_message_received(self, message) -> None:
        _log.debug("tincand: MessageReceived")
        self.message_received.emit(_demarshal_map(message))

    @Slot(str)
    def _on_message_sent(self, message_id: str) -> None:
        _log.debug("tincand: MessageSent(%s)", message_id)
        self.message_sent.emit(str(message_id))

    @Slot("QVariantMap")
    def _on_conversation_updated(self, conversation) -> None:
        _log.debug("tincand: ConversationUpdated")
        self.conversation_updated.emit(_demarshal_map(conversation))

    # ------------------------------------------------------------------
    # Daemon method calls (Qt → daemon)
    # ------------------------------------------------------------------

    def _dbus_call(self, iface_name: str, method: str, *args):
        """Call a tincand method via dbus-python; returns raw dbus result or None.

        dbus-python returns properly-typed Python objects (dbus.Dictionary,
        dbus.Array, etc.) without QDBusArgument navigation, avoiding the COW
        read-only cursor bug seen in PySide6 6.11.1 on QDBusArgument.beginMapEntry().
        Returns None when dbus-python is unavailable, the daemon is absent, or
        the call fails for any reason.
        """
        if not _HAVE_DBUS:
            return None
        try:
            bus = _dbus.SessionBus()
            obj = bus.get_object(_BUS_NAME, _OBJECT)
            iface = _dbus.Interface(obj, iface_name)
            return getattr(iface, method)(*args)
        except Exception as exc:
            _log.debug("%s.%s via dbus-python failed: %s", iface_name, method, exc)
            return None

    def get_status(self) -> dict:
        """Call GetStatus.  Returns {} when daemon is absent.

        Always includes adapter_path_requested ('' if no mismatch or daemon absent).
        """
        if not self._bus.isConnected():
            return {}
        result = self._dbus_call(_IFACE_DAEMON, "GetStatus")
        if result is not None:
            d = {str(k): v for k, v in result.items()} if hasattr(result, "items") else {}
            d.setdefault("adapter_path_requested", "")
            return d
        # Qt fallback: used when dbus-python is unavailable (unit tests with mocks).
        iface = QDBusInterface(_BUS_NAME, _OBJECT, _IFACE_DAEMON, self._bus)
        if not iface.isValid():
            return {}
        raw = iface.call("GetStatus")
        if isinstance(raw, QDBusMessage):
            if raw.type() == QDBusMessage.MessageType.ErrorMessage:
                _log.debug("GetStatus failed: %s", raw.errorMessage())
                return {}
            args = raw.arguments()
            d = _demarshal_map(args[0] if args else {})
            d.setdefault("adapter_path_requested", "")
            return d
        reply = _wrap_reply(raw)
        if not reply.isValid():
            _log.debug("GetStatus failed: %s", reply.error().message())
            return {}
        d = _demarshal_map(reply.value())
        d.setdefault("adapter_path_requested", "")
        return d

    def get_adapters(self) -> list[dict]:
        """Call GetAdapters. Returns [] when daemon is absent or BlueZ unavailable.

        Each dict: path, alias, address, powered(bool),
        hfp_sco_capable('yes'/'no'/'unknown'), le_capable(bool), is_selected(bool).
        No dbus.SystemBus() import — all BlueZ queries go via the daemon.
        """
        if not self._bus.isConnected():
            return []
        result = self._dbus_call(_IFACE_DAEMON, "GetAdapters")
        if result is not None:
            return [
                {str(k): v for k, v in a.items()}
                for a in result
                if hasattr(a, "items")
            ]
        # Qt fallback
        iface = QDBusInterface(_BUS_NAME, _OBJECT, _IFACE_DAEMON, self._bus)
        if not iface.isValid():
            return []
        raw = iface.call("GetAdapters")
        if isinstance(raw, QDBusMessage):
            if raw.type() == QDBusMessage.MessageType.ErrorMessage:
                _log.debug("GetAdapters failed: %s", raw.errorMessage())
                return []
            args = raw.arguments()
            return _demarshal_list_of_maps(args[0] if args else [])
        reply = _wrap_reply(raw)
        if not reply.isValid():
            _log.debug("GetAdapters failed: %s", reply.error().message())
            return []
        return _demarshal_list_of_maps(reply.value())

    def list_conversations(self) -> list[dict]:
        """Call ListConversations.  Returns [] when daemon is absent.

        Each dict includes is_group (bool) and group_name (str, equals
        display_name for group conversations).
        """
        if not self._bus.isConnected():
            return []
        result = self._dbus_call(_IFACE_MESSAGES, "ListConversations")
        if result is not None:
            return [
                {str(k): v for k, v in conv.items()}
                for conv in result
                if hasattr(conv, "items")
            ]
        # Qt fallback: used when dbus-python is unavailable (unit tests with mocks).
        iface = QDBusInterface(_BUS_NAME, _OBJECT, _IFACE_MESSAGES, self._bus)
        if not iface.isValid():
            return []
        raw = iface.call("ListConversations")
        if isinstance(raw, QDBusMessage):
            if raw.type() == QDBusMessage.MessageType.ErrorMessage:
                _log.debug("ListConversations failed: %s", raw.errorMessage())
                return []
            args = raw.arguments()
            return _demarshal_list_of_maps(args[0] if args else [])
        reply = _wrap_reply(raw)
        if not reply.isValid():
            _log.debug("ListConversations failed: %s", reply.error().message())
            return []
        raw = _demarshal_list_of_maps(reply.value())
        result = []
        for d in raw:
            is_group = bool(d.get("is_group", False))
            d["is_group"] = is_group
            d["group_name"] = str(d.get("display_name", "")) if is_group else ""
            result.append(d)
        return result

    def send_message_to_recipients(self, recipients: list[str], body: str) -> str:
        """Call SendMessageToRecipients.  Returns conv_id or '' on error."""
        if not self._bus.isConnected():
            _log.warning("send_message_to_recipients: no D-Bus session bus")
            return ""
        iface = QDBusInterface(_BUS_NAME, _OBJECT, _IFACE_MESSAGES, self._bus)
        if not iface.isValid():
            _log.warning("send_message_to_recipients: tincand not running")
            return ""
        reply = _wrap_reply(iface.call("SendMessageToRecipients", recipients, body))
        if not reply.isValid():
            _log.warning("SendMessageToRecipients failed: %s", reply.error().message())
            return ""
        return str(reply.value() or "")

    def get_conversation_participants(self, conv_id: str) -> list[str]:
        """Call GetConversationParticipants.  Returns [] on error."""
        if not self._bus.isConnected():
            return []
        iface = QDBusInterface(_BUS_NAME, _OBJECT, _IFACE_MESSAGES, self._bus)
        if not iface.isValid():
            return []
        reply = _wrap_reply(iface.call("GetConversationParticipants", conv_id))
        if not reply.isValid():
            _log.debug(
                "GetConversationParticipants failed: %s", reply.error().message()
            )
            return []
        value = reply.value()
        if isinstance(value, list):
            return [str(v) for v in value]
        return []

    def get_messages(self, conv_id: str) -> list[dict]:
        """Call GetMessages(conv_id).  Returns [] when daemon is absent."""
        if not self._bus.isConnected():
            return []
        result = self._dbus_call(_IFACE_MESSAGES, "GetMessages", str(conv_id))
        if result is not None:
            msgs = [
                {str(k): v for k, v in msg.items()}
                for msg in result
                if hasattr(msg, "items")
            ]
            _trace.emit("dbus_in", method="GetMessages", conv_id=conv_id, count=len(msgs))
            return msgs
        iface = QDBusInterface(_BUS_NAME, _OBJECT, _IFACE_MESSAGES, self._bus)
        if not iface.isValid():
            return []
        raw = iface.call("GetMessages", str(conv_id))
        if isinstance(raw, QDBusMessage):
            if raw.type() == QDBusMessage.MessageType.ErrorMessage:
                _log.debug("GetMessages failed: %s", raw.errorMessage())
                return []
            args = raw.arguments()
            msgs = _demarshal_list_of_maps(args[0] if args else [])
            _trace.emit("dbus_in", method="GetMessages", conv_id=conv_id, count=len(msgs))
            return msgs
        reply = _wrap_reply(raw)
        if not reply.isValid():
            _log.debug("GetMessages failed: %s", reply.error().message())
            return []
        msgs = _demarshal_list_of_maps(reply.value())
        _trace.emit("dbus_in", method="GetMessages", conv_id=conv_id, count=len(msgs))
        return msgs

    def send_message(self, to: str, body: str) -> str:
        """Call SendMessage.  Returns the new message_id or '' on error."""
        if not self._bus.isConnected():
            _log.warning("send_message: no D-Bus session bus")
            return ""
        iface = QDBusInterface(_BUS_NAME, _OBJECT, _IFACE_MESSAGES, self._bus)
        if not iface.isValid():
            _log.warning("send_message: tincand not running")
            return ""
        reply = _wrap_reply(iface.call("SendMessage", to, body))
        if not reply.isValid():
            _log.warning("SendMessage failed: %s", reply.error().message())
            return ""
        return str(reply.value() or "")

    def send_message_async(self, to: str, body: str) -> None:
        """Call SendMessage asynchronously; emits message_send_accepted or message_send_failed."""
        _trace.emit("dbus_out", method="SendMessage", to=to,
                    body_hash=_trace.body_hash(body), body_len=len(body))
        if not self._bus.isConnected():
            _log.warning("send_message_async: no D-Bus session bus")
            self.message_send_failed.emit(to, body)
            return
        iface = QDBusInterface(_BUS_NAME, _OBJECT, _IFACE_MESSAGES, self._bus)
        if not iface.isValid():
            _log.warning("send_message_async: tincand not running")
            self.message_send_failed.emit(to, body)
            return
        pending = iface.asyncCallWithArgumentList("SendMessage", [to, body])
        watcher = QDBusPendingCallWatcher(pending, self)
        watcher.finished.connect(lambda w: self._on_send_message_reply(w, to, body))

    def _on_send_message_reply(
        self, watcher: QDBusPendingCallWatcher, to: str, body: str
    ) -> None:
        reply = QDBusReply(watcher.reply())
        if reply.isValid():
            self.message_send_accepted.emit(to, body, str(reply.value() or ""))
        else:
            _log.warning("SendMessage async failed: %s", reply.error().message())
            self.message_send_failed.emit(to, body)
        watcher.deleteLater()

    def request_reconnect(self) -> None:
        """Call RequestReconnect on the daemon (fire-and-forget)."""
        if not self._bus.isConnected():
            return
        iface = QDBusInterface(_BUS_NAME, _OBJECT, _IFACE_DAEMON, self._bus)
        if iface.isValid():
            iface.call("RequestReconnect")

    def request_ancs_heal(self) -> None:
        """Call RequestANCSHeal on the daemon (GUI Try-to-Reconnect, fire-and-forget)."""
        if not self._bus.isConnected():
            return
        iface = QDBusInterface(_BUS_NAME, _OBJECT, _IFACE_DAEMON, self._bus)
        if iface.isValid():
            iface.call("RequestANCSHeal")

    def refresh_contacts(self) -> None:
        """Call RefreshContacts on the daemon (fire-and-forget, tincan-mox38)."""
        if not self._bus.isConnected():
            return
        iface = QDBusInterface(_BUS_NAME, _OBJECT, _IFACE_DAEMON, self._bus)
        if iface.isValid():
            iface.call("RefreshContacts")

    def mark_conversation_read(self, conv_id: str) -> None:
        """Call MarkConversationRead on the daemon (fire-and-forget)."""
        if not self._bus.isConnected():
            return
        result = self._dbus_call(_IFACE_MESSAGES, "MarkConversationRead", str(conv_id))
        if result is None:
            iface = QDBusInterface(_BUS_NAME, _OBJECT, _IFACE_MESSAGES, self._bus)
            if iface.isValid():
                iface.call("MarkConversationRead", str(conv_id))

    def fetch_contact_photo(self, conv_id: str) -> None:
        """Call FetchContactPhoto on the daemon (fire-and-forget)."""
        if not self._bus.isConnected():
            return
        iface = QDBusInterface(_BUS_NAME, _OBJECT, _IFACE_MESSAGES, self._bus)
        if iface.isValid():
            iface.call("FetchContactPhoto", str(conv_id))

    def list_contacts(self) -> list[dict]:
        """Call GetContacts; returns [{phone, name}] or [] when daemon is absent."""
        result = self._dbus_call(_IFACE_MESSAGES, "GetContacts")
        if result is None:
            return []
        try:
            return [dict(c) for c in result]
        except (TypeError, ValueError):
            return []

    # ------------------------------------------------------------------
    # Notification filter methods (im.tincan.Daemon)
    # ------------------------------------------------------------------

    def get_notification_filter(self) -> dict:
        """Call GetNotificationFilter. Returns safe default when daemon is absent."""
        _default: dict = {"enabled": True, "apps": {}}
        if not self._bus.isConnected():
            return _default
        result = self._dbus_call(_IFACE_DAEMON, "GetNotificationFilter")
        if result is not None:
            enabled = bool(result.get("enabled", True)) if hasattr(result, "get") else True
            apps_raw = result.get("apps", {}) if hasattr(result, "get") else {}
            apps: dict = {}
            if hasattr(apps_raw, "items"):
                for app_id, app_data in apps_raw.items():
                    if hasattr(app_data, "get"):
                        action = str(app_data.get("action", "allow"))
                    else:
                        action = "allow"
                    apps[str(app_id)] = action
            return {"enabled": enabled, "apps": apps}
        iface = QDBusInterface(_BUS_NAME, _OBJECT, _IFACE_DAEMON, self._bus)
        if not iface.isValid():
            return _default
        raw = iface.call("GetNotificationFilter")
        if isinstance(raw, QDBusMessage):
            if raw.type() == QDBusMessage.MessageType.ErrorMessage:
                _log.warning("GetNotificationFilter failed: %s", raw.errorMessage())
                return _default
            args = raw.arguments()
            data = _demarshal_map(args[0] if args else {})
        else:
            reply = _wrap_reply(raw)
            if not reply.isValid():
                _log.warning("GetNotificationFilter failed: %s", reply.error().message())
                return _default
            data = _demarshal_map(reply.value())
        enabled = bool(data.get("enabled", True))
        apps_raw = data.get("apps", {})
        apps = {}
        if isinstance(apps_raw, dict):
            for app_id, app_data in apps_raw.items():
                if isinstance(app_data, dict):
                    apps[str(app_id)] = str(app_data.get("action", "allow"))
                else:
                    apps[str(app_id)] = "allow"
        return {"enabled": enabled, "apps": apps}

    def set_notifications_enabled(self, enabled: bool) -> None:
        """Call SetNotificationsEnabled on the daemon (fire-and-forget)."""
        if not self._bus.isConnected():
            return
        result = self._dbus_call(_IFACE_DAEMON, "SetNotificationsEnabled", bool(enabled))
        if result is None:
            iface = QDBusInterface(_BUS_NAME, _OBJECT, _IFACE_DAEMON, self._bus)
            if iface.isValid():
                iface.call("SetNotificationsEnabled", bool(enabled))

    def get_seen_apps(self) -> list[dict]:
        """Call GetSeenApps. Returns [] when daemon is absent."""
        if not self._bus.isConnected():
            return []
        result = self._dbus_call(_IFACE_DAEMON, "GetSeenApps")
        if result is not None:
            return [
                {
                    "app_id": str(r.get("app_id", "")) if hasattr(r, "get") else "",
                    "label_hint": str(r.get("label_hint", "")) if hasattr(r, "get") else "",
                }
                for r in result
            ]
        iface = QDBusInterface(_BUS_NAME, _OBJECT, _IFACE_DAEMON, self._bus)
        if not iface.isValid():
            return []
        raw = iface.call("GetSeenApps")
        if isinstance(raw, QDBusMessage):
            if raw.type() == QDBusMessage.MessageType.ErrorMessage:
                _log.warning("GetSeenApps failed: %s", raw.errorMessage())
                return []
            args = raw.arguments()
            items = _demarshal_list_of_maps(args[0] if args else [])
        else:
            reply = _wrap_reply(raw)
            if not reply.isValid():
                _log.warning("GetSeenApps failed: %s", reply.error().message())
                return []
            items = _demarshal_list_of_maps(reply.value())
        return [
            {"app_id": str(item.get("app_id", "")), "label_hint": str(item.get("label_hint", ""))}
            for item in items
        ]

    def set_app_filter(self, app_id: str, action: str) -> None:
        """Call SetAppFilter on the daemon (fire-and-forget)."""
        if not self._bus.isConnected():
            return
        result = self._dbus_call(_IFACE_DAEMON, "SetAppFilter", str(app_id), str(action))
        if result is None:
            iface = QDBusInterface(_BUS_NAME, _OBJECT, _IFACE_DAEMON, self._bus)
            if iface.isValid():
                iface.call("SetAppFilter", str(app_id), str(action))

    def _on_contact_photo_received(self, conv_id, photo) -> None:
        _log.debug("tincand: ContactPhotoReceived(%s)", conv_id)
        try:
            photo_bytes = bytes(photo) if photo else b""
        except (TypeError, ValueError):
            photo_bytes = b""
        self.contact_photo_received.emit(str(conv_id), photo_bytes)

    # ------------------------------------------------------------------
    # HFP call slot handlers (im.tincan.Calls — tincan-xohrx pending)
    # ------------------------------------------------------------------

    @Slot(str, str)
    def _on_call_incoming(self, caller_name: str, caller_number: str) -> None:
        _log.debug("tincand: IncomingCall(%s, %s)", caller_name, caller_number)
        self.call_incoming.emit(str(caller_name), str(caller_number))

    @Slot()
    def _on_call_connected(self) -> None:
        _log.debug("tincand: CallConnected")
        self.call_connected.emit()

    @Slot()
    def _on_call_ended(self) -> None:
        _log.debug("tincand: CallEnded")
        self.call_ended.emit()

    @Slot(str)
    def _on_audio_error(self, reason: str) -> None:
        _log.debug("tincand: AudioError(%s)", reason)
        self.audio_error.emit(str(reason))

    @Slot()
    def _on_audio_restored(self) -> None:
        _log.debug("tincand: AudioRestored")
        self.audio_restored.emit()

    @Slot(str, str)
    def _on_call_active(self, call_id: str, number: str) -> None:
        _log.debug("tincand: CallActive(%s)", call_id)
        self.call_active.emit(str(call_id), str(number))

    @Slot(str, str)
    def _on_call_held(self, call_id: str, number: str) -> None:
        _log.debug("tincand: CallHeld(%s)", call_id)
        self.call_held.emit(str(call_id), str(number))

    @Slot(str, str, str)
    def _on_call_waiting(self, call_id: str, number: str, name: str) -> None:
        _log.debug("tincand: CallWaiting(%s)", call_id)
        self.call_waiting.emit(str(call_id), str(number), str(name))

    @Slot(str)
    def _on_call_removed(self, call_id: str) -> None:
        _log.debug("tincand: CallRemoved(%s)", call_id)
        self.call_removed.emit(str(call_id))

    def answer(self, call_id: str = "") -> None:
        """Answer the current incoming HFP call."""
        try:
            self._dbus_call(_IFACE_CALLS, "Answer", str(call_id))
        except Exception as exc:
            _log.debug("answer(%r) failed: %s", call_id, exc)

    def hangup(self, call_id: str = "") -> None:
        """Hang up or decline the current HFP call."""
        try:
            self._dbus_call(_IFACE_CALLS, "Hangup", str(call_id))
        except Exception as exc:
            _log.debug("hangup(%r) failed: %s", call_id, exc)

    def dial(self, number: str) -> str:
        """Initiate an outbound HFP call; returns daemon-assigned call_id."""
        try:
            result = self._dbus_call(_IFACE_CALLS, "Dial", str(number))
            return str(result) if result else ""
        except Exception as exc:
            _log.debug("dial(%r) failed: %s", number, exc)
            return ""

    def hold_and_answer(self) -> None:
        """Hold the active call and answer the waiting call."""
        try:
            self._dbus_call(_IFACE_CALLS, "HoldAndAnswer")
        except Exception as exc:
            _log.debug("hold_and_answer() failed: %s", exc)

    def release_and_answer(self) -> None:
        """Release the active call and answer the waiting call."""
        try:
            self._dbus_call(_IFACE_CALLS, "ReleaseAndAnswer")
        except Exception as exc:
            _log.debug("release_and_answer() failed: %s", exc)

    def send_dtmf(self, key: str) -> None:
        """Send a DTMF tone during an active HFP call.

        Calls im.tincan.Calls.SendDtmf(key) on tincand.
        Silently no-ops on method-not-found or any bus error (interface name
        pending architect confirmation via tincan-xohrx).
        """
        # TODO(tincan-xohrx): update _IFACE_CALLS and method name once confirmed
        try:
            self._dbus_call(_IFACE_CALLS, "SendDtmf", key)
        except Exception as exc:
            _log.debug("send_dtmf(%r) failed: %s", key, exc)
