"""ANCS GATT scaffold and ANCSBackend for tincand (direct GATT, system bus).

Architecture (tincan-034 / tincan-1cj):
- All D-Bus objects on the SYSTEM BUS (not session bus)
- iPhone is the GATT server; Linux is the GATT client/consumer
- We advertise SolicitUUIDs=[ANCS_SERVICE_UUID] as a peripheral to trigger
  iOS to expose ANCS; BlueZ discovers the service; we StartNotify on its chars

Four GATT scaffold classes registered on the system bus:
  GattApplication  — ObjectManager returning service0 + char0/char1/char2
  GattService1     — ANCS service properties (UUID, Primary)
  GattCharacteristic1 — Reusable char: UUID, Flags, ReadValue, WriteValue,
                        StartNotify, StopNotify, write_callback
  LEAdvertisement1 — Peripheral advertisement (ServiceUUIDs=[ANCS], LocalName=tincan)
"""
from __future__ import annotations

import logging
import struct

import dbus
import dbus.service

from tincand.ancs_util import (
    ANCS_SERVICE_UUID,
    ATTR_APP_ID,
    ATTR_MESSAGE,
    ATTR_TITLE,
    CONTROL_POINT_UUID,
    DATA_SOURCE_UUID,
    NOTIF_SOURCE_UUID,
    ANCSDataBuffer,
    build_get_attrs_cmd,
    parse_data_source,
    parse_notification_source,
)
from tincand.backends.base import BackendInterface

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# D-Bus interface constants
# ---------------------------------------------------------------------------

_GATT_SVC_IFACE = "org.bluez.GattService1"
_GATT_CHAR_IFACE = "org.bluez.GattCharacteristic1"
_LE_ADV_IFACE = "org.bluez.LEAdvertisement1"
_PROPS_IFACE = "org.freedesktop.DBus.Properties"
_OBJ_MANAGER_IFACE = "org.freedesktop.DBus.ObjectManager"
_GATT_MANAGER_IFACE = "org.bluez.GattManager1"
_LE_ADV_MANAGER_IFACE = "org.bluez.LEAdvertisingManager1"
_DEVICE_IFACE = "org.bluez.Device1"

# Base D-Bus path for all ANCS objects
_BASE_PATH = "/uk/tincanapp/ancs"
_APP_PATH = f"{_BASE_PATH}/app"
_SVC_PATH = f"{_BASE_PATH}/service0"
_CHAR0_PATH = f"{_BASE_PATH}/char0"   # Notification Source
_CHAR1_PATH = f"{_BASE_PATH}/char1"   # Control Point
_CHAR2_PATH = f"{_BASE_PATH}/char2"   # Data Source
_ADV_PATH = f"{_BASE_PATH}/advertisement0"

_NOTSUPP = dbus.exceptions.DBusException(
    "Not supported",
    name="org.bluez.Error.NotSupported",
)


# ---------------------------------------------------------------------------
# GATT scaffold classes
# ---------------------------------------------------------------------------

