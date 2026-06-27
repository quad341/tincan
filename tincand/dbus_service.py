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

import hashlib
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime

import dbus
import dbus.exceptions
import dbus.service

from tincand.contact_store import ContactStore, normalize_phone
from tincand.notification_filter import NotificationFilter, SeenAppsRegistry

_log = logging.getLogger(__name__)

BUS_NAME = "im.tincan.Daemon"
OBJECT_PATH = "/im/tincan"
IFACE_DAEMON = "im.tincan.Daemon"
IFACE_MESSAGES = "im.tincan.Messages"
IFACE_CALLS = "im.tincan.Calls"


@dataclass
class Conversation:
    id: str
    display_name: str
    participants: list[str] = field(default_factory=list)
    last_message_at: str = ""
    last_message_preview: str = ""
    last_message_direction: str = ""
    unread_count: int = 0
    send_target: str = ""  # canonical phone for reply (may differ from id when id is name-keyed)
    is_group: bool = False
    group_name: str = ""

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
                "last_message_direction": dbus.String(self.last_message_direction),
                "unread_count": dbus.UInt32(self.unread_count),
                "send_target": dbus.String(self.send_target),
                "is_group": dbus.Boolean(self.is_group),
                "group_name": dbus.String(self.group_name),
            },
            signature="sv",
        )


def _normalize_phone(number: str) -> str:
    """Strip non-digit characters from a phone number, preserving a leading +."""
    number = number.strip()
    if number.startswith("+"):
        return "+" + re.sub(r"[^\d]", "", number[1:])
    return re.sub(r"[^\d]", "", number)


