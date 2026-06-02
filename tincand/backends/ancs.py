"""ANCSBackend — correct GATT consumer model for tincand (system bus).

Architecture (tincan-4lu / tincan-dus):
  iPhone IS the GATT server exposing the ANCS service.
  Linux IS the GATT client/consumer.

Consumer flow:
  1. Register NoInputNoOutput pairing agent on system bus.
  2. Register SolicitUUIDs=[ANCS_SERVICE_UUID] LE advertisement via LEAdvertisingManager1.
  3. iPhone sees solicitation and connects.
  4. We call Device1.Pair() to establish an authorized LE bond (triggers iOS notification
     access prompt if not already granted).
  5. After bond, BlueZ discovers iPhone's ANCS GATT service.  We enumerate via
     ObjectManager, find the three characteristic paths, call StartNotify on
     Notification Source and Data Source.
  6. Notification Source PropertiesChanged Value (8 bytes LE) → parse → filter →
     write GetNotifAttrs to Control Point → Data Source TLV → on_message_received.
  7. set_capability('ancs', True) on link up; False on link drop or errors.

NOT registered:
  - No local GattApplication / GattService1 / GattCharacteristic1 for the ANCS UUID.
    Those were the m02_ancs.py mistake: registering a local ANCS server instead of
    subscribing to the iPhone's remote server.
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

_GATT_CHAR_IFACE = "org.bluez.GattCharacteristic1"
_LE_ADV_IFACE = "org.bluez.LEAdvertisement1"
_PROPS_IFACE = "org.freedesktop.DBus.Properties"
_OBJ_MANAGER_IFACE = "org.freedesktop.DBus.ObjectManager"
_GATT_MANAGER_IFACE = "org.bluez.GattManager1"
_LE_ADV_MANAGER_IFACE = "org.bluez.LEAdvertisingManager1"
_AGENT_MANAGER_IFACE = "org.bluez.AgentManager1"
_AGENT_IFACE = "org.bluez.Agent1"
_DEVICE_IFACE = "org.bluez.Device1"

_ADV_PATH = "/uk/tincanapp/ancs/advertisement0"
_AGENT_PATH = "/uk/tincanapp/agent"


# ---------------------------------------------------------------------------
# LE advertisement — SolicitUUIDs (not ServiceUUIDs; Linux is the consumer)
# ---------------------------------------------------------------------------

class _SolicitAdvertisement(dbus.service.Object):
    """Peripheral advertisement that solicits the ANCS service from the iPhone.

    SolicitUUIDs=[ANCS_SERVICE_UUID] signals to iOS that we want to subscribe to
    its ANCS GATT service.  We do NOT register our own ANCS GATT server here.
    """

    def __init__(self, bus: dbus.Bus) -> None:
        super().__init__(bus, _ADV_PATH)
        self._props = {
            "Type": dbus.String("peripheral"),
            "SolicitUUIDs": dbus.Array([ANCS_SERVICE_UUID], signature="s"),
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
# Pairing agent — NoInputNoOutput, auto-accept (enables LE bond for ANCS)
# ---------------------------------------------------------------------------

class _PairingAgent(dbus.service.Object):
    """BlueZ pairing agent that auto-accepts to allow ANCS LE bond.

    NoInputNoOutput capability: numeric comparison is not possible; the agent
    simply accepts all incoming pairing requests.  This is the correct capability
    for headless ANCS subscription.
    """

    CAPABILITY = "NoInputNoOutput"

    def __init__(self, bus: dbus.Bus) -> None:
        super().__init__(bus, _AGENT_PATH)

    @dbus.service.method(_AGENT_IFACE, in_signature="o", out_signature="s")
    def RequestPinCode(self, device):  # noqa: N802
        return "0000"

    @dbus.service.method(_AGENT_IFACE, in_signature="o", out_signature="u")
    def RequestPasskey(self, device):  # noqa: N802
        return dbus.UInt32(0)

    @dbus.service.method(_AGENT_IFACE, in_signature="ouq")
    def DisplayPasskey(self, device, passkey, entered):  # noqa: N802
        pass

    @dbus.service.method(_AGENT_IFACE, in_signature="ou")
    def RequestConfirmation(self, device, passkey):  # noqa: N802
        pass  # auto-accept

    @dbus.service.method(_AGENT_IFACE, in_signature="o")
    def RequestAuthorization(self, device):  # noqa: N802
        pass  # auto-accept

    @dbus.service.method(_AGENT_IFACE, in_signature="os")
    def AuthorizeService(self, device, uuid):  # noqa: N802
        pass  # auto-accept

    @dbus.service.method(_AGENT_IFACE)
    def Cancel(self):  # noqa: N802
        pass

    @dbus.service.method(_AGENT_IFACE)
    def Release(self):  # noqa: N802
        pass


# ---------------------------------------------------------------------------
# ANCSBackend
# ---------------------------------------------------------------------------

class ANCSBackend(BackendInterface):
    """ANCS backend: subscribe to iPhone's ANCS service via GATT consumer model.

    start() / connect(): register pairing agent + SolicitUUIDs advertisement;
      watch PropertiesChanged for iPhone connect event.
    _on_device_connected(): establish LE bond via Device1.Pair(); enumerate
      BlueZ ObjectManager to find ANCS chars; StartNotify on NotifSource + DataSource.
    _on_notif_source_changed(): parse 8-byte header; filter messages; write Control Point.
    _on_data_source_changed(): accumulate TLV; parse; call on_message_received.
    stop(): Unregister advertisement + agent; set_capability(ancs, False).
    """

    def __init__(
        self,
        adapter_path: str = "/org/bluez/hci0",
        device_addr: str | None = None,
    ) -> None:
        self._adapter_path = adapter_path
        self._device_addr = device_addr
        self._service = None
        self._bus: dbus.Bus | None = None
        self._adv: _SolicitAdvertisement | None = None
        self._agent: _PairingAgent | None = None
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
        if device_addr and not self._device_addr:
            self._device_addr = device_addr
        self.start()

    def disconnect(self) -> None:
        self.stop()

    def poll_inbox(self) -> list:
        return []

    def get_message(self, handle: str) -> object:
        return None  # ANCS is push-only; no per-message fetch

    def send_message(self, to: str, body: str) -> str:
        raise NotImplementedError("ANCS is receive-only; use MapBackend for sending")

    # ------------------------------------------------------------------
    # GATT consumer lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Connect to system bus, register pairing agent + SolicitUUIDs advertisement."""
        try:
            self._bus = dbus.SystemBus()
        except dbus.exceptions.DBusException as exc:
            _log.warning("ANCSBackend: cannot connect to system bus: %s", exc)
            if self._service is not None:
                self._service.set_capability("ancs", False)
            return

        # Pairing agent — enables LE bond which triggers iOS ANCS access prompt
        self._agent = _PairingAgent(self._bus)
        try:
            agent_mgr = dbus.Interface(
                self._bus.get_object("org.bluez", "/org/bluez"),
                _AGENT_MANAGER_IFACE,
            )
            agent_mgr.RegisterAgent(_AGENT_PATH, _PairingAgent.CAPABILITY)
            agent_mgr.RequestDefaultAgent(_AGENT_PATH)
            _log.debug("ANCSBackend: pairing agent registered")
        except dbus.exceptions.DBusException as exc:
            _log.warning("ANCSBackend: RegisterAgent failed (may already exist): %s", exc)

        # SolicitUUIDs advertisement — signals iPhone to expose its ANCS service
        self._adv = _SolicitAdvertisement(self._bus)
        try:
            adv_mgr = dbus.Interface(
                self._bus.get_object("org.bluez", self._adapter_path),
                _LE_ADV_MANAGER_IFACE,
            )
            adv_mgr.RegisterAdvertisement(_ADV_PATH, {})
            _log.debug("ANCSBackend: SolicitUUIDs advertisement registered")
        except dbus.exceptions.DBusException as exc:
            _log.warning("ANCSBackend: RegisterAdvertisement failed: %s", exc)

        # Watch for iPhone connection events
        self._bus.add_signal_receiver(
            self._on_properties_changed,
            signal_name="PropertiesChanged",
            dbus_interface=_PROPS_IFACE,
            path_keyword="path",
        )
        _log.info("ANCSBackend: started — listening for ANCS device connection")

    def stop(self) -> None:
        """Unregister advertisement + agent; clean up."""
        if self._bus is None:
            return

        try:
            adv_mgr = dbus.Interface(
                self._bus.get_object("org.bluez", self._adapter_path),
                _LE_ADV_MANAGER_IFACE,
            )
            adv_mgr.UnregisterAdvertisement(_ADV_PATH)
        except dbus.exceptions.DBusException as exc:
            _log.debug("ANCSBackend: UnregisterAdvertisement: %s", exc)

        try:
            agent_mgr = dbus.Interface(
                self._bus.get_object("org.bluez", "/org/bluez"),
                _AGENT_MANAGER_IFACE,
            )
            agent_mgr.UnregisterAgent(_AGENT_PATH)
        except dbus.exceptions.DBusException as exc:
            _log.debug("ANCSBackend: UnregisterAgent: %s", exc)

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
        """Establish LE bond, then discover and subscribe to ANCS chars."""
        if self._bus is None:
            return

        if self._device_addr:
            # Filter: only handle the configured target device
            device_addr_from_path = str(device_path).split("/")[-1].replace("_", ":").upper()
            if device_addr_from_path != self._device_addr.upper():
                _log.debug(
                    "ANCSBackend: ignoring connection from %s (expecting %s)",
                    device_addr_from_path, self._device_addr,
                )
                return

        # Initiate LE bond (triggers iOS notification access prompt if not bonded)
        try:
            device_iface = dbus.Interface(
                self._bus.get_object("org.bluez", device_path),
                _DEVICE_IFACE,
            )
            props = dbus.Interface(
                self._bus.get_object("org.bluez", device_path),
                _PROPS_IFACE,
            )
            bonded = bool(props.Get(_DEVICE_IFACE, "Bonded"))
            if not bonded:
                _log.info("ANCSBackend: requesting LE bond with %s", device_path)
                device_iface.Pair()
        except dbus.exceptions.DBusException as exc:
            _log.warning(
                "ANCSBackend: LE bond failed for %s: %s — "
                "ANCS unavailable (MAP polling continues)",
                device_path, exc,
            )
            if self._service is not None:
                self._service.set_capability("ancs", False)
            return

        # Enumerate BlueZ's view of the iPhone's GATT services
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
            # Only consider chars under the connected device path
            if not str(obj_path).startswith(str(device_path)):
                continue
            uuid = str(ifaces[_GATT_CHAR_IFACE].get("UUID", "")).upper()
            if uuid == NOTIF_SOURCE_UUID.upper():
                notif_src_path = str(obj_path)
            elif uuid == CONTROL_POINT_UUID.upper():
                ctrl_pt_path = str(obj_path)
            elif uuid == DATA_SOURCE_UUID.upper():
                data_src_path = str(obj_path)

        if not all((notif_src_path, ctrl_pt_path, data_src_path)):
            _log.warning(
                "ANCSBackend: ANCS service not found on %s "
                "(notif=%s ctrl=%s data=%s) — iOS may not have granted access yet",
                device_path, notif_src_path, ctrl_pt_path, data_src_path,
            )
            if self._service is not None:
                self._service.set_capability("ancs", False)
            return

        try:
            self._control_point_proxy = dbus.Interface(
                self._bus.get_object("org.bluez", ctrl_pt_path),
                _GATT_CHAR_IFACE,
            )
        except dbus.exceptions.DBusException as exc:
            _log.warning("ANCSBackend: could not get ControlPoint proxy: %s", exc)
            if self._service is not None:
                self._service.set_capability("ancs", False)
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
        _log.info("ANCSBackend: ANCS link established on %s", device_path)

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
