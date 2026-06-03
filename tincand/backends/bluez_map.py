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
_POLL_INTERVAL_SECONDS = 30


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
        "BEGIN:BENV\r\n"
        "BEGIN:VCARD\r\n"
        "VERSION:3.0\r\n"
        f"TEL;TYPE=CELL:{to_number}\r\n"
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


class MapBackend(BackendInterface):
    """MAP backend using obexd org.bluez.obex.Client1."""

    def __init__(self) -> None:
        self._service: object | None = None
        self._session_path: str | None = None
        self._msg_access: object | None = None
        self._poll_source_id: int | None = None
        self._device_name: str = ""

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
        self._msg_access = dbus.Interface(
            bus.get_object(_OBEX_CLIENT, self._session_path),
            _MAP_ACCESS_IFACE,
        )
        _log.info("MAP session established: %s → %s", device_addr, self._session_path)

        self._device_name = self._resolve_device_name(device_addr)

        if self._service is not None:
            self._service.Connect(device_addr)  # type: ignore[attr-defined]
            self._service.set_device_name(self._device_name)  # type: ignore[attr-defined]
            self._service.set_capability("messages", True)  # type: ignore[attr-defined]

        self._poll_source_id = GLib.timeout_add_seconds(_POLL_INTERVAL_SECONDS, self._poll_tick)

    def disconnect(self) -> None:
        """Remove the obexd MAP session; silently no-ops if not connected."""
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
        for msg_path, props in inbox_raw.items():
            body = (
                self._fetch_full_body(str(msg_path))
                or str(props.get("Subject", "")).strip()
                or "New message"
            )
            phone = str(props.get("SenderAddressing", props.get("Sender", "")))
            display_name = str(props.get("Sender", phone))
            parsed.append({
                "path": str(msg_path),
                "sender": phone,
                "display_name": display_name,
                "timestamp": str(props.get("Datetime", "")),
                "read": bool(props.get("Read", False)),
                "body": body,
                "direction": "inbound",
            })

        try:
            sent_raw = self._retry(self._msg_access.ListMessages, "sent", {})
            for msg_path, props in sent_raw.items():
                body = (
                    self._fetch_full_body(str(msg_path))
                    or str(props.get("Subject", "")).strip()
                    or ""
                )
                phone = str(props.get("RecipientAddressing", props.get("Recipient", "")))
                display_name = str(props.get("Recipient", phone))
                parsed.append({
                    "path": str(msg_path),
                    "sender": phone,
                    "display_name": display_name,
                    "timestamp": str(props.get("Datetime", "")),
                    "read": True,
                    "body": body,
                    "direction": "outbound",
                })
        except dbus.exceptions.DBusException as exc:
            _log.debug("sent folder unavailable: %s", exc)

        if parsed and self._service is not None:
            self._emit_messages(parsed)

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

            transfer_path = self._retry(self._msg_access.PushMessage, tmp_path, "outbox", {})
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
        """GLib timer callback — poll inbox and return SOURCE_CONTINUE."""
        try:
            self.poll_inbox()
        except Exception as exc:
            _log.warning("poll_inbox error: %s", exc)
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
        try:
            result = self._retry(
                self._msg_access.GetMessage,
                msg_path,
                "",  # targetfile: empty = obexd picks temp location
                {"Attachment": dbus.Boolean(False)},
            )
            if result is None:
                return None
            transfer_path, _ = result
            return self._wait_transfer_recv(str(transfer_path))
        except dbus.exceptions.DBusException as exc:
            _log.warning("GetMessage failed for %s: %s", msg_path, exc)
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
        """Poll Transfer1.Status for a PushMessage transfer; raise SendFailed on error."""
        bus = dbus.SessionBus()
        props = dbus.Interface(
            bus.get_object(_OBEX_CLIENT, transfer_path),
            _PROPS_IFACE,
        )
        deadline = time.monotonic() + _TRANSFER_TIMEOUT
        while time.monotonic() < deadline:
            status = str(props.Get(_TRANSFER_IFACE, "Status"))
            if status == "complete":
                return
            if status not in ("queued", "active"):
                raise SendFailed(
                    f"PushMessage transfer ended in unexpected state {status!r}: {transfer_path}"
                )
            time.sleep(0.05)
        raise SendFailed(f"PushMessage transfer timed out: {transfer_path}")

    def _emit_messages(self, messages: list[dict]) -> None:
        """Group *messages* by sender (phone number) and drive TincanService callbacks."""
        svc = self._service
        if svc is None:
            return

        by_sender: dict[str, list[dict]] = {}
        for msg in messages:
            by_sender.setdefault(msg["sender"], []).append(msg)

        for sender, msgs in by_sender.items():
            unread = sum(1 for m in msgs if not m["read"])
            latest = max(msgs, key=lambda m: m["timestamp"])
            display_name = latest.get("display_name", sender) or sender
            conv = Conversation(
                id=sender,
                display_name=display_name,
                participants=[sender],
                last_message_at=latest["timestamp"],
                last_message_preview=latest["body"],
                unread_count=unread,
            )
            svc.upsert_conversation(conv)  # type: ignore[attr-defined]
            for msg in msgs:
                svc.on_message_received(  # type: ignore[attr-defined]
                    {
                        "conversation_id": sender,
                        "body": msg["body"],
                        "timestamp": msg["timestamp"],
                        "direction": msg["direction"],
                        "status": "unread" if not msg["read"] else "read",
                        "from": sender,
                    }
                )