class TincanService(dbus.service.Object):
    """tincand D-Bus service object at /im/tincan."""

    def __init__(self, bus: dbus.SessionBus) -> None:
        # do_not_queue=True makes a second instance fail fast (NameExistsException)
        # instead of silently queueing for the name while running forever — that
        # queuing was how stale daemons accumulated and exhausted the session-bus
        # FD limit. The entry point (__main__) catches this and exits cleanly.
        bus_name = dbus.service.BusName(BUS_NAME, bus=bus, do_not_queue=True)
        super().__init__(bus_name, OBJECT_PATH)
        self._connected = False
        self._device_address = ""
        self._device_name = ""
        # tincan-40c: all capability keys always present, default False.
        # tincan-5mze: ancs_needs_repair added for FALLBACK state.
        # tincan-r41sx: call_setup_ready is system-level (SELinux module present),
        # not per-connection; it is NOT reset on Disconnect.
        self._capabilities: dict[str, bool] = {
            "messages": False,
            "contacts": False,
            "contacts_empty": False,   # True when PBAP loaded but found 0 contacts (tincan-d3xw)
            "ancs": False,
            "ancs_needs_repair": False,
            "call_setup_ready": False,
        }
        self._conversations: dict[str, Conversation] = {}
        self._messages: dict[str, list[dict]] = {}
        self._message_keys: set[tuple] = set()
        self._group_participants: dict[str, list[str]] = {}
        self._backend: object | None = None
        self._contact_store = ContactStore()
        self._pbap: object | None = None  # set by __main__ after construction
        self._call_controller: object | None = None  # set by __main__ after construction
        self._notification_filter = NotificationFilter()
        self._seen_apps = SeenAppsRegistry()
        self._adapter_path: str = ""
        self._adapter_path_requested: str = ""
        self._adapter_warning: str = ""
        self._device_discovered: bool = False

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
        # Preserve call_setup_ready — it reflects SELinux module presence, not BT state.
        call_setup_ready = self._capabilities.get("call_setup_ready", False)
        self._capabilities = {
            "messages": False,
            "contacts": False,
            "contacts_empty": False,
            "ancs": False,
            "ancs_needs_repair": False,
            "call_setup_ready": call_setup_ready,
        }
        self._contact_store.clear()
        _log.info("Disconnected")
        self.Disconnected()

    @dbus.service.method(IFACE_DAEMON, in_signature="", out_signature="")
    def RequestReconnect(self) -> None:
        """Ask the backend to schedule a reconnect attempt (fire-and-forget)."""
        if self._backend is not None:
            self._backend.schedule_reconnect()

    @dbus.service.method(IFACE_DAEMON, in_signature="", out_signature="")
    def RequestANCSHeal(self) -> None:
        """GUI Try-to-Reconnect: re-enter HEALING from FALLBACK (fire-and-forget)."""
        if self._backend is not None and hasattr(self._backend, "request_heal"):
            self._backend.request_heal()

    @dbus.service.method(IFACE_DAEMON, in_signature="", out_signature="a{sv}")
    def GetStatus(self) -> dbus.Dictionary:
        """Return current daemon status.

        Keys: connected(b), device_address(s), capabilities(a{sb}),
        adapter_path_requested(s), adapter_warning(s), device_discovered(b).
        capabilities always includes messages, contacts, ancs — even when
        disconnected (tincan-40c).  Never raises.
        adapter_path_requested is '' unless the QSettings adapter was absent at
        startup and the daemon fell back to a different adapter.
        adapter_warning is '' when adapter is correct; non-empty is actionable
        operator guidance (plain text, no ANSI/Markdown).
        device_discovered is True when the device address came from oFono
        auto-discovery rather than explicit config/CLI.
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
                "adapter_path": dbus.String(self._adapter_path),
                "adapter_path_requested": dbus.String(self._adapter_path_requested),
                "adapter_warning": dbus.String(self._adapter_warning),
                "device_discovered": dbus.Boolean(self._device_discovered),
            },
            signature="sv",
        )

    @dbus.service.method(IFACE_DAEMON, in_signature="", out_signature="aa{sv}")
    def GetAdapters(self) -> list:
        """Return all BlueZ adapters with capability and selection state.

        Each dict: path(s), alias(s), address(s), powered(b),
        hfp_sco_capable(s: 'yes'/'no'/'unknown'), le_capable(b), is_selected(b).
        is_selected reflects QSettings bluetooth/adapter_path at call time.
        Returns [] if BlueZ is unavailable.
        """
        from tincand.adapter_check import list_adapters  # noqa: PLC0415
        from tincand.config import DaemonSettings  # noqa: PLC0415

        settings_path = DaemonSettings().value("bluetooth/adapter_path", default=None)
        result = []
        for a in list_adapters():
            cap = a["hfp_sco_capable"]
            hfp_str = "yes" if cap is True else ("no" if cap is False else "unknown")
            result.append(dbus.Dictionary(
                {
                    "path": dbus.String(a["path"]),
                    "alias": dbus.String(a["alias"]),
                    "address": dbus.String(a["address"]),
                    "powered": dbus.Boolean(a["powered"]),
                    "hfp_sco_capable": dbus.String(hfp_str),
                    "le_capable": dbus.Boolean(a["le_capable"]),
                    "is_selected": dbus.Boolean(a["path"] == settings_path),
                },
                signature="sv",
            ))
        return result

    @dbus.service.signal(IFACE_DAEMON, signature="s")
    def Connected(self, device_address: str) -> None:  # noqa: N802
        pass

    @dbus.service.signal(IFACE_DAEMON, signature="")
    def Disconnected(self) -> None:  # noqa: N802
        pass

    @dbus.service.signal(IFACE_DAEMON, signature="sb")
    def CapabilityChanged(self, feature: str, available: bool) -> None:  # noqa: N802
        pass

    @dbus.service.signal(IFACE_DAEMON, signature="a{sv}")
    def AppNotificationReceived(self, payload: dbus.Dictionary) -> None:  # noqa: N802
        pass

    _KNOWN_CAPABILITIES = frozenset({
        "messages", "contacts", "contacts_empty", "ancs", "ancs_needs_repair",
        "call_setup_ready",
    })

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

    def set_adapter_path(self, path: str) -> None:
        """Record the resolved BT adapter path the daemon is running with."""
        self._adapter_path = str(path)

    def set_adapter_path_requested(self, path: str) -> None:
        """Record the QSettings adapter path that was unavailable at startup.

        Set to '' when the running adapter matches what was requested (no mismatch).
        Set to the QSettings path when the daemon fell back to a different adapter.
        Reported via GetStatus() as adapter_path_requested.
        """
        self._adapter_path_requested = str(path)

    def set_adapter_warning(self, text: str) -> None:
        """Set or clear the adapter mismatch warning.

        Non-empty text means the iPhone is connected on the wrong adapter (no SCO).
        Empty string means adapter is correct or state is unknown.
        Plain text only — no ANSI codes, no Markdown.
        """
        self._adapter_warning = str(text)

    def set_device_discovered(self, discovered: bool) -> None:
        """Record whether the device address came from oFono auto-discovery.

        True only when _resolve_device_address() found the device via oFono
        GetModems() (Step 4 of the priority chain).  False for explicit
        CLI/env/config sources.
        """
        self._device_discovered = bool(discovered)

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
        Falls back to the normalize_phone key so GUI lookups by name-keyed or
        differently-formatted phone IDs still find phone-keyed stored messages.
        """
        if not self._connected:
            raise dbus.exceptions.DBusException(
                "No active Bluetooth session",
                name="im.tincan.Error.NotConnected",
            )
        raw = str(conv_id)
        raw_msgs = self._messages.get(raw, [])
        if not raw_msgs:
            norm = normalize_phone(raw)
            if norm and len(norm) >= 7 and norm != raw:
                raw_msgs = self._messages.get(norm, [])
        msgs = sorted(raw_msgs, key=lambda m: m.get("timestamp", "") or "")
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

    @staticmethod
    def _resolve_to_phone(
        to: str,
        conversations: dict,
        contact_store: ContactStore,
    ) -> str:
        """Return a canonical phone number for *to*, which may be a display name.

        Resolution order:
        1. normalize_phone(to) has 7+ digits → it is a phone; return it.
        2. contact_store.lookup_by_name(to) → PBAP-populated reverse lookup.
        3. Scan conversations for display_name match with a phone-shaped id.
        4. Fall back to *to* unchanged (MAP send will fail; caller logs/raises).
        """
        normalized = normalize_phone(to)
        if len(normalized) >= 7:
            return normalized
        by_name = contact_store.lookup_by_name(to)
        if by_name:
            return by_name
        to_lower = to.lower()
        for conv in conversations.values():
            if conv.display_name.lower() == to_lower:
                if conv.send_target:
                    return conv.send_target
                cid_norm = normalize_phone(conv.id)
                if len(cid_norm) >= 7:
                    return cid_norm
        return to

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
        if to in self._group_participants and self._backend is not None:
            try:
                participants = self._group_participants[to]
                return str(
                    self._backend.send_group_message(participants, body)  # type: ignore[attr-defined]
                )
            except RuntimeError as exc:
                raise dbus.exceptions.DBusException(
                    str(exc), name="im.tincan.Error.SendFailed"
                ) from exc
        if self._backend is None:
            raise dbus.exceptions.DBusException(
                "No backend registered",
                name="im.tincan.Error.SendFailed",
            )
        phone_to = self._resolve_to_phone(str(to), self._conversations, self._contact_store)
        try:
            handle = self._backend.send_message(phone_to, str(body))  # type: ignore[attr-defined]
        except Exception as exc:
            raise dbus.exceptions.DBusException(
                str(exc),
                name="im.tincan.Error.SendFailed",
            ) from exc
        now_iso = datetime.now().strftime("%Y%m%dT%H%M%S")
        normalized_to = normalize_phone(phone_to)
        raw_to = str(to)
        conv_id_for_send = raw_to if raw_to in self._conversations else normalized_to
        # Ensure the conversation exists so on_message_received emits ConversationUpdated.
        # Without this, sending to a new contact produces no thread in the GUI conversation list.
        if conv_id_for_send not in self._conversations:
            display = self._contact_store.get_name(normalized_to) or normalized_to
            self.upsert_conversation(Conversation(
                id=conv_id_for_send,
                display_name=display,
                send_target=normalized_to,
            ))
        self.on_message_received({
            "id": str(handle),
            "conversation_id": conv_id_for_send,
            "direction": "outbound",
            "status": "read",
            "body": str(body),
            "from": "",
            "timestamp": now_iso,
        })
        self.MessageSent(str(handle))
        return str(handle)

    @dbus.service.method(IFACE_MESSAGES, in_signature="ass", out_signature="s")
    def SendMessageToRecipients(self, recipients: list, body: str) -> str:
        """Start a group conversation and optionally send an opening message."""
        if len(recipients) < 2:
            raise dbus.exceptions.DBusException(
                "At least 2 recipients required",
                name="im.tincan.Error.InvalidArgument",
            )
        normalized: list[str] = []
        for r in recipients:
            phone = _normalize_phone(str(r))
            if len(re.sub(r"[^\d]", "", phone)) < 7:
                raise dbus.exceptions.DBusException(
                    f"Invalid phone number: {r!r}",
                    name="im.tincan.Error.InvalidArgument",
                )
            normalized.append(phone)

        if not self._connected:
            raise dbus.exceptions.DBusException(
                "No active Bluetooth session",
                name="im.tincan.Error.NotConnected",
            )

        key = "|".join(sorted(normalized))
        conv_id = hashlib.sha1(key.encode()).hexdigest()[:8]
        self._group_participants[conv_id] = normalized

        label = f"{normalized[0]}, {normalized[1]}"
        if len(normalized) > 2:
            label += f" & {len(normalized) - 2} more"
        conv = Conversation(
            id=conv_id,
            display_name=label,
            participants=normalized,
            is_group=True,
            group_name=label,
        )
        self.upsert_conversation(conv)

        if body and os.environ.get("TINCAN_GROUP_SEND_ENABLED") and self._backend is not None:
            try:
                self._backend.send_group_message(normalized, body)  # type: ignore[attr-defined]
            except RuntimeError as exc:
                raise dbus.exceptions.DBusException(
                    str(exc), name="im.tincan.Error.SendFailed"
                ) from exc

        return conv_id

    @dbus.service.method(IFACE_MESSAGES, in_signature="s", out_signature="as")
    def GetConversationParticipants(self, conv_id: str) -> list:
        """Return phone numbers for *conv_id*, or [] if unknown."""
        return [dbus.String(p) for p in self._group_participants.get(conv_id, [])]

    @dbus.service.method(IFACE_MESSAGES, in_signature="", out_signature="aa{sv}")
    def GetContacts(self) -> list:  # noqa: N802
        """Return [{phone, name}] for all PBAP-synced contacts."""
        result = []
        for contact in self._contact_store.all_contacts():
            if contact.name:
                result.append(dbus.Dictionary(
                    {"phone": dbus.String(contact.normalized_phone),
                     "name": dbus.String(contact.name)},
                    signature="sv",
                ))
        return dbus.Array(result, signature="a{sv}")

    @dbus.service.signal(IFACE_MESSAGES, signature="a{sv}")
    def MessageReceived(self, message: dbus.Dictionary) -> None:  # noqa: N802
        pass

    @dbus.service.signal(IFACE_MESSAGES, signature="s")
    def MessageSent(self, message_id: str) -> None:  # noqa: N802
        pass

    @dbus.service.signal(IFACE_MESSAGES, signature="a{sv}")
    def ConversationUpdated(self, conversation: dbus.Dictionary) -> None:  # noqa: N802
        pass

    @dbus.service.signal(IFACE_MESSAGES, signature="say")
    def ContactPhotoReceived(  # noqa: N802
        self, conversation_id: str, photo: dbus.Array
    ) -> None:
        pass

    @dbus.service.method(IFACE_MESSAGES, in_signature="s", out_signature="")
    def MarkConversationRead(self, conversation_id: str) -> None:  # noqa: N802
        """Reset unread_count to 0 for the given conversation and emit ConversationUpdated."""
        conv = self._conversations.get(str(conversation_id))
        if conv is not None and conv.unread_count != 0:
            conv.unread_count = 0
            self.ConversationUpdated(conv.to_dbus())

    @dbus.service.method(IFACE_MESSAGES, in_signature="s", out_signature="")
    def FetchContactPhoto(self, conversation_id: str) -> None:  # noqa: N802
        if self._pbap is not None:
            self._pbap.fetch_photo(str(conversation_id))

    @dbus.service.method(IFACE_DAEMON, in_signature="", out_signature="")
    def RefreshContacts(self) -> None:  # noqa: N802
        """Re-pull PBAP contacts without a daemon restart (tincan-mox38).

        Fire-and-forget — results arrive via ConversationUpdated signals as
        vCards are parsed and names resolved.
        """
        if self._pbap is not None:
            self._pbap.refresh()

    # ------------------------------------------------------------------
    # im.tincan.Daemon — notification filter API (tincan-9kav)
    # ------------------------------------------------------------------

    @dbus.service.method(IFACE_DAEMON, in_signature="", out_signature="a{sv}")
    def GetNotificationFilter(self) -> dbus.Dictionary:  # noqa: N802
        """Return {enabled: b, apps: a{sa{sv}}} with current filter state."""
        enabled = self._notification_filter.is_enabled()
        app_filters = self._notification_filter.get_all_filters()
        apps_dict = dbus.Dictionary(
            {
                app_id: dbus.Dictionary(
                    {"action": dbus.String(action)}, signature="sv"
                )
                for app_id, action in app_filters.items()
            },
            signature="sa{sv}",
        )
        return dbus.Dictionary(
            {"enabled": dbus.Boolean(enabled), "apps": apps_dict},
            signature="sv",
        )

    @dbus.service.method(IFACE_DAEMON, in_signature="b", out_signature="")
    def SetNotificationsEnabled(self, enabled: bool) -> None:  # noqa: N802
        """Persist the global app notification mirroring toggle."""
        self._notification_filter.set_enabled(bool(enabled))

    @dbus.service.method(IFACE_DAEMON, in_signature="ss", out_signature="")
    def SetAppFilter(self, app_id: str, action: str) -> None:  # noqa: N802
        """Persist allow/deny for app_id. Raises InvalidArgument on bad action."""
        if str(action) not in ("allow", "deny"):
            raise dbus.exceptions.DBusException(
                f"Invalid action {action!r}; must be 'allow' or 'deny'",
                name="im.tincan.Error.InvalidArgument",
            )
        self._notification_filter.set_filter(str(app_id), str(action))

    @dbus.service.method(IFACE_DAEMON, in_signature="", out_signature="aa{sv}")
    def GetSeenApps(self) -> list:  # noqa: N802
        """Return [{app_id: s, label_hint: s}] sorted by app_id."""
        return [
            dbus.Dictionary(
                {
                    "app_id": dbus.String(r["app_id"]),
                    "label_hint": dbus.String(r["label_hint"]),
                },
                signature="sv",
            )
            for r in self._seen_apps.list()
        ]

    # ------------------------------------------------------------------
    # im.tincan.Calls — HFP call control (tincan-0e6na / tincan-xohrx)
    # ------------------------------------------------------------------

    def _require_call_setup_ready(self) -> None:
        """Raise NotAvailable if the SELinux HFP module is not in place."""
        if not self._capabilities.get("call_setup_ready", False):
            raise dbus.exceptions.DBusException(
                "HFP call setup not ready — install the tincan SELinux policy module",
                name="org.ofono.Error.NotAvailable",
            )

    @dbus.service.method(IFACE_CALLS, in_signature="s", out_signature="s")
    def Dial(self, number: str) -> str:  # noqa: N802
        self._require_call_setup_ready()
        if self._call_controller is None:
            raise dbus.exceptions.DBusException(
                "oFono not available — install oFono to use call features",
                name="org.freedesktop.DBus.Error.ServiceUnknown",
            )
        try:
            return str(self._call_controller.dial(str(number)))
        except Exception as exc:
            raise dbus.exceptions.DBusException(
                str(exc), name="org.ofono.Error.Failed"
            ) from exc

    @dbus.service.method(IFACE_CALLS, in_signature="s", out_signature="")
    def Answer(self, call_id: str) -> None:  # noqa: N802
        self._require_call_setup_ready()
        if self._call_controller is None:
            raise dbus.exceptions.DBusException(
                "oFono not available — install oFono to use call features",
                name="org.freedesktop.DBus.Error.ServiceUnknown",
            )
        try:
            self._call_controller.answer_call(str(call_id))
        except Exception as exc:
            raise dbus.exceptions.DBusException(
                str(exc), name="org.ofono.Error.Failed"
            ) from exc

    @dbus.service.method(IFACE_CALLS, in_signature="s", out_signature="")
    def Hangup(self, call_id: str) -> None:  # noqa: N802
        self._require_call_setup_ready()
        if self._call_controller is None:
            raise dbus.exceptions.DBusException(
                "oFono not available — install oFono to use call features",
                name="org.freedesktop.DBus.Error.ServiceUnknown",
            )
        try:
            self._call_controller.hangup_call(str(call_id))
        except Exception as exc:
            raise dbus.exceptions.DBusException(
                str(exc), name="org.ofono.Error.Failed"
            ) from exc

    @dbus.service.method(IFACE_CALLS, in_signature="s", out_signature="")
    def SendDtmf(self, key: str) -> None:  # noqa: N802
        self._require_call_setup_ready()
        if self._call_controller is None:
            raise dbus.exceptions.DBusException(
                "oFono not available — install oFono to use call features",
                name="org.freedesktop.DBus.Error.ServiceUnknown",
            )
        key_str = str(key)
        if len(key_str) != 1 or key_str not in "0123456789*#":
            raise dbus.exceptions.DBusException(
                f"Invalid DTMF key {key_str!r}; must be a single char in [0-9*#]",
                name="im.tincan.Error.InvalidArgument",
            )
        try:
            self._call_controller.send_dtmf(key_str)
        except Exception as exc:
            raise dbus.exceptions.DBusException(
                str(exc), name="org.ofono.Error.Failed"
            ) from exc

    @dbus.service.method(IFACE_CALLS, in_signature="", out_signature="a(ssss)")
    def GetCalls(self) -> list:  # noqa: N802
        self._require_call_setup_ready()
        if self._call_controller is None:
            return []
        return [
            (cs.call_id, cs.number, cs.state, cs.direction)
            for cs in self._call_controller.get_calls()
        ]

    @dbus.service.method(IFACE_CALLS, in_signature="", out_signature="")
    def SwapCalls(self) -> None:  # noqa: N802
        self._require_call_setup_ready()
        if self._call_controller is None:
            raise dbus.exceptions.DBusException(
                "oFono not available — install oFono to use call features",
                name="org.freedesktop.DBus.Error.ServiceUnknown",
            )
        try:
            self._call_controller.swap_calls()
        except Exception as exc:
            raise dbus.exceptions.DBusException(
                str(exc), name="org.ofono.Error.Failed"
            ) from exc

    @dbus.service.method(IFACE_CALLS, in_signature="", out_signature="")
    def HoldAndAnswer(self) -> None:  # noqa: N802
        self._require_call_setup_ready()
        if self._call_controller is None:
            raise dbus.exceptions.DBusException(
                "oFono not available — install oFono to use call features",
                name="org.freedesktop.DBus.Error.ServiceUnknown",
            )
        try:
            self._call_controller.hold_and_answer()
        except Exception as exc:
            raise dbus.exceptions.DBusException(
                str(exc), name="org.ofono.Error.Failed"
            ) from exc

    @dbus.service.method(IFACE_CALLS, in_signature="", out_signature="")
    def ReleaseAndAnswer(self) -> None:  # noqa: N802
        self._require_call_setup_ready()
        if self._call_controller is None:
            raise dbus.exceptions.DBusException(
                "oFono not available — install oFono to use call features",
                name="org.freedesktop.DBus.Error.ServiceUnknown",
            )
        try:
            self._call_controller.release_and_answer()
        except Exception as exc:
            raise dbus.exceptions.DBusException(
                str(exc), name="org.ofono.Error.Failed"
            ) from exc

    @dbus.service.signal(IFACE_CALLS, signature="ss")
    def IncomingCall(self, caller_name: str, caller_number: str) -> None:  # noqa: N802
        pass

    @dbus.service.signal(IFACE_CALLS, signature="")
    def CallConnected(self) -> None:  # noqa: N802
        pass

    @dbus.service.signal(IFACE_CALLS, signature="")
    def CallEnded(self) -> None:  # noqa: N802
        pass

    @dbus.service.signal(IFACE_CALLS, signature="s")
    def AudioError(self, reason: str) -> None:  # noqa: N802
        pass

    @dbus.service.signal(IFACE_CALLS, signature="")
    def AudioRestored(self) -> None:  # noqa: N802
        pass

    @dbus.service.signal(IFACE_CALLS, signature="sss")
    def CallWaiting(self, call_id: str, number: str, name: str) -> None:  # noqa: N802
        pass

    @dbus.service.signal(IFACE_CALLS, signature="ss")
    def CallHeld(self, call_id: str, number: str) -> None:  # noqa: N802
        pass

    @dbus.service.signal(IFACE_CALLS, signature="ss")
    def CallActive(self, call_id: str, number: str) -> None:  # noqa: N802
        pass

    @dbus.service.signal(IFACE_CALLS, signature="s")
    def CallRemoved(self, call_id: str) -> None:  # noqa: N802
        pass

    def on_call_incoming(self, caller_name: str, caller_number: str) -> None:
        """Called by CallController when an incoming call arrives."""
        _log.info("IncomingCall: %s <%s>", caller_name, caller_number)
        self.IncomingCall(str(caller_name), str(caller_number))

    def on_call_connected(self) -> None:
        """Called by CallController when a call transitions to active."""
        _log.info("CallConnected")
        self.CallConnected()

    def on_call_ended(self) -> None:
        """Called by CallController when a call is terminated."""
        _log.info("CallEnded")
        self.CallEnded()

    def on_audio_error(self, reason: str) -> None:
        """Called by CallController when SCO audio fails to establish."""
        _log.warning("AudioError: %s", reason)
        self.AudioError(str(reason))

    def on_audio_restored(self) -> None:
        """Called by CallController when SCO audio recovers after an error."""
        _log.info("AudioRestored")
        self.AudioRestored()

    def on_call_active(self, call_id: str, number: str) -> None:
        """Called by CallController before on_call_connected when call goes active."""
        _log.info("CallActive: %s", call_id)
        self.CallActive(str(call_id), str(number))

    def on_call_held(self, call_id: str, number: str) -> None:
        """Called by CallController when a call is placed on hold."""
        _log.info("CallHeld: %s", call_id)
        self.CallHeld(str(call_id), str(number))

    def on_call_waiting(self, call_id: str, number: str, name: str) -> None:
        """Called by CallController when a second call arrives while one is active."""
        _log.info("CallWaiting: %s", call_id)
        self.CallWaiting(str(call_id), str(number), str(name))

    def on_call_removed(self, call_id: str) -> None:
        """Called by CallController when a specific call is removed."""
        _log.info("CallRemoved: %s", call_id)
        self.CallRemoved(str(call_id))

    def on_app_notification_received(self, notif: dict) -> None:
        """Handle a non-SMS iOS app notification from the ANCS backend.

        Applies the filter, registers the app in SeenAppsRegistry, then
        emits AppNotificationReceived with a normalized 7-key payload.
        """
        app_id = str(notif.get("app_id", ""))
        if not self._notification_filter.is_enabled():
            _log.debug("app mirroring disabled — skipping %s", app_id)
            return
        if not self._notification_filter.is_allowed(app_id):
            _log.debug("app %s denied — skipping", app_id)
            return
        title = str(notif.get("title", ""))
        self._seen_apps.register(app_id, label_hint=title)
        try:
            category_id = int(notif.get("category_id", 0))
        except (TypeError, ValueError):
            category_id = 0
        try:
            event_flags = int(notif.get("event_flags", 0))
        except (TypeError, ValueError):
            event_flags = 0
        payload = dbus.Dictionary(
            {
                "app_id": dbus.String(app_id),
                "title": dbus.String(title),
                "subtitle": dbus.String(str(notif.get("subtitle", ""))),
                "body": dbus.String(str(notif.get("body", ""))),
                "category": dbus.String(str(notif.get("category", ""))),
                "category_id": dbus.UInt32(category_id),
                "event_flags": dbus.UInt32(event_flags),
            },
            signature="sv",
        )
        self.AppNotificationReceived(payload)

    # ------------------------------------------------------------------
    # Internal helpers called by Bluetooth adapters
    # ------------------------------------------------------------------

    def register_backend(self, backend: object) -> None:
        """Wire a backend so SendMessage/SendMessageToRecipients can call send_group_message."""
        self._backend = backend

    def set_call_controller(self, controller: object) -> None:
        """Wire the CallController so im.tincan.Calls methods can dispatch to oFono."""
        self._call_controller = controller

    def upsert_conversation(self, conv: Conversation) -> None:
        """Add or replace a conversation in the in-memory store."""
        self._conversations[conv.id] = conv
        if conv.is_group and conv.participants:
            self._group_participants[conv.id] = list(conv.participants)

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
                "attachments": str(message.get("attachments", "[]")),
            })

        if conv_id in self._conversations:
            conv = self._conversations[conv_id]
            if not conv.last_message_at or timestamp >= conv.last_message_at:
                conv.last_message_at = timestamp
                conv.last_message_preview = body  # GUI owns truncation
                conv.last_message_direction = direction
            if direction == "inbound" and status == "unread":
                conv.unread_count += 1
            updated_conv = conv.to_dbus()
        else:
            # Unknown conv_id: emit MessageReceived but skip ConversationUpdated.
            # MAP adapters must call upsert_conversation() before delivering messages
            # so the daemon always has a Conversation object to update (review F4).
            updated_conv = None

        def _to_dbus_value(v: object) -> object:
            if isinstance(v, bool):
                return dbus.Boolean(v)
            if isinstance(v, list):
                return dbus.Array([dbus.String(str(i)) for i in v], signature="s")
            return dbus.String(str(v))

        msg_dbus = dbus.Dictionary(
            {k: _to_dbus_value(v) for k, v in message.items()},
            signature="sv",
        )
        self.MessageReceived(msg_dbus)
        if updated_conv is not None:
            self.ConversationUpdated(updated_conv)

    def update_contact(self, phone: str, name: str) -> None:
        """Store a resolved contact name, update phone-keyed convs, and merge name-keyed ones."""
        normalized = normalize_phone(phone)
        self._contact_store.upsert(normalized, name)
        for conv in list(self._conversations.values()):
            if normalize_phone(conv.id) == normalized:
                conv.display_name = name
                self.upsert_conversation(conv)
                self.ConversationUpdated(conv.to_dbus())

        # Merge any conversation keyed by display name into the phone-keyed slot.
        name_lower = name.lower()
        for old_id in [cid for cid in list(self._conversations) if cid.lower() == name_lower]:
            old_conv = self._conversations.pop(old_id)

            # Migrate messages and re-key dedup set.
            old_msgs = self._messages.pop(old_id, [])
            for msg in old_msgs:
                msg["conversation_id"] = normalized
            self._messages.setdefault(normalized, []).extend(old_msgs)
            stale = {k for k in self._message_keys if k[0] == old_id}
            self._message_keys -= stale
            self._message_keys.update((normalized, k[1], k[2]) for k in stale)

            if normalized in self._conversations:
                existing = self._conversations[normalized]
                if old_conv.last_message_at > existing.last_message_at:
                    existing.last_message_at = old_conv.last_message_at
                    existing.last_message_preview = old_conv.last_message_preview
                    existing.last_message_direction = old_conv.last_message_direction
                existing.unread_count += old_conv.unread_count
                self.ConversationUpdated(existing.to_dbus())
            else:
                new_conv = Conversation(
                    id=normalized,
                    display_name=name,
                    participants=[normalized],
                    last_message_at=old_conv.last_message_at,
                    last_message_preview=old_conv.last_message_preview,
                    last_message_direction=old_conv.last_message_direction,
                    unread_count=old_conv.unread_count,
                )
                self.upsert_conversation(new_conv)
                self.ConversationUpdated(new_conv.to_dbus())

    def deliver_contact_photo(self, phone: str, photo: bytes | None) -> None:
        """Store a contact photo and emit ContactPhotoReceived for matching conversations."""
        normalized = normalize_phone(phone)
        self._contact_store.set_photo(normalized, photo)
        photo_bytes = dbus.Array(photo or b"", signature="y")
        for conv in self._conversations.values():
            if normalize_phone(conv.id) == normalized:
                self.ContactPhotoReceived(conv.id, photo_bytes)
