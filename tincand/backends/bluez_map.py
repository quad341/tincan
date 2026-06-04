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
import os
import re
import tempfile
import time

import dbus
from gi.repository import GLib

from tincand.backends.base import BackendInterface
from tincand.dbus_service import Conversation

_log = logging.getLogger(__name__)

_OBEX_CLIENT = "org.bluez.obex"
_OBEX_CLIENT_IFACE = "org.bluez.obex.Client1"
_OBEX_CLIENT_PATH = "/org/bluez/obex"
_MAP_ACCESS_IFACE = "org.bluez.obex.MessageAccess1"
_TRANSFER_IFACE = "org.bluez.obex.Transfer1"
_PROPS_IFACE = "org.freedesktop.DBus.Properties"
_OBJ_MANAGER_IFACE = "org.freedesktop.DBus.ObjectManager"
_BLUEZ_SERVICE = "org.bluez"
_BLUEZ_ROOT = "/"
_DEVICE_IFACE = "org.bluez.Device1"

_FORBIDDEN_ERRORS = {
    "org.openobex.Error.Forbidden",
    "org.bluez.obex.Error.Forbidden",
}
_TRANSIENT_ERRORS = {"org.bluez.obex.Error.Failed"}

_TRANSFER_TIMEOUT = 15.0
_RETRY_MAX = 3
_RETRY_BACKOFF = 0.5
_POLL_INTERVAL_SECONDS = 5
_RECONNECT_INTERVAL_SECONDS = 10

# UpdateInbox raising UnknownObject means the OBEX session object is gone — dead session.
# Contrast: UnknownMethod from GetMessage is a BlueZ API gap (tincan-ixqg) — handled by
# _fetch_full_body's _failed_handles cache, never propagates to _poll_tick.
_DEAD_SESSION_ERRORS = frozenset({"org.freedesktop.DBus.Error.UnknownObject"})


class ConsentRequired(Exception):
    """Raised when iOS has not yet granted MAP access (OBEX 0x43 Forbidden).

    The caller should prompt the user to enable 'Show Notifications' on the
    iPhone, then retry connect().
    """


class SendFailed(Exception):
    """Raised when a MAP PushMessage transfer ends in an error state."""


def build_bmsg(to_number: str, body: str) -> str:
    """Return a bMessage-format string for *body* addressed to *to_number*.

    LENGTH is the byte length of the BEGIN:MSG…END:MSG block encoded as
    UTF-8, so multi-byte characters (accented letters, emoji) count correctly.
    """
    msg_block = f"BEGIN:MSG\r\n{body}\r\nEND:MSG\r\n"
    length = len(msg_block.encode("utf-8"))
    return (
        "BEGIN:BMSG\r\n"
        "VERSION:1.0\r\n"
        "STATUS:UNREAD\r\n"
        "TYPE:SMS_GSM\r\n"
        "FOLDER:telecom/msg/outbox\r\n"
        "BEGIN:VCARD\r\n"
        "VERSION:2.1\r\n"
        "N:;\r\n"
        "TEL:\r\n"
        "END:VCARD\r\n"
        "BEGIN:BENV\r\n"
        # Recipient vCard carries N: for vCard 2.1 correctness. (Live testing
        # showed iOS delivers with or without it — the real send blocker was a
        # missing MAP folder reset in send_message, not the bMessage format.)
        "BEGIN:VCARD\r\n"
        "VERSION:2.1\r\n"
        f"N:;{to_number}\r\n"
        f"TEL:{to_number}\r\n"
        "END:VCARD\r\n"
        "BEGIN:BBODY\r\n"
        "CHARSET:UTF-8\r\n"
        f"LENGTH:{length}\r\n"
        f"{msg_block}"
        "END:BBODY\r\n"
        "END:BENV\r\n"
        "END:BMSG\r\n"
    )


def _parse_bmsg_body(bmsg: str) -> str:
    """Extract body text from a bMessage string."""
    match = re.search(r"BEGIN:MSG\r?\n(.*?)\r?\nEND:MSG", bmsg, re.DOTALL)
    return match.group(1) if match else ""


_NON_DIGIT_RE = re.compile(r"\D")


