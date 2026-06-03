"""tincand D-Bus service — im.tincan.Daemon and im.tincan.Messages.

Bus name:    im.tincan.Daemon
Object path: /im/tincan

Implements the interface contract from tincan-56i, with amendments:
  tincan-40c: capabilities dict always includes messages/contacts/ancs keys.
  tincan-5mze: ancs_needs_repair added to capabilities (FALLBACK state indicator).
  tincan-bxs: Conversation dict always includes last_message_preview(s) and
              unread_count(u); unread_count resets on Connect/reconnect,
              increments on inbound unread MessageReceived.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import dbus
import dbus.exceptions
import dbus.service

_log = logging.getLogger(__name__)

BUS_NAME = "im.tincan.Daemon"
OBJECT_PATH = "/im/tincan"
IFACE_DAEMON = "im.tincan.Daemon"
IFACE_MESSAGES = "im.tincan.Messages"


@dataclass
class Conversation:
    id: str
    display_name: str
    participants: list[str] = field(default_factory=list)
    last_message_at: str = ""
    last_message_preview: str = ""
    unread_count: int = 0

    def to_dbus(self) -> dbus.Dictionary:
        return dbus.Dictionary(
            {
                "id": dbus.String(self.id),
                "display_name": dbus.String(self.display_name),
                "participants": dbus.Array(
                    [dbus.String(p) for p in self.participants], signature="s"
                ),
                "last_message_at": dbus.String(self.last_message_at),
                "last_message_preview": dbus.String(self.last_message_preview),
                "unread_count": dbus.UInt32(self.unread_count),
            },
            signature="sv",
        )


class TincanService(dbus.service.Object):
    """tincand D-Bus service object at /im/tincan."""

    def __init__(self, bus: dbus.SessionBus) -> None:
        bus_name = dbus.service.BusName(BUS_NAME, bus=bus)
        super().__init__(bus_name, OBJECT_PATH)
        self._connected = False
        self._device_address = ""
        self._device_name = ""
        # tincan-40c: all capability keys always present, default False.
        # tincan-5mze: ancs_needs_repair added for FALLBACK state.
        self._capabilities: dict[str, bool] = {
            "messages": False,
            "contacts": False,
            "ancs": False,
            "ancs_needs_repair": False,
        }
        self._conversations: dict[str, Conversation] = {}
        self._messages: dict[str, list[dict]] = {}
        self._message_keys: set[tuple] = set()
        self._backend: object | None = None

    # ------------------------------------------------------------------
    # im.tincan.Daemon — lifecycle and status
    # ------------------------------------------------------------------

    @dbus.service.method(IFACE_DAEMON, in_signature="s", out_signature="")
    def Connect(self, device_address: str) -> None:
        if self._connected:
            raise dbus.exceptions.DBusException(
                "Session already active",
                name="im.tincan.Error.AlreadyConnected",
            )
        # TODO(review F3): raise im.tincan.Error.DeviceNotFound when device_address
        # is not in the BlueZ paired-devices list.  Requires BlueZ adapter wiring
        # (tincand/bluetooth/pairing.py) — deferred to M1.1.
        self._connected = True
        self._device_address = str(device_address)
        # tincan-bxs: reset unread_count for all conversations on connect.
        for conv in self._conversations.values():
            conv.unread_count = 0
        self._messages.clear()
        self._message_keys.clear()
        _log.info("Connected to %s", device_address)
        self.Connected(str(device_address))

    @dbus.service.method(IFACE_DAEMON, in_signature="", out_signature="")
    def Disconnect(self) -> None:
        if not self._connected:
            return
        self._connected = False
        self._device_address = ""
        self._device_name = ""
        self._capabilities = {
            "messages": False,
            "contacts": False,
            "ancs": False,
            "ancs_needs_repair": False,
        }
        _log.info("Disconnected")
        self.Disconnected()

    @dbus.service.method(IFACE_DAEMON, in_signature="", out_signature="a{sv}")
    def GetStatus(self) -> dbus.Dictionary:
        """Return current daemon status.

        Keys: connected(b), device_address(s), capabilities(a{sb}).
        capabilities always includes messages, contacts, ancs — even when
        disconnected (tincan-40c).  Never raises.
        """
        return dbus.Dictionary(
            {
                "connected": dbus.Boolean(self._connected),
                "device_address": dbus.String(self._device_address),
                "device_name": dbus.String(self._device_name),
                "capabilities": dbus.Dictionary(
                    {k: dbus.Boolean(v) for k, v in self._capabilities.items()},
                    signature="sb",
                ),
            },
            signature="sv",
        )

    @dbus.service.signal(IFACE_DAEMON, signature="s")
    def Connected(self, device_address: str) -> None:  # noqa: N802
        pass

    @dbus.service.signal(IFACE_DAEMON, signature="")
    def Disconnected(self) -> None:  # noqa: N802
        pass

    @dbus.service.signal(IFACE_DAEMON, signature="sb")
    def CapabilityChanged(self, feature: str, available: bool) -> None:  # noqa: N802
        pass

    _KNOWN_CAPABILITIES = frozenset({"messages", "contacts", "ancs", "ancs_needs_repair"})

    def set_capability(self, feature: str, available: bool) -> None:
        """Update a capability and emit CapabilityChanged.

        Called by Bluetooth adapters (e.g. AncsAdapter.set_capability('ancs', True)
        when the ANCS GATT subscription is established or dropped).
        Unknown feature names are logged and rejected to avoid silently polluting
        the capabilities dict (review F2).
        """
        if feature not in self._KNOWN_CAPABILITIES:
            _log.warning("set_capability: unknown feature %r — ignored", feature)
            return
        self._capabilities[feature] = bool(available)
        _log.debug("Capability %s → %s", feature, available)
        self.CapabilityChanged(str(feature), bool(available))

    def set_device_name(self, name: str) -> None:
        """Set the human-readable Bluetooth device name (e.g. BlueZ Device1.Alias)."""
        self._device_name = str(name)

    def register_backend(self, backend: object) -> None:
        """Wire the backend so SendMessage/GetMessage delegate to it."""
        self._backend = backend

    # ------------------------------------------------------------------
    # im.tincan.Messages — SMS/iMessage send and receive
    # ------------------------------------------------------------------

    @dbus.service.method(IFACE_MESSAGES, in_signature="", out_signature="aa{sv}")
    def ListConversations(self) -> list:
        """Return all known conversations sorted by last_message_at descending.

        Each Conversation dict always includes last_message_preview(s) and
        unread_count(u) (tincan-bxs).  Raises NotConnected if no session.
        """
        if not self._connected:
            raise dbus.exceptions.DBusException(
                "No active Bluetooth session",
                name="im.tincan.Error.NotConnected",
            )
        conversations = sorted(
            self._conversations.values(),
            key=lambda c: c.last_message_at,
            reverse=True,
        )
        return [c.to_dbus() for c in conversations]

    @dbus.service.method(IFACE_MESSAGES, in_signature="s", out_signature="aa{sv}")
    def GetMessages(self, conv_id: str) -> list:  # noqa: A002
        """Return stored messages for *conv_id*, oldest first.

        Raises NotConnected if no session.  Returns [] for unknown conv_id.
        """
        if not self._connected:
            raise dbus.exceptions.DBusException(
                "No active Bluetooth session",
                name="im.tincan.Error.NotConnected",
            )
        msgs = self._messages.get(str(conv_id), [])
        return [
            dbus.Dictionary(
                {k: dbus.String(str(v)) for k, v in msg.items()},
                signature="sv",
            )
            for msg in msgs
        ]

    @dbus.service.method(IFACE_MESSAGES, in_signature="s", out_signature="a{sv}")
    def GetMessage(self, id: str) -> dbus.Dictionary:  # noqa: A002
        if not self._connected:
            raise dbus.exceptions.DBusException(
                "No active Bluetooth session",
                name="im.tincan.Error.NotConnected",
            )
        if self._backend is None:
            raise dbus.exceptions.DBusException(
                "Message handle not found or session expired",
                name="im.tincan.Error.MessageNotFound",
            )
        body = self._backend.get_message(str(id))  # type: ignore[attr-defined]
        if body is None:
            raise dbus.exceptions.DBusException(
                "Message handle not found or session expired",
                name="im.tincan.Error.MessageNotFound",
            )
        return dbus.Dictionary(
            {
                "id": dbus.String(str(id)),
                "body": dbus.String(str(body)),
                "direction": dbus.String("inbound"),
                "status": dbus.String("read"),
                "timestamp": dbus.String(""),
                "conversation_id": dbus.String(""),
            },
            signature="sv",
        )

    @dbus.service.method(IFACE_MESSAGES, in_signature="ss", out_signature="s")
    def SendMessage(self, to: str, body: str) -> str:
        if not to or not body:
            raise dbus.exceptions.DBusException(
                "to and body must be non-empty",
                name="im.tincan.Error.InvalidArgument",
            )
        if not self._connected:
            raise dbus.exceptions.DBusException(
                "No active Bluetooth session",
                name="im.tincan.Error.NotConnected",
            )
        if self._backend is None:
            raise dbus.exceptions.DBusException(
                "No backend registered",
                name="im.tincan.Error.SendFailed",
            )
        try:
            handle = self._backend.send_message(str(to), str(body))  # type: ignore[attr-defined]
        except Exception as exc:
            raise dbus.exceptions.DBusException(
                str(exc),
                name="im.tincan.Error.SendFailed",
            ) from exc
        self.MessageSent(str(handle))
        return str(handle)

    @dbus.service.signal(IFACE_MESSAGES, signature="a{sv}")
    def MessageReceived(self, message: dbus.Dictionary) -> None:  # noqa: N802
        pass

    @dbus.service.signal(IFACE_MESSAGES, signature="s")
    def MessageSent(self, message_id: str) -> None:  # noqa: N802
        pass

    @dbus.service.signal(IFACE_MESSAGES, signature="a{sv}")
    def ConversationUpdated(self, conversation: dbus.Dictionary) -> None:  # noqa: N802
        pass

    # ------------------------------------------------------------------
    # Internal helpers called by Bluetooth adapters
    # ------------------------------------------------------------------

    def upsert_conversation(self, conv: Conversation) -> None:
        """Add or replace a conversation in the in-memory store."""
        self._conversations[conv.id] = conv

    def on_message_received(self, message: dict) -> None:
        """Record an inbound message; update conversation state; emit signals.

        Callers pass a normalized Message dict (per tincan-56i §2.1).
        tincan-bxs invariants maintained here:
          - last_message_preview updated to verbatim body if this message is newest.
          - unread_count incremented for inbound status=unread messages; never
            decremented.
        """
        conv_id = str(message.get("conversation_id", ""))
        body = str(message.get("body", ""))
        timestamp = str(message.get("timestamp", ""))
        direction = str(message.get("direction", ""))
        status = str(message.get("status", ""))

        # Store message for GetMessages; deduplicate by (conv_id, timestamp, body).
        msg_key = (conv_id, timestamp, body)
        if conv_id and msg_key not in self._message_keys:
            self._message_keys.add(msg_key)
            self._messages.setdefault(conv_id, []).append({
                "id": f"{conv_id}:{timestamp}",
                "conversation_id": conv_id,
                "body": body,
                "timestamp": timestamp,
                "direction": direction,
                "status": status,
                "from": str(message.get("from", conv_id)),
            })

        if conv_id in self._conversations:
            conv = self._conversations[conv_id]
            if not conv.last_message_at or timestamp >= conv.last_message_at:
                conv.last_message_at = timestamp
                conv.last_message_preview = body  # GUI owns truncation
            if direction == "inbound" and status == "unread":
                conv.unread_count += 1
            updated_conv = conv.to_dbus()
        else:
            # Unknown conv_id: emit MessageReceived but skip ConversationUpdated.
            # MAP adapters must call upsert_conversation() before delivering messages
            # so the daemon always has a Conversation object to update (review F4).
            updated_conv = None

        msg_dbus = dbus.Dictionary(
            {
                k: dbus.String(str(v)) if not isinstance(v, bool) else dbus.Boolean(v)
                for k, v in message.items()
            },
            signature="sv",
        )
        self.MessageReceived(msg_dbus)
        if updated_conv is not None:
            self.ConversationUpdated(updated_conv)
