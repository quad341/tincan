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

_log = logging.getLogger(__name__)

_BUS_NAME = "im.tincan.Daemon"
_OBJECT = "/im/tincan"
_IFACE_DAEMON = "im.tincan.Daemon"
_IFACE_MESSAGES = "im.tincan.Messages"


# ---------------------------------------------------------------------------
# QDBusArgument demarshalling helpers
# ---------------------------------------------------------------------------

def _demarshal_map(value) -> dict:
    """Demarshal a{sv} QDBusArgument (or plain dict) into a Python dict."""
    if isinstance(value, dict):
        return dict(value)
    if not isinstance(value, QDBusArgument):
        return {}
    result: dict = {}
    value.beginMap()
    while not value.atEnd():
        value.beginMapEntry()
        k = value.asVariant()
        v = value.asVariant()
        value.endMapEntry()
        result[str(k)] = v
    value.endMap()
    return result


def _demarshal_list_of_maps(value) -> list[dict]:
    """Demarshal aa{sv} QDBusArgument (or plain list) into a list of dicts."""
    if isinstance(value, list):
        return [_demarshal_map(item) for item in value]
    if not isinstance(value, QDBusArgument):
        return []
    result: list[dict] = []
    value.beginArray()
    while not value.atEnd():
        result.append(_demarshal_map(value))
    value.endArray()
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

    def get_status(self) -> dict:
        """Call GetStatus.  Returns {} when daemon is absent."""
        if not self._bus.isConnected():
            return {}
        iface = QDBusInterface(_BUS_NAME, _OBJECT, _IFACE_DAEMON, self._bus)
        if not iface.isValid():
            return {}
        reply = _wrap_reply(iface.call("GetStatus"))
        if not reply.isValid():
            _log.debug("GetStatus failed (daemon likely absent): %s", reply.error().message())
            return {}
        return _demarshal_map(reply.value())

    def list_conversations(self) -> list[dict]:
        """Call ListConversations.  Returns [] when daemon is absent."""
        if not self._bus.isConnected():
            return []
        iface = QDBusInterface(_BUS_NAME, _OBJECT, _IFACE_MESSAGES, self._bus)
        if not iface.isValid():
            return []
        reply = _wrap_reply(iface.call("ListConversations"))
        if not reply.isValid():
            _log.debug("ListConversations failed: %s", reply.error().message())
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