class GattApplication(dbus.service.Object):
    """GATT application: ObjectManager for BlueZ RegisterApplication.

    GetManagedObjects() returns service0 + char0/char1/char2.
    advertisement0 is NOT included (registered separately with LEAdvertisingManager1).
    """

    def __init__(self, bus: dbus.Bus) -> None:
        super().__init__(bus, _APP_PATH)

    @dbus.service.method(_OBJ_MANAGER_IFACE, out_signature="a{oa{sa{sv}}}")
    def GetManagedObjects(self):  # noqa: N802
        return dbus.Dictionary({
            dbus.ObjectPath(_SVC_PATH): dbus.Dictionary({
                _GATT_SVC_IFACE: dbus.Dictionary({
                    "UUID": dbus.String(ANCS_SERVICE_UUID),
                    "Primary": dbus.Boolean(True),
                }, signature="sv"),
            }, signature="sa{sv}"),
            dbus.ObjectPath(_CHAR0_PATH): dbus.Dictionary({
                _GATT_CHAR_IFACE: dbus.Dictionary({
                    "UUID": dbus.String(NOTIF_SOURCE_UUID),
                    "Service": dbus.ObjectPath(_SVC_PATH),
                    "Flags": dbus.Array(["notify"], signature="s"),
                }, signature="sv"),
            }, signature="sa{sv}"),
            dbus.ObjectPath(_CHAR1_PATH): dbus.Dictionary({
                _GATT_CHAR_IFACE: dbus.Dictionary({
                    "UUID": dbus.String(CONTROL_POINT_UUID),
                    "Service": dbus.ObjectPath(_SVC_PATH),
                    "Flags": dbus.Array(["write-without-response"], signature="s"),
                }, signature="sv"),
            }, signature="sa{sv}"),
            dbus.ObjectPath(_CHAR2_PATH): dbus.Dictionary({
                _GATT_CHAR_IFACE: dbus.Dictionary({
                    "UUID": dbus.String(DATA_SOURCE_UUID),
                    "Service": dbus.ObjectPath(_SVC_PATH),
                    "Flags": dbus.Array(["notify"], signature="s"),
                }, signature="sv"),
            }, signature="sa{sv}"),
        }, signature="oa{sa{sv}}")


class GattService1(dbus.service.Object):
    """GATT service: ANCS_SERVICE_UUID, Primary=True."""

    def __init__(self, bus: dbus.Bus) -> None:
        super().__init__(bus, _SVC_PATH)
        self._props = {
            "UUID": dbus.String(ANCS_SERVICE_UUID),
            "Primary": dbus.Boolean(True),
        }

    @dbus.service.method(_PROPS_IFACE, in_signature="ss", out_signature="v")
    def Get(self, interface, prop):  # noqa: N802
        if interface == _GATT_SVC_IFACE:
            return self._props[prop]
        raise dbus.exceptions.DBusException(
            name="org.freedesktop.DBus.Error.InvalidArgs",
        )

    @dbus.service.method(_PROPS_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):  # noqa: N802
        if interface == _GATT_SVC_IFACE:
            return dbus.Dictionary(self._props, signature="sv")
        raise dbus.exceptions.DBusException(
            name="org.freedesktop.DBus.Error.InvalidArgs",
        )


class GattCharacteristic1(dbus.service.Object):
    """Reusable GATT characteristic.

    uuid           — GATT UUID string
    flags          — list of flag strings (e.g. ["notify"], ["write-without-response"])
    service_path   — D-Bus path of the parent GattService1
    obj_path       — D-Bus object path for this characteristic
    write_callback — called with bytes value when WriteValue arrives (ControlPoint only)
    """

    def __init__(
        self,
        bus: dbus.Bus,
        obj_path: str,
        uuid: str,
        flags: list[str],
        service_path: str,
        write_callback=None,
    ) -> None:
        super().__init__(bus, obj_path)
        self._uuid = uuid
        self._flags = flags
        self._service_path = service_path
        self._write_callback = write_callback
        self._notifying = False
        self._props = {
            "UUID": dbus.String(uuid),
            "Service": dbus.ObjectPath(service_path),
            "Flags": dbus.Array(flags, signature="s"),
        }

    @dbus.service.method(_PROPS_IFACE, in_signature="ss", out_signature="v")
    def Get(self, interface, prop):  # noqa: N802
        if interface == _GATT_CHAR_IFACE:
            return self._props[prop]
        raise dbus.exceptions.DBusException(
            name="org.freedesktop.DBus.Error.InvalidArgs",
        )

    @dbus.service.method(_PROPS_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):  # noqa: N802
        if interface == _GATT_CHAR_IFACE:
            return dbus.Dictionary(self._props, signature="sv")
        raise dbus.exceptions.DBusException(
            name="org.freedesktop.DBus.Error.InvalidArgs",
        )

    @dbus.service.method(_GATT_CHAR_IFACE, in_signature="a{sv}", out_signature="ay")
    def ReadValue(self, options):  # noqa: N802
        raise _NOTSUPP

    @dbus.service.method(_GATT_CHAR_IFACE, in_signature="aya{sv}")
    def WriteValue(self, value, options):  # noqa: N802
        if self._write_callback is not None:
            self._write_callback(bytes(value))
        else:
            raise _NOTSUPP

    @dbus.service.method(_GATT_CHAR_IFACE)
    def StartNotify(self):  # noqa: N802
        if "notify" not in self._flags:
            raise _NOTSUPP
        self._notifying = True

    @dbus.service.method(_GATT_CHAR_IFACE)
    def StopNotify(self):  # noqa: N802
        if "notify" not in self._flags:
            raise _NOTSUPP
        self._notifying = False

    @property
    def notifying(self) -> bool:
        return self._notifying