def _norm_phone(s: str) -> str:
    """Return a canonical conversation key from *s*.

    Strips formatting characters and returns the last 10 digits when *s*
    looks like a phone number (≥7 digits after stripping). Falls back to *s*
    unchanged when the digit count is too low (e.g. a contact display name).
    This merges threads that differ only by country-code prefix or formatting
    ("+15555550123" == "5555550123" == "(555) 555-0123").
    """
    digits = _NON_DIGIT_RE.sub("", s)
    if len(digits) >= 7:
        return digits[-10:] if len(digits) > 10 else digits
    return s


def _parse_map_datetime(dt: str) -> str:
    """Convert MAP Datetime 'YYYYMMDDTHHMMSS[±HHMM]' to 'HH:MM' for GUI display.

    Returns '' when dt is empty or does not contain a time component (e.g. date-only
    strings from test fixtures, or missing Datetime from the phone's MAP server).
    """
    if not dt:
        return ""
    t = dt.find("T")
    if t < 0 or len(dt) < t + 5:
        return ""
    time_part = dt[t + 1:]
    if len(time_part) >= 4:
        return f"{time_part[:2]}:{time_part[2:4]}"
    return ""


class MapBackend(BackendInterface):
    """MAP backend using obexd org.bluez.obex.Client1."""

    def __init__(self) -> None:
        self._service: object | None = None
        self._session_path: str | None = None
        self._msg_access: object | None = None
        self._poll_source_id: int | None = None
        self._reconnect_source_id: int | None = None
        self._device_addr: str = ""
        self._device_name: str = ""
        self._seen_handles: set[str] = set()  # handles seen on initial poll — skip notifications
        self._initial_poll_done: bool = False
        self._failed_handles: set[str] = set()  # handles where GetMessage raised; skip on retry
        # display_name.lower() → phone; populated from phone-keyed messages, persists across polls
        self._name_to_phone: dict[str, str] = {}

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
        self._device_addr = device_addr
        # Cancel any pending reconnect timer so it doesn't race this explicit connect.
        if self._reconnect_source_id is not None:
            GLib.source_remove(self._reconnect_source_id)
            self._reconnect_source_id = None
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
        self._msg_access = dbus.Interface(
            bus.get_object(_OBEX_CLIENT, self._session_path),
            _MAP_ACCESS_IFACE,
        )
        _log.info("MAP session established: %s → %s", device_addr, self._session_path)

        self._device_name = self._resolve_device_name(device_addr)
        self._seen_handles.clear()
        self._initial_poll_done = False
        self._failed_handles.clear()
        self._name_to_phone.clear()

        if self._service is not None:
            self._service.Connect(device_addr)  # type: ignore[attr-defined]
            self._service.set_device_name(self._device_name)  # type: ignore[attr-defined]
            self._service.set_capability("messages", True)  # type: ignore[attr-defined]

        self._poll_source_id = GLib.timeout_add_seconds(_POLL_INTERVAL_SECONDS, self._poll_tick)

    def disconnect(self) -> None:
        """Remove the obexd MAP session; silently no-ops if not connected."""
        if self._reconnect_source_id is not None:
            GLib.source_remove(self._reconnect_source_id)
            self._reconnect_source_id = None
        if self._poll_source_id is not None:
            GLib.source_remove(self._poll_source_id)
            self._poll_source_id = None
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
            self._msg_access = None
            self._device_name = ""
            if self._service is not None:
                self._service.set_capability("messages", False)  # type: ignore[attr-defined]
                self._service.Disconnect()  # type: ignore[attr-defined]

    def poll_inbox(self) -> list:
        """Poll MAP inbox + sent folders and emit D-Bus signals for messages.

        Navigates to telecom/msg, then lists inbox (inbound) and sent (outbound).
        Body is fetched via GetMessage transfer; Subject is used as fallback.
        Conversation key is SenderAddressing (normalised phone number).
        """
        if self._msg_access is None:
            return []

        self._retry(self._msg_access.UpdateInbox)

        # Navigate to telecom/msg from whatever the current folder is.
        for _ in range(2):
            try:
                self._msg_access.SetFolder("")
            except dbus.exceptions.DBusException:
                pass
        self._retry(self._msg_access.SetFolder, "telecom")
        self._retry(self._msg_access.SetFolder, "msg")

        parsed: list[dict] = []

        inbox_raw = self._retry(self._msg_access.ListMessages, "inbox", {})
        _first_inbox = True
        for msg_path, props in inbox_raw.items():
            if _first_inbox:
                _log.debug(
                    "MAP inbox props (first message) — raw keys: %s",
                    {str(k): str(v) for k, v in props.items()},
                )
                _first_inbox = False
            body = (
                self._fetch_full_body(str(msg_path))
                or str(props.get("Subject", "")).strip()
                or "New message"
            )
            phone = str(props.get("SenderAddressing", props.get("Sender", "")))
            display_name = str(props.get("Sender", phone))
            raw_dt = str(
                props.get("Datetime", "")
                or props.get("DateTime", "")
                or props.get("Date", "")
            )
            parsed.append({
                "path": str(msg_path),
                "sender": phone,
                "display_name": display_name,
                "timestamp": _parse_map_datetime(raw_dt),
                "read": bool(props.get("Read", False)),
                "body": body,
                "direction": "inbound",
            })

        try:
            sent_raw = self._retry(self._msg_access.ListMessages, "sent", {})
            _first_sent = True
            for msg_path, props in sent_raw.items():
                if _first_sent:
                    _log.debug(
                        "MAP sent props (first message) — raw keys: %s",
                        {str(k): str(v) for k, v in props.items()},
                    )
                    _first_sent = False
                body = (
                    self._fetch_full_body(str(msg_path))
                    or str(props.get("Subject", "")).strip()
                    or ""
                )
                phone = str(props.get("RecipientAddressing", props.get("Recipient", "")))
                display_name = str(props.get("Recipient", phone))
                raw_dt = str(
                    props.get("Datetime", "")
                    or props.get("DateTime", "")
                    or props.get("Date", "")
                )
                parsed.append({
                    "path": str(msg_path),
                    "sender": phone,
                    "display_name": display_name,
                    "timestamp": _parse_map_datetime(raw_dt),
                    "read": True,
                    "body": body,
                    "direction": "outbound",
                })
        except dbus.exceptions.DBusException as exc:
            _log.debug("sent folder unavailable: %s", exc)

        if parsed and self._service is not None:
            if not self._initial_poll_done:
                # Seed the seen-handles baseline so historical messages don't replay
                # as notifications or inflate the unread badge.
                for msg in parsed:
                    self._seen_handles.add(msg["path"])
                self._initial_poll_done = True
                # Still upsert conversations for list display, but skip signals.
                self._emit_messages(parsed, notify=False)
            else:
                new_msgs = [m for m in parsed if m["path"] not in self._seen_handles]
                for msg in new_msgs:
                    self._seen_handles.add(msg["path"])
                if new_msgs:
                    self._emit_messages(new_msgs, notify=True)

        return parsed

    def get_message(self, handle: str) -> object:
        """Fetch a MAP message by handle — returns parsed body string or None."""
        return self._fetch_full_body(handle)

    def send_message(self, to: str, body: str) -> str:
        """Build a bMessage, push via PushMessage, and watch the transfer.

        Returns the transfer object path on success.
        Raises SendFailed if the transfer ends in an error state.
        """
        if self._msg_access is None:
            raise RuntimeError("Not connected — call connect() first")

        bmsg_content = build_bmsg(to, body)
        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".bmsg", delete=False, encoding="utf-8"
            ) as f:
                f.write(bmsg_content)
                tmp_path = f.name

            # Reset to the MAP root before navigating. A prior poll or send may
            # have left the current folder at telecom/msg; without this reset the
            # relative SetFolder("telecom") fails with obexd Error.Failed
            # ("Internal Server Error") and the send aborts. poll_inbox resets the
            # same way — sends were failing intermittently right after a poll.
            for _ in range(2):
                try:
                    self._msg_access.SetFolder("")
                except dbus.exceptions.DBusException:
                    pass
            self._retry(self._msg_access.SetFolder, "telecom")
            self._retry(self._msg_access.SetFolder, "msg")
            result = self._retry(self._msg_access.PushMessage, tmp_path, "outbox", {})
            transfer_path, _ = result  # PushMessage returns (object_path, properties)
            self._wait_transfer_send(str(transfer_path))
            _log.info("MAP send complete: to=%s transfer=%s", to, transfer_path)
            return str(transfer_path)
        finally:
            if tmp_path is not None:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_device_name(self, device_addr: str) -> str:
        """Return BlueZ Device1.Alias for device_addr, or device_addr if lookup fails."""
        try:
            sys_bus = dbus.SystemBus()
            obj_mgr = dbus.Interface(
                sys_bus.get_object(_BLUEZ_SERVICE, _BLUEZ_ROOT),
                _OBJ_MANAGER_IFACE,
            )
            for _path, interfaces in obj_mgr.GetManagedObjects().items():
                dev = interfaces.get(_DEVICE_IFACE, {})
                if str(dev.get("Address", "")) == device_addr:
                    alias = str(dev.get("Alias", ""))
                    return alias if alias else device_addr
        except dbus.exceptions.DBusException as exc:
            _log.debug("Could not resolve device name for %s: %s", device_addr, exc)
        return device_addr

    def _poll_tick(self) -> bool:
        """GLib timer callback — poll inbox; detect dead session and trigger recovery."""
        try:
            self.poll_inbox()
        except dbus.exceptions.DBusException as exc:
            if exc.get_dbus_name() in _DEAD_SESSION_ERRORS:
                _log.warning("MAP session object gone — recovering: %s", exc)
                self._handle_session_dead()
                return GLib.SOURCE_REMOVE
            _log.warning("poll_inbox error: %s", exc)
        except Exception as exc:
            _log.warning("poll_inbox error: %s", exc)
        return GLib.SOURCE_CONTINUE

    def _handle_session_dead(self) -> None:
        """Tear down a dead OBEX session and schedule reconnect attempts."""
        # Nullify poll ID before disconnect() so it skips the source_remove call —
        # GLib removes it when we return SOURCE_REMOVE from _poll_tick.
        self._poll_source_id = None
        self.disconnect()
        if self._device_addr:
            self._reconnect_source_id = GLib.timeout_add_seconds(
                _RECONNECT_INTERVAL_SECONDS, self._reconnect_tick
            )

    def _reconnect_tick(self) -> bool:
        """GLib timer callback — attempt to re-establish the MAP session."""
        if not self._device_addr:
            self._reconnect_source_id = None
            return GLib.SOURCE_REMOVE
        try:
            self.connect(self._device_addr)
            _log.info("MAP session reconnected to %s", self._device_addr)
            self._reconnect_source_id = None
            return GLib.SOURCE_REMOVE
        except Exception as exc:
            _log.debug("MAP reconnect attempt failed (will retry): %s", exc)
            return GLib.SOURCE_CONTINUE

    def _retry(self, fn: object, *args: object) -> object:
        """Call *fn(*args)*, retrying on transient obexd errors."""
        for attempt in range(_RETRY_MAX):
            try:
                return fn(*args)  # type: ignore[operator]
            except dbus.exceptions.DBusException as exc:
                if exc.get_dbus_name() in _TRANSIENT_ERRORS and attempt < _RETRY_MAX - 1:
                    _log.debug("Transient obexd error (attempt %d): %s", attempt + 1, exc)
                    time.sleep(_RETRY_BACKOFF)
                    continue
                raise
        return None  # unreachable, satisfies type checker

    def _fetch_full_body(self, msg_path: str) -> str | None:
        """GetMessage for *msg_path*, wait for transfer, return parsed body."""
        if self._msg_access is None:
            return None
        if msg_path in self._failed_handles:
            return None
        try:
            result = self._retry(
                self._msg_access.GetMessage,
                msg_path,
                "",  # targetfile: empty = obexd picks temp location
                dbus.Dictionary({"Attachment": dbus.Boolean(False)}, signature="sv"),
            )
            if result is None:
                return None
            transfer_path, _ = result
            return self._wait_transfer_recv(str(transfer_path))
        except dbus.exceptions.DBusException as exc:
            _log.warning("GetMessage failed for %s: %s", msg_path, exc)
            self._failed_handles.add(msg_path)
            return None

    def _wait_transfer_recv(self, transfer_path: str) -> str | None:
        """Poll Transfer1.Status until complete; read and return bMessage body."""
        bus = dbus.SessionBus()
        props = dbus.Interface(
            bus.get_object(_OBEX_CLIENT, transfer_path),
            _PROPS_IFACE,
        )
        deadline = time.monotonic() + _TRANSFER_TIMEOUT
        while time.monotonic() < deadline:
            status = str(props.Get(_TRANSFER_IFACE, "Status"))
            if status == "complete":
                filename = str(props.Get(_TRANSFER_IFACE, "Filename"))
                try:
                    with open(filename, encoding="utf-8") as f:
                        return _parse_bmsg_body(f.read())
                finally:
                    try:
                        os.unlink(filename)
                    except OSError:
                        pass
            if status == "error":
                _log.warning("Transfer recv failed: %s", transfer_path)
                return None
            time.sleep(0.05)
        _log.warning("Transfer recv timed out: %s", transfer_path)
        return None

    def _wait_transfer_send(self, transfer_path: str) -> None:
        """Poll Transfer1.Status for a PushMessage transfer; raise SendFailed on error.

        obexd removes the transfer object immediately after completion, so an
        UnknownObject/ServiceUnknown DBusException after seeing 'queued'/'active'
        is treated as complete rather than an error.
        """
        _OBJECT_GONE = {
            "org.freedesktop.DBus.Error.UnknownObject",
            "org.freedesktop.DBus.Error.ServiceUnknown",
        }
        bus = dbus.SessionBus()
        props = dbus.Interface(
            bus.get_object(_OBEX_CLIENT, transfer_path),
            _PROPS_IFACE,
        )
        deadline = time.monotonic() + _TRANSFER_TIMEOUT
        while time.monotonic() < deadline:
            try:
                status = str(props.Get(_TRANSFER_IFACE, "Status"))
            except dbus.exceptions.DBusException as exc:
                if exc.get_dbus_name() in _OBJECT_GONE:
                    _log.debug("MAP send transfer vanished (completed): %s", transfer_path)
                    return
                raise SendFailed(f"Transfer status query failed: {exc}") from exc
            _log.debug("MAP send transfer %s: status=%s", transfer_path, status)
            if status == "complete":
                return
            if status not in ("queued", "active"):
                raise SendFailed(
                    f"PushMessage transfer ended in unexpected state {status!r}: {transfer_path}"
                )
            time.sleep(0.05)
        raise SendFailed(f"PushMessage transfer timed out: {transfer_path}")

    def _emit_messages(self, messages: list[dict], *, notify: bool = True) -> None:
        """Group *messages* by sender (phone number) and drive TincanService callbacks.

        When notify=False (initial-poll baseline), messages are stored and conversations
        upserted but status is forced to 'read' so no unread count increment or desktop
        notification fires.
        """
        svc = self._service
        if svc is None:
            return

        by_sender: dict[str, list[dict]] = {}
        for msg in messages:
            key = _norm_phone(msg["sender"])
            by_sender.setdefault(key, []).append(msg)

        # Build phone → display_name for phone-keyed groups so name-keyed groups
        # (SenderAddressing absent/non-numeric) can resolve a send_target.
        # Also persist mappings in _name_to_phone so subsequent polls can still
        # resolve names even when no phone-keyed messages appear in the new batch.
        phone_by_display: dict[str, str] = {}
        for key, msgs in by_sender.items():
            if len(_NON_DIGIT_RE.sub("", key)) >= 7:
                latest_dn = (max(msgs, key=lambda m: m["timestamp"] or "")
                             .get("display_name", key) or key)
                phone_by_display[latest_dn.lower()] = key
                self._name_to_phone[latest_dn.lower()] = key

        for sender, msgs in by_sender.items():
            unread = sum(1 for m in msgs if not m["read"]) if notify else 0
            latest = max(msgs, key=lambda m: m["timestamp"] or "")
            display_name = latest.get("display_name", sender) or sender
            is_phone_key = len(_NON_DIGIT_RE.sub("", sender)) >= 7
            dn_lower = display_name.lower()
            send_target = sender if is_phone_key else (
                phone_by_display.get(dn_lower) or self._name_to_phone.get(dn_lower, "")
            )
            conv = Conversation(
                id=sender,
                display_name=display_name,
                participants=[sender],
                last_message_at=latest["timestamp"],
                last_message_preview=latest["body"],
                unread_count=unread,
                send_target=send_target,
            )
            svc.upsert_conversation(conv)  # type: ignore[attr-defined]
            for msg in msgs:
                svc.on_message_received(  # type: ignore[attr-defined]
                    {
                        "conversation_id": sender,
                        "body": msg["body"],
                        "timestamp": msg["timestamp"],
                        "direction": msg["direction"],
                        "status": "read" if (not notify or msg["read"]) else "unread",
                        "from": sender,
                    }
                )
