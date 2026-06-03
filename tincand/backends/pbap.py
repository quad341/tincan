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


class PBAPContactSync:
    """PBAP Phase-1: pull all contact names into TincanService via PullAll."""

    def __init__(self, service: "TincanService") -> None:
        self._service = service
        self._store = service._contact_store
        self.session_path: str | None = None

    def connect(self, device_addr: str) -> None:
        """Create PBAP session, run PullAll, parse vCards, update service contacts."""
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
            pbap.Select("int", "pb")

            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".vcf", delete=False, encoding="utf-8"
            )
            tmp_path = tmp.name
            tmp.close()

            result = pbap.PullAll(
                tmp_path,
                {"Format": dbus.String("vcard21"), "Fields": dbus.Array(["FN", "TEL"], "s")},
            )
            transfer_path = str(result[0]) if isinstance(result, (list, tuple)) else str(result)
            self._wait_transfer(transfer_path, lambda error=False: self._on_pullall_complete(
                tmp_path, error
            ))
        except dbus.exceptions.DBusException as exc:
            _log.warning("PBAP connect failed for %s: %s", device_addr, exc)

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
            try:
                for vcard in vobject.readComponents(content):
                    fn = getattr(vcard, "fn", None)
                    if fn is None:
                        continue
                    name = fn.value.strip()
                    if not name:
                        continue
                    tels = vcard.contents.get("tel", [])
                    if not tels:
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
                _log.warning("PBAP PullAll: vCard parse error (partial load %d contacts): %s", count, exc)

            _log.info("PBAP PullAll: %d phone-name mappings loaded", count)
            self._service.set_capability("contacts", True)
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
