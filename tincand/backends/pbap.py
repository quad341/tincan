"""PBAPContactSync — Phase 1: bulk name sync via PullAll.

Creates a PBAP session, downloads the phonebook as vCard 2.1, and calls
TincanService.update_contact() for every contact with a name and number.
"""
from __future__ import annotations

import logging
import os
import tempfile
from typing import TYPE_CHECKING, Callable

import dbus
import vobject
from gi.repository import GLib

from tincand.contact_store import normalize_phone

if TYPE_CHECKING:
    from tincand.dbus_service import TincanService

_log = logging.getLogger(__name__)

_OBEX_CLIENT = "org.bluez.obex"
_OBEX_CLIENT_IFACE = "org.bluez.obex.Client1"
_OBEX_CLIENT_PATH = "/org/bluez/obex"
_PBAP_ACCESS_IFACE = "org.bluez.obex.PhonebookAccess1"
_TRANSFER_IFACE = "org.bluez.obex.Transfer1"
_PROPS_IFACE = "org.freedesktop.DBus.Properties"

_POLL_INTERVAL_MS = 500
_MAX_RETRIES = 3
_RETRY_DELAY_S = 5


class PBAPContactSync:
    """PBAP Phase-1: pull all contact names into TincanService via PullAll."""

    def __init__(self, service: "TincanService") -> None:
        self._service = service
        self._store = service._contact_store
        self.session_path: str | None = None
        self._pbap_iface: object | None = None
        self._device_addr: str | None = None
        self._retry_count: int = 0

    def connect(self, device_addr: str) -> None:
        """Create PBAP session, run PullAll, parse vCards, update service contacts."""
        self._device_addr = device_addr
        self._retry_count = 0
        self._do_connect()

    def _do_connect(self) -> None:
        """Open PBAP session and start PullAll — used by connect() and retries."""
        device_addr = self._device_addr
        if device_addr is None:
            return
        try:
            bus = dbus.SessionBus()
            client = dbus.Interface(
                bus.get_object(_OBEX_CLIENT, _OBEX_CLIENT_PATH),
                _OBEX_CLIENT_IFACE,
            )
            self.session_path = str(client.CreateSession(
                device_addr,
                {"Target": dbus.String("pbap")},
            ))
            pbap = dbus.Interface(
                bus.get_object(_OBEX_CLIENT, self.session_path),
                _PBAP_ACCESS_IFACE,
            )
            self._pbap_iface = pbap
            # PBAP 1.1+ (iOS) uses "telecom/pb"; PBAP 1.0 uses "pb".
            _selected = False
            for _pb_path in ("telecom/pb", "pb"):
                try:
                    pbap.Select("int", _pb_path)
                    _log.debug("PBAP: selected phonebook int/%s", _pb_path)
                    _selected = True
                    break
                except dbus.exceptions.DBusException as exc:
                    _log.debug("PBAP: Select('int', '%s') failed: %s", _pb_path, exc)
            if not _selected:
                _log.warning("PBAP: could not select any phonebook — aborting contact sync")
                return

            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".vcf", delete=False, encoding="utf-8"
            )
            tmp_path = tmp.name
            tmp.close()

            # Request vCard 2.1 without field filtering: 'Fields'/'PropertySelector'
            # syntax varies by implementation; omitting it returns all fields safely.
            result = pbap.PullAll(
                tmp_path,
                {"Format": dbus.String("vcard21")},
            )
            transfer_path = str(result[0]) if isinstance(result, (list, tuple)) else str(result)
            self._wait_transfer(transfer_path, lambda error=False: self._on_pullall_complete(
                tmp_path, error
            ))
        except dbus.exceptions.DBusException as exc:
            _log.warning("PBAP connect failed for %s: %s", device_addr, exc)

    def _retry_pullall(self) -> bool:
        """Re-run PullAll on the stored session — iOS approval-race recovery."""
        if self._pbap_iface is None or self.session_path is None:
            return False
        _log.debug("PBAP PullAll retry %d/%d", self._retry_count, _MAX_RETRIES)
        try:
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".vcf", delete=False, encoding="utf-8"
            )
            tmp_path = tmp.name
            tmp.close()
            result = self._pbap_iface.PullAll(
                tmp_path,
                {"Format": dbus.String("vcard21")},
            )
            transfer_path = str(result[0]) if isinstance(result, (list, tuple)) else str(result)
            self._wait_transfer(transfer_path, lambda error=False: self._on_pullall_complete(
                tmp_path, error
            ))
        except dbus.exceptions.DBusException as exc:
            _log.warning("PBAP retry PullAll failed: %s", exc)
        return False

    def disconnect(self) -> None:
        """Remove the PBAP session if one is active."""
        if self.session_path is None:
            return
        try:
            bus = dbus.SessionBus()
            client = dbus.Interface(
                bus.get_object(_OBEX_CLIENT, _OBEX_CLIENT_PATH),
                _OBEX_CLIENT_IFACE,
            )
            client.RemoveSession(self.session_path)
        except dbus.exceptions.DBusException as exc:
            _log.debug("PBAP RemoveSession failed (already gone?): %s", exc)
        finally:
            self.session_path = None
            self._pbap_iface = None

    def _wait_transfer(self, transfer_path: str, callback: Callable) -> None:
        """Poll Transfer1.Status every 500ms via GLib.timeout_add."""
        bus = dbus.SessionBus()
        props = dbus.Interface(
            bus.get_object(_OBEX_CLIENT, transfer_path),
            _PROPS_IFACE,
        )

        def _poll() -> bool:
            try:
                status = str(props.Get(_TRANSFER_IFACE, "Status"))
            except dbus.exceptions.DBusException as exc:
                name = exc.get_dbus_name()
                if name in ("org.freedesktop.DBus.Error.UnknownObject",
                            "org.freedesktop.DBus.Error.ServiceUnknown"):
                    _log.debug("PBAP transfer completed (object vanished): %s", transfer_path)
                    callback()
                    return False
                _log.warning("PBAP transfer status error: %s", exc)
                callback(error=True)
                return False
            if status == "complete":
                callback()
                return False
            if status == "error":
                _log.warning("PBAP transfer error: %s", transfer_path)
                callback(error=True)
                return False
            return True  # still in progress — reschedule

        GLib.timeout_add(_POLL_INTERVAL_MS, _poll)

    def _on_pullall_complete(self, tmp_path: str, error: bool = False) -> None:
        """Parse the downloaded vCard file and update the service contact store."""
        try:
            if error:
                _log.warning("PBAP PullAll transfer failed — contacts not updated")
                return
            try:
                with open(tmp_path, encoding="utf-8") as f:
                    content = f.read()
            except OSError as exc:
                _log.warning("PBAP: could not read vCard file: %s", exc)
                self._service.set_capability("contacts", True)
                return

            count = 0
            skipped_no_fn = 0
            skipped_no_tel = 0
            try:
                for vcard in vobject.readComponents(content):
                    fn = getattr(vcard, "fn", None)
                    if fn is None:
                        skipped_no_fn += 1
                        continue
                    name = fn.value.strip()
                    if not name:
                        skipped_no_fn += 1
                        continue
                    tels = vcard.contents.get("tel", [])
                    if not tels:
                        skipped_no_tel += 1
                        continue
                    for tel_obj in tels:
                        number = "".join(tel_obj.value.split())  # strip whitespace
                        if not number:
                            continue
                        normalized = normalize_phone(number)
                        if normalized:
                            self._service.update_contact(normalized, name)
                            count += 1
            except Exception as exc:  # noqa: BLE001
                _log.warning(
                    "PBAP PullAll: vCard parse error (partial load %d contacts): %s",
                    count, exc,
                )

            if count == 0 and self._retry_count < _MAX_RETRIES:
                # 0 contacts on a fresh pairing typically means iOS hasn't yet
                # approved "Sync Contacts." Retry on the existing session after a
                # short delay; iOS grants access asynchronously post-approval.
                self._retry_count += 1
                _log.warning(
                    "PBAP PullAll: 0 contacts — retry %d/%d in %ds "
                    "(iOS Sync-Contacts approval race?)",
                    self._retry_count, _MAX_RETRIES, _RETRY_DELAY_S,
                )
                GLib.timeout_add_seconds(_RETRY_DELAY_S, self._retry_pullall)
                self._service.set_capability("contacts", True)
                # Clear any stale empty-flag from a prior exhausted cycle so the
                # "Sync Contacts off" banner doesn't linger during this retry window.
                self._service.set_capability("contacts_empty", False)
                return

            level = _log.info if count > 0 else _log.warning
            level(
                "PBAP PullAll: %d phone-name mappings loaded "
                "(skipped: %d no-fn, %d no-tel)",
                count, skipped_no_fn, skipped_no_tel,
            )
            self._service.set_capability("contacts", True)
            # Signal GUI to show a hint when 0 contacts were loaded (tincan-d3xw).
            # This usually means 'Sync Contacts' is off in iPhone BT settings.
            self._service.set_capability("contacts_empty", count == 0)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def fetch_photo(self, phone: str) -> None:
        """Fetch a contact photo for *phone* via PBAP Pull; fire-and-forget.

        Guarded by photo_fetched flag — no OBEX call if photo already fetched.
        """
        normalized = normalize_phone(phone)
        contact = self._store.get(normalized)
        if contact is not None and contact.photo_fetched:
            return  # already fetched (or fetch attempted)

        if self.session_path is None:
            return

        try:
            bus = dbus.SessionBus()
            phonebook = dbus.Interface(
                bus.get_object(_OBEX_CLIENT, self.session_path),
                _PBAP_ACCESS_IFACE,
            )
            handles = phonebook.List(
                {"SearchValue": dbus.String(phone), "SearchAttribute": dbus.String("number")}
            )
            if not handles:
                self._service.deliver_contact_photo(phone, None)
                return
            handle = str(handles[0][0])

            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".vcf", delete=False, encoding="utf-8"
            )
            tmp_path = tmp.name
            tmp.close()

            result = phonebook.Pull(
                handle, tmp_path, {"Fields": dbus.Array(["PHOTO"], "s")}
            )
            transfer_path = str(result[0]) if isinstance(result, (list, tuple)) else str(result)
            self._wait_transfer(
                transfer_path,
                lambda error=False: self._parse_photo(phone, tmp_path, error),
            )
        except dbus.exceptions.DBusException as exc:
            _log.debug("PBAP fetch_photo failed for %s: %s", phone, exc)
            self._service.deliver_contact_photo(phone, None)

    def _parse_photo(self, phone: str, tmp_path: str, error: bool = False) -> None:
        """Parse the fetched vCard for a PHOTO field and deliver to service."""
        try:
            if error:
                self._service.deliver_contact_photo(phone, None)
                return
            try:
                with open(tmp_path, encoding="utf-8", errors="replace") as f:
                    content = f.read()
                photo_bytes: bytes | None = None
                for vcard in vobject.readComponents(content):
                    photos = vcard.contents.get("photo", [])
                    if photos:
                        raw = photos[0].value
                        photo_bytes = raw if isinstance(raw, bytes) else raw.encode("latin-1")
                        break
                self._service.deliver_contact_photo(phone, photo_bytes)
            except Exception as exc:  # noqa: BLE001
                _log.debug("PBAP photo parse error for %s: %s", phone, exc)
                self._service.deliver_contact_photo(phone, None)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