class LEAdvertisement1(dbus.service.Object):
    """LE peripheral advertisement for ANCS solicitation.

    Type: peripheral, ServiceUUIDs=[ANCS_SERVICE_UUID], LocalName=tincan.
    BlueZ LEAdvertisingManager1 calls Release() when unregistering — no-op here.
    """

    def __init__(self, bus: dbus.Bus) -> None:
        super().__init__(bus, _ADV_PATH)
        self._props = {
            "Type": dbus.String("peripheral"),
            "ServiceUUIDs": dbus.Array([ANCS_SERVICE_UUID], signature="s"),
            "LocalName": dbus.String("tincan"),
        }

    @dbus.service.method(_PROPS_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):  # noqa: N802
        if interface == _LE_ADV_IFACE:
            return dbus.Dictionary(self._props, signature="sv")
        raise dbus.exceptions.DBusException(
            name="org.freedesktop.DBus.Error.InvalidArgs",
        )

    @dbus.service.method(_LE_ADV_IFACE)
    def Release(self):  # noqa: N802
        pass


# ---------------------------------------------------------------------------
# ANCSBackend
# ---------------------------------------------------------------------------

class ANCSBackend(BackendInterface):
    """ANCS notification backend using direct GATT D-Bus on the system bus.

    Lifecycle:
      start()  — connect system bus; register GattApplication + LEAdvertisement;
                 watch PropertiesChanged for device connect/disconnect
      stop()   — unregister both; set_capability('ancs', False)

    Notification flow (once device connected + ANCS chars discovered):
      NotifSource → _on_notif_source_changed → filter → WriteValue ControlPoint
      DataSource  → _on_data_source_changed  → ANCSDataBuffer → parse → on_message_received
    """

    def __init__(
        self,
        adapter_path: str = "/org/bluez/hci0",
        device_addr: str | None = None,
    ) -> None:
        self._adapter_path = adapter_path
        self._device_addr = device_addr  # optional: filter by address in _on_device_connected
        self._service = None
        self._bus: dbus.Bus | None = None
        self._app: GattApplication | None = None
        self._adv: LEAdvertisement1 | None = None
        self._data_buffer = ANCSDataBuffer()
        self._control_point_proxy = None

    # ------------------------------------------------------------------
    # BackendInterface
    # ------------------------------------------------------------------

    def register_service(self, svc) -> None:
        self._service = svc

    def list_conversations(self) -> list:
        return []

    def connect(self, device_addr: str) -> None:
        self.start()

    def disconnect(self) -> None:
        self.stop()

    def poll_inbox(self) -> list:
        return []

    def send_message(self, to: str, body: str) -> str:
        raise NotImplementedError("ANCS is receive-only; use MapBackend for sending")

    # ------------------------------------------------------------------
    # GATT lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Connect to system bus, register GATT app + advertisement."""
        try:
            self._bus = dbus.SystemBus()
        except dbus.exceptions.DBusException as exc:
            _log.warning("ANCSBackend: cannot connect to system bus: %s", exc)
            if self._service is not None:
                self._service.set_capability("ancs", False)
            return

        self._app = GattApplication(self._bus)
        self._adv = LEAdvertisement1(self._bus)
        GattCharacteristic1(
            self._bus, _CHAR0_PATH, NOTIF_SOURCE_UUID, ["notify"], _SVC_PATH
        )
        GattCharacteristic1(
            self._bus, _CHAR1_PATH, CONTROL_POINT_UUID,
            ["write-without-response"], _SVC_PATH,
        )
        GattCharacteristic1(
            self._bus, _CHAR2_PATH, DATA_SOURCE_UUID, ["notify"], _SVC_PATH
        )

        try:
            adapter = dbus.Interface(
                self._bus.get_object("org.bluez", self._adapter_path),
                _GATT_MANAGER_IFACE,
            )
            adapter.RegisterApplication(_APP_PATH, {})
        except dbus.exceptions.DBusException as exc:
            _log.warning("ANCSBackend: RegisterApplication failed: %s", exc)

        try:
            adv_mgr = dbus.Interface(
                self._bus.get_object("org.bluez", self._adapter_path),
                _LE_ADV_MANAGER_IFACE,
            )
            adv_mgr.RegisterAdvertisement(_ADV_PATH, {})
        except dbus.exceptions.DBusException as exc:
            _log.warning("ANCSBackend: RegisterAdvertisement failed: %s", exc)

        self._bus.add_signal_receiver(
            self._on_properties_changed,
            signal_name="PropertiesChanged",
            dbus_interface=_PROPS_IFACE,
            path_keyword="path",
        )
        _log.info("ANCSBackend: started on system bus")

    def stop(self) -> None:
        """Unregister GATT app + advertisement; clean up."""
        if self._bus is None:
            return

        try:
            adapter = dbus.Interface(
                self._bus.get_object("org.bluez", self._adapter_path),
                _GATT_MANAGER_IFACE,
            )
            adapter.UnregisterApplication(_APP_PATH)
        except dbus.exceptions.DBusException as exc:
            _log.debug("ANCSBackend: UnregisterApplication: %s", exc)

        try:
            adv_mgr = dbus.Interface(
                self._bus.get_object("org.bluez", self._adapter_path),
                _LE_ADV_MANAGER_IFACE,
            )
            adv_mgr.UnregisterAdvertisement(_ADV_PATH)
        except dbus.exceptions.DBusException as exc:
            _log.debug("ANCSBackend: UnregisterAdvertisement: %s", exc)

        if self._service is not None:
            self._service.set_capability("ancs", False)
        self._bus = None
        self._control_point_proxy = None
        _log.info("ANCSBackend: stopped")

    # ------------------------------------------------------------------
    # Signal handlers
    # ------------------------------------------------------------------

    def _on_properties_changed(self, interface, changed, invalidated, path=None):
        if interface != _DEVICE_IFACE:
            return
        if "Connected" in changed:
            if changed["Connected"]:
                self._on_device_connected(path)
            else:
                self._on_device_disconnected()

    def _on_device_connected(self, device_path: str) -> None:
        """Enumerate ANCS chars via ObjectManager, then StartNotify."""
        if self._bus is None:
            return
        try:
            obj_mgr = dbus.Interface(
                self._bus.get_object("org.bluez", "/"),
                _OBJ_MANAGER_IFACE,
            )
            objects = obj_mgr.GetManagedObjects()
        except dbus.exceptions.DBusException as exc:
            _log.warning("ANCSBackend: GetManagedObjects failed: %s", exc)
            return

        notif_src_path = ctrl_pt_path = data_src_path = None
        for obj_path, ifaces in objects.items():
            if _GATT_CHAR_IFACE not in ifaces:
                continue
            char_props = ifaces[_GATT_CHAR_IFACE]
            uuid = str(char_props.get("UUID", "")).upper()
            if uuid == NOTIF_SOURCE_UUID.upper():
                notif_src_path = str(obj_path)
            elif uuid == CONTROL_POINT_UUID.upper():
                ctrl_pt_path = str(obj_path)
            elif uuid == DATA_SOURCE_UUID.upper():
                data_src_path = str(obj_path)

        if not all((notif_src_path, ctrl_pt_path, data_src_path)):
            _log.warning(
                "ANCSBackend: ANCS chars not found on device %s "
                "(notif=%s ctrl=%s data=%s)",
                device_path, notif_src_path, ctrl_pt_path, data_src_path,
            )
            return

        try:
            self._control_point_proxy = dbus.Interface(
                self._bus.get_object("org.bluez", ctrl_pt_path),
                _GATT_CHAR_IFACE,
            )
        except dbus.exceptions.DBusException as exc:
            _log.warning("ANCSBackend: could not get ControlPoint proxy: %s", exc)
            return

        for path, name in (
            (notif_src_path, "NotifSource"),
            (data_src_path, "DataSource"),
        ):
            try:
                char = dbus.Interface(
                    self._bus.get_object("org.bluez", path), _GATT_CHAR_IFACE
                )
                char.StartNotify()
                _log.debug("ANCSBackend: StartNotify on %s (%s)", name, path)
            except dbus.exceptions.DBusException as exc:
                _log.warning("ANCSBackend: StartNotify failed for %s: %s", name, exc)

        self._bus.add_signal_receiver(
            self._on_notif_source_changed,
            signal_name="PropertiesChanged",
            dbus_interface=_PROPS_IFACE,
            path=notif_src_path,
        )
        self._bus.add_signal_receiver(
            lambda iface, changed, inv: self._on_data_source_changed(changed),
            signal_name="PropertiesChanged",
            dbus_interface=_PROPS_IFACE,
            path=data_src_path,
        )

        if self._service is not None:
            self._service.set_capability("ancs", True)
        _log.info("ANCSBackend: ANCS connected on %s", device_path)

    def _on_device_disconnected(self) -> None:
        self._data_buffer._buffers.clear()
        self._control_point_proxy = None
        if self._service is not None:
            self._service.set_capability("ancs", False)
        _log.info("ANCSBackend: device disconnected")

    def _on_notif_source_changed(self, interface, changed, invalidated):
        if "Value" not in changed:
            return
        try:
            parsed = parse_notification_source(bytes(changed["Value"]))
        except ValueError as exc:
            _log.debug("ANCSBackend: parse_notification_source error: %s", exc)
            return
        if parsed["event_id"] != 0 or parsed["category_id"] not in (4, 6):
            return
        uid = parsed["notification_uid"]
        self._data_buffer.clear(uid)
        if self._control_point_proxy is None:
            return
        cmd = build_get_attrs_cmd(uid, [ATTR_APP_ID, ATTR_TITLE, ATTR_MESSAGE])
        try:
            self._control_point_proxy.WriteValue(list(cmd), {})
        except dbus.exceptions.DBusException as exc:
            _log.warning("ANCSBackend: WriteValue(ControlPoint) failed: %s", exc)

    def _on_data_source_changed(self, changed):
        if "Value" not in changed:
            return
        chunk = bytes(changed["Value"])
        if len(chunk) < 5:
            return
        uid = struct.unpack_from("<L", chunk, 1)[0]
        complete = self._data_buffer.accumulate(uid, chunk)
        if complete is None:
            return
        try:
            result = parse_data_source(complete)
        except Exception as exc:
            _log.warning(
                "ANCSBackend: parse_data_source error for uid=%d: %s", uid, exc
            )
            self._data_buffer.clear(uid)
            return
        self._data_buffer.clear(uid)
        attrs = result.get("attrs", {})
        if self._service is not None:
            self._service.on_message_received({
                "conversation_id": attrs.get(ATTR_APP_ID, ""),
                "body": attrs.get(ATTR_MESSAGE, ""),
                "from": attrs.get(ATTR_TITLE, ""),
                "direction": "inbound",
                "status": "unread",
                "timestamp": "",
            })
