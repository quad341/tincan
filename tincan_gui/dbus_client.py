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
    QDBusReply,
)

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

    # Messages interface
    message_received = Signal(dict)        # message a{sv} → dict
    message_sent = Signal(str)             # message_id
    conversation_updated = Signal(dict)    # conversation a{sv} → dict

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
            b.connect(_BUS_NAME, _OBJECT, _IFACE_MESSAGES, "MessageReceived",
                      self, "1_on_message_received(QVariantMap)"),
            b.connect(_BUS_NAME, _OBJECT, _IFACE_MESSAGES, "MessageSent",
                      self, "1_on_message_sent(QString)"),
            b.connect(_BUS_NAME, _OBJECT, _IFACE_MESSAGES, "ConversationUpdated",
                      self, "1_on_conversation_updated(QVariantMap)"),
        ]
        if not all(_ok):
            _log.warning("tincan D-Bus: some signal subscriptions failed: %s", _ok)
        else:
            _log.debug("tincan D-Bus: all 6 signal subscriptions registered")

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
        """Call GetStatus.  Returns {} when daemon is absent."""
        if not self._bus.isConnected():
            return {}
        result = self._dbus_call(_IFACE_DAEMON, "GetStatus")
        if result is not None:
            return {str(k): v for k, v in result.items()} if hasattr(result, "items") else {}
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
            return _demarshal_map(args[0] if args else {})
        reply = _wrap_reply(raw)
        if not reply.isValid():
            _log.debug("GetStatus failed: %s", reply.error().message())
            return {}
        return _demarshal_map(reply.value())

    def list_conversations(self) -> list[dict]:
        """Call ListConversations.  Returns [] when daemon is absent."""
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
        return _demarshal_list_of_maps(reply.value())

    def get_messages(self, conv_id: str) -> list[dict]:
        """Call GetMessages(conv_id).  Returns [] when daemon is absent."""
        if not self._bus.isConnected():
            return []
        result = self._dbus_call(_IFACE_MESSAGES, "GetMessages", str(conv_id))
        if result is not None:
            return [
                {str(k): v for k, v in msg.items()}
                for msg in result
                if hasattr(msg, "items")
            ]
        iface = QDBusInterface(_BUS_NAME, _OBJECT, _IFACE_MESSAGES, self._bus)
        if not iface.isValid():
            return []
        raw = iface.call("GetMessages", str(conv_id))
        if isinstance(raw, QDBusMessage):
            if raw.type() == QDBusMessage.MessageType.ErrorMessage:
                _log.debug("GetMessages failed: %s", raw.errorMessage())
                return []
            args = raw.arguments()
            return _demarshal_list_of_maps(args[0] if args else [])
        reply = _wrap_reply(raw)
        if not reply.isValid():
            _log.debug("GetMessages failed: %s", reply.error().message())
            return []
        return _demarshal_list_of_maps(reply.value())

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
