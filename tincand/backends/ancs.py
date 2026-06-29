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
from gi.repository import GLib

from tincand.ancs_util import (
    ANCS_SERVICE_UUID,
    ATTR_APP_ID,
    ATTR_DATE,
    ATTR_MESSAGE,
    ATTR_SUBTITLE,
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
from tincand.pairing import FailureReason

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
        self._notif_src_path: str | None = None
        self._data_src_path: str | None = None
        self._uid_meta: dict[int, tuple[int, int]] = {}  # uid → (category_id, event_flags)
        self._health_check_id: int | None = None
        self._heal_timer_id: int | None = None
        self._heal_attempts: int = 0
        self._backlog_suppress: bool = False
        self._backlog_timer_id: int | None = None
        self._subscribe_pending: bool = False
        self._adv_failure_reason: str | None = None

    # ------------------------------------------------------------------
    # BackendInterface
    # ------------------------------------------------------------------

    def register_service(self, svc) -> None:
        self._service = svc

    def list_conversations(self) -> list:
        return []

    def connect(self, device_addr: str) -> None:
        if device_addr:
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

    def send_group_message(self, participants: list[str], body: str) -> str:
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

        # SolicitUUIDs advertisement — signals iPhone to expose its ANCS service.
        # RegisterAdvertisement MUST be async: BlueZ calls Properties.GetAll on
        # our advertisement object during registration; a synchronous call blocks
        # the main thread and cannot service that callback → deadlock → NoReply.
        self._adv = _SolicitAdvertisement(self._bus)
        try:
            adv_mgr = dbus.Interface(
                self._bus.get_object("org.bluez", self._adapter_path),
                _LE_ADV_MANAGER_IFACE,
            )
            adv_mgr.RegisterAdvertisement(
                _ADV_PATH, {},
                reply_handler=self._on_adv_registered,
                error_handler=self._on_adv_error,
            )
            _log.debug("ANCSBackend: SolicitUUIDs advertisement registration sent (async)")
        except dbus.exceptions.DBusException as exc:
            _log.warning("ANCSBackend: RegisterAdvertisement call failed: %s", exc)

        # Watch for iPhone connection events
        self._bus.add_signal_receiver(
            self._on_properties_changed,
            signal_name="PropertiesChanged",
            dbus_interface=_PROPS_IFACE,
            path_keyword="path",
        )
        self._bus.add_signal_receiver(
            self._on_interfaces_added,
            signal_name="InterfacesAdded",
            dbus_interface=_OBJ_MANAGER_IFACE,
            bus_name="org.bluez",
            path="/",
        )
        _log.info("ANCSBackend: started — listening for ANCS device connection")
        if self._service is not None and hasattr(self._service, "set_ancs_status"):
            self._service.set_ancs_status("armed")

        # Probe for devices already connected before start() was called
        # (daemon restart or phone auto-reconnect before daemon starts).
        self._probe_connected_devices()
        self._probe_le_advertising()

    def _probe_connected_devices(self) -> None:
        """Schedule _on_device_connected for any device already connected at start().

        Uses idle_add so the callback runs after the GLib main loop starts.
        The double-subscribe guard in _on_device_connected prevents duplicate subscriptions.
        """
        if self._bus is None:
            return
        try:
            obj_mgr = dbus.Interface(
                self._bus.get_object("org.bluez", "/"),
                _OBJ_MANAGER_IFACE,
            )
            objects = obj_mgr.GetManagedObjects()
        except dbus.exceptions.DBusException as exc:
            _log.debug("ANCSBackend: _probe_connected_devices failed: %s", exc)
            return

        for obj_path, ifaces in objects.items():
            dev = ifaces.get(_DEVICE_IFACE, {})
            if not bool(dev.get("Connected", False)):
                continue
            if not bool(dev.get("ServicesResolved", False)):
                continue
            if self._device_addr:
                if str(dev.get("Address", "")).upper() != self._device_addr.upper():
                    continue
            _log.info(
                "ANCSBackend: already-connected device %s — scheduling subscribe",
                obj_path,
            )
            GLib.idle_add(self._on_device_connected, str(obj_path))

    def _probe_le_advertising(self) -> None:
        """Log LEAdvertisingManager1 capacity; degrade early if advertising unsupported."""
        if self._bus is None:
            return
        _REMEDY = (
            "Remedies: use a USB BT adapter (RTL8761B, e.g. ASUS USB-BT500), "
            "or run bluetoothd --experimental and restart bluetooth."
        )
        try:
            props_iface = dbus.Interface(
                self._bus.get_object("org.bluez", self._adapter_path),
                _PROPS_IFACE,
            )
            props = props_iface.GetAll(_LE_ADV_MANAGER_IFACE)
            supported = int(props.get("SupportedInstances", -1))
            active = int(props.get("ActiveInstances", -1))
            _log.info(
                "ANCSBackend: LEAdvertisingManager1 probe on %s — "
                "SupportedInstances=%d ActiveInstances=%d",
                self._adapter_path, supported, active,
            )
            if supported == 0:
                _log.warning(
                    "ANCSBackend: adapter %s reports SupportedInstances=0 — LE advertising "
                    "not supported. ANCS will not arm. %s",
                    self._adapter_path, _REMEDY,
                )
                if self._service is not None:
                    self._service.set_capability("ancs", False)
        except dbus.exceptions.DBusException as exc:
            _log.warning(
                "ANCSBackend: LEAdvertisingManager1 probe failed on %s: %s — "
                "cannot confirm LE advertising support. %s",
                self._adapter_path, exc, _REMEDY,
            )
            if self._service is not None:
                self._service.set_capability("ancs", False)

    def _on_adv_registered(self) -> None:
        _log.info("ANCSBackend: SolicitUUIDs advertisement registered — soliciting ANCS")

    def _on_adv_error(self, exc) -> None:
        exc_str = str(exc)
        if "Invalid Parameters" in exc_str or "0x0d" in exc_str:
            self._adv_failure_reason = FailureReason.ANCS_EXT_ADV_BUG
            _log.warning(
                "ANCSBackend: RegisterAdvertisement failed — BlueZ ext-adv length bug "
                "(%s, adapter %s). Fix: patch BlueZ ≤ 5.86 or use a USB BT adapter "
                "(RTL8761B, e.g. ASUS USB-BT500). "
                "See docs/ancs-bluez-ext-adv-rootcause.md.",
                exc, self._adapter_path,
            )
        elif "NotSupported" in exc_str:
            self._adv_failure_reason = FailureReason.ANCS_EXPERIMENTAL_REQUIRED
            _log.warning(
                "ANCSBackend: RegisterAdvertisement failed — bluetoothd --experimental "
                "required for SolicitUUIDs (%s, adapter %s). "
                "Run bluetoothd with --experimental and restart bluetooth.",
                exc, self._adapter_path,
            )
        else:
            self._adv_failure_reason = FailureReason.ADVERTISING_FAILED
            _log.warning(
                "ANCSBackend: RegisterAdvertisement failed (%s). ANCS needs LE advertising; "
                "this BT controller (%s) may not support it. Remedies: use a USB BT adapter "
                "(RTL8761B, e.g. ASUS USB-BT500), or run bluetoothd --experimental and "
                "restart bluetooth.",
                exc, self._adapter_path,
            )
        if self._service is not None:
            self._service.set_capability("ancs", False)

    def stop(self) -> None:
        """Unregister advertisement + agent; clean up."""
        if self._bus is None:
            return

        if self._health_check_id is not None:
            GLib.source_remove(self._health_check_id)
            self._health_check_id = None
        if self._heal_timer_id is not None:
            GLib.source_remove(self._heal_timer_id)
            self._heal_timer_id = None
        if self._backlog_timer_id is not None:
            GLib.source_remove(self._backlog_timer_id)
            self._backlog_timer_id = None
        self._backlog_suppress = False
        self._subscribe_pending = False
        self._notif_src_path = None
        self._data_src_path = None

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
            if hasattr(self._service, "set_ancs_status"):
                self._service.set_ancs_status("disabled")
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

    def _on_interfaces_added(self, object_path: str, interfaces: dict) -> None:
        if _DEVICE_IFACE not in interfaces:
            return
        if not interfaces[_DEVICE_IFACE].get("Connected", False):
            return
        _log.info("ANCSBackend: InterfacesAdded Connected=True for %s", object_path)
        GLib.idle_add(self._on_device_connected, str(object_path))

    def _on_device_connected(self, device_path: str) -> None:
        """Establish LE bond, then discover and subscribe to ANCS chars."""
        if self._bus is None:
            return
        # Double-subscribe guard: at-start probe and PropertiesChanged can both fire
        if self._notif_src_path is not None:
            return

        # Get device interfaces — properties read via DBus.Properties, not Device1
        try:
            dev_obj = self._bus.get_object("org.bluez", device_path)
            device_iface = dbus.Interface(dev_obj, _DEVICE_IFACE)
            props_iface = dbus.Interface(dev_obj, _PROPS_IFACE)
        except dbus.exceptions.DBusException as exc:
            _log.warning("ANCSBackend: cannot get device interface for %s: %s", device_path, exc)
            return

        if self._device_addr:
            # Filter: only handle the configured target device (case-insensitive)
            try:
                device_addr = str(props_iface.Get(_DEVICE_IFACE, "Address"))
            except dbus.exceptions.DBusException as exc:
                _log.warning("ANCSBackend: cannot read device address: %s", exc)
                return
            if device_addr.upper() != self._device_addr.upper():
                _log.debug(
                    "ANCSBackend: ignoring device %s (filter=%s)",
                    device_addr, self._device_addr,
                )
                return

        # Initiate LE bond (triggers iOS notification access prompt if not bonded)
        try:
            bonded = bool(props_iface.Get(_DEVICE_IFACE, "Bonded"))
        except dbus.exceptions.DBusException as exc:
            _log.warning("ANCSBackend: cannot read Bonded property for %s: %s", device_path, exc)
            return

        if not bonded:
            _log.info("ANCSBackend: requesting LE bond with %s", device_path)
            try:
                device_iface.Pair()
            except dbus.exceptions.DBusException as exc:
                err = getattr(exc, "get_dbus_name", lambda: str(exc))()
                if err == "org.bluez.Error.AlreadyExists":
                    # Device has a Classic bond but no LE bond yet — proceed to GATT discovery.
                    # If no LE ACL is live, StartNotify will return OK but Notifying stays False;
                    # _check_notifying_after_subscribe then enters HEALING, ready to recover when
                    # iOS opens an LE link on its next natural BT reconnect (tincan-ygh87).
                    _log.info(
                        "ANCSBackend: %s already classic-paired — "
                        "proceeding to GATT discovery without LE re-pair",
                        device_path,
                    )
                else:
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

        subscribe_was_pending = self._subscribe_pending
        self._subscribe_pending = False

        notify_ok = 0
        any_in_progress = False
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
                notify_ok += 1
            except dbus.exceptions.DBusException as exc:
                if "InProgress" in str(exc) and not subscribe_was_pending:
                    any_in_progress = True
                    _log.warning(
                        "ANCSBackend: StartNotify InProgress for %s — retry in 1.5 s", name
                    )
                else:
                    _log.warning("ANCSBackend: StartNotify failed for %s: %s", name, exc)

        if any_in_progress:
            self._subscribe_pending = True
            GLib.timeout_add(1500, self._on_device_connected, device_path)
            return

        if notify_ok < 2:
            _log.warning(
                "ANCSBackend: StartNotify succeeded on %d/2 chars — ANCS unavailable",
                notify_ok,
            )
            if self._service is not None:
                self._service.set_capability("ancs", False)
            return

        self._notif_src_path = notif_src_path
        self._data_src_path = data_src_path
        self._bus.add_signal_receiver(
            self._on_notif_source_changed,
            signal_name="PropertiesChanged",
            dbus_interface=_PROPS_IFACE,
            path=notif_src_path,
        )
        self._bus.add_signal_receiver(
            self._on_data_source_changed_handler,
            signal_name="PropertiesChanged",
            dbus_interface=_PROPS_IFACE,
            path=data_src_path,
        )

        # Optimistic ACTIVE entry — corrected to HEALING if Notifying=False at 500ms
        if self._service is not None:
            self._service.set_capability("ancs", True)
        _log.info(
            "ANCSBackend: StartNotify done on %s — validating Notifying in 500 ms",
            device_path,
        )
        GLib.timeout_add(500, self._check_notifying_after_subscribe)

    def _on_data_source_changed_handler(self, iface, changed, invalidated) -> None:
        self._on_data_source_changed(changed)

    def _on_device_disconnected(self) -> None:
        if self._health_check_id is not None:
            GLib.source_remove(self._health_check_id)
            self._health_check_id = None
        if self._heal_timer_id is not None:
            GLib.source_remove(self._heal_timer_id)
            self._heal_timer_id = None
        if self._backlog_timer_id is not None:
            GLib.source_remove(self._backlog_timer_id)
            self._backlog_timer_id = None
        self._backlog_suppress = False
        self._subscribe_pending = False
        if self._bus is not None:
            if self._notif_src_path:
                try:
                    self._bus.remove_signal_receiver(
                        self._on_notif_source_changed,
                        signal_name="PropertiesChanged",
                        dbus_interface=_PROPS_IFACE,
                        path=self._notif_src_path,
                    )
                except Exception as exc:
                    _log.debug("ANCSBackend: remove NotifSource receiver: %s", exc)
            if self._data_src_path:
                try:
                    self._bus.remove_signal_receiver(
                        self._on_data_source_changed_handler,
                        signal_name="PropertiesChanged",
                        dbus_interface=_PROPS_IFACE,
                        path=self._data_src_path,
                    )
                except Exception as exc:
                    _log.debug("ANCSBackend: remove DataSource receiver: %s", exc)
        self._notif_src_path = None
        self._data_src_path = None
        self._data_buffer.clear_all()
        self._uid_meta.clear()
        self._control_point_proxy = None
        if self._service is not None:
            self._service.set_capability("ancs", False)
        _log.info("ANCSBackend: device disconnected")

    # ------------------------------------------------------------------
    # Lifecycle: Notifying validation, health check, HEALING, FALLBACK
    # ------------------------------------------------------------------

    def _verify_notifying(self, path: str) -> bool:
        try:
            p = dbus.Interface(self._bus.get_object("org.bluez", path), _PROPS_IFACE)
            return bool(p.Get(_GATT_CHAR_IFACE, "Notifying"))
        except Exception:
            return False

    def _check_notifying_after_subscribe(self) -> bool:
        """500 ms post-StartNotify Notifying poll (CHECK state)."""
        if self._bus is None or self._notif_src_path is None or self._data_src_path is None:
            return GLib.SOURCE_REMOVE
        if (self._verify_notifying(self._notif_src_path) and
                self._verify_notifying(self._data_src_path)):
            _log.info("ANCSBackend: Notifying=True on both chars — ACTIVE confirmed")
            if self._service is not None and hasattr(self._service, "set_ancs_status"):
                self._service.set_ancs_status("active")
            self._health_check_id = GLib.timeout_add(30_000, self._health_check)
            self._backlog_suppress = True
            self._backlog_timer_id = GLib.timeout_add(2_000, self._end_backlog_suppress)
        else:
            _log.warning("ANCSBackend: Notifying=False after StartNotify — entering HEALING")
            self._enter_healing()
        return GLib.SOURCE_REMOVE

    def _end_backlog_suppress(self) -> bool:
        self._backlog_suppress = False
        self._backlog_timer_id = None
        _log.debug("ANCSBackend: backlog suppression window ended — new notifications active")
        return GLib.SOURCE_REMOVE

    def _health_check(self) -> bool:
        """30 s health check while ACTIVE; reschedules on pass, enters HEALING on fail."""
        if self._bus is None or self._notif_src_path is None or self._data_src_path is None:
            self._health_check_id = None
            return GLib.SOURCE_REMOVE
        if (self._verify_notifying(self._notif_src_path) and
                self._verify_notifying(self._data_src_path)):
            _log.debug("ANCSBackend: health check OK")
            return GLib.SOURCE_CONTINUE
        _log.warning("ANCSBackend: health check — Notifying=False — entering HEALING")
        self._health_check_id = None
        self._enter_healing()
        return GLib.SOURCE_REMOVE

    def _enter_healing(self) -> None:
        """Enter HEALING state: clear capability, cancel health check, start heal timer."""
        if self._service is not None:
            self._service.set_capability("ancs", False)
            if hasattr(self._service, "set_ancs_status"):
                self._service.set_ancs_status("healing")
        if self._health_check_id is not None:
            GLib.source_remove(self._health_check_id)
            self._health_check_id = None
        if self._heal_timer_id is not None:
            GLib.source_remove(self._heal_timer_id)
            self._heal_timer_id = None
        if self._backlog_timer_id is not None:
            GLib.source_remove(self._backlog_timer_id)
            self._backlog_timer_id = None
        self._backlog_suppress = False
        self._heal_attempts = 0
        self._heal_timer_id = GLib.timeout_add(5_000, self._attempt_le_rearm)
        _log.warning("ANCSBackend: HEALING — max 3 attempts at 5 s each")

    def _attempt_le_rearm(self) -> bool:
        """HEALING body — check if Notifying was externally restored; else try again.

        Active rearm strategy is SPIKE-TBD (tincan-jr96). This method detects
        when iOS independently restores Notifying=True (e.g., user re-opened the
        app) and transitions back to ACTIVE without needing an explicit rearm call.
        """
        if (self._heal_timer_id is not None and
                self._notif_src_path and self._data_src_path and
                self._verify_notifying(self._notif_src_path) and
                self._verify_notifying(self._data_src_path)):
            _log.info("ANCSBackend: HEALING → ACTIVE (Notifying restored)")
            self._heal_timer_id = None
            self._heal_attempts = 0
            if self._service is not None:
                self._service.set_capability("ancs_needs_repair", False)
                self._service.set_capability("ancs", True)
                if hasattr(self._service, "set_ancs_status"):
                    self._service.set_ancs_status("active")
            self._health_check_id = GLib.timeout_add(30_000, self._health_check)
            return GLib.SOURCE_REMOVE

        # SPIKE-TBD: insert hardware-validated rearm strategy here when spike is complete
        self._heal_attempts += 1
        _log.warning(
            "ANCSBackend: HEALING attempt %d/3 — SPIKE-TBD: no rearm strategy confirmed",
            self._heal_attempts,
        )
        if self._heal_attempts >= 3:
            self._heal_timer_id = None
            self._enter_fallback()
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def _enter_fallback(self) -> None:
        """Enter FALLBACK: all healing attempts exhausted, wizard intervention required."""
        if self._service is not None:
            self._service.set_capability("ancs_needs_repair", True)
            if hasattr(self._service, "set_ancs_status"):
                self._service.set_ancs_status("fallback")
        _log.warning(
            "ANCSBackend: FALLBACK — LE ANCS link could not be re-armed after 3 attempts; "
            "wizard tap-to-reconnect required",
        )

    def request_heal(self) -> None:
        """GUI-triggered re-entry into HEALING from FALLBACK (Try-to-Reconnect button)."""
        if self._service is not None:
            self._service.set_capability("ancs_needs_repair", False)
        self._heal_attempts = 0
        self._enter_healing()

    def _on_notif_source_changed(self, interface, changed, invalidated):
        if "Value" not in changed:
            return
        try:
            parsed = parse_notification_source(bytes(changed["Value"]))
        except ValueError as exc:
            _log.debug("ANCSBackend: parse_notification_source error: %s", exc)
            return
        if parsed["event_id"] != 0:
            return
        uid = parsed["notification_uid"]
        self._uid_meta[uid] = (parsed["category_id"], parsed["event_flags"])
        self._data_buffer.clear(uid)
        if self._control_point_proxy is None:
            return
        cmd = build_get_attrs_cmd(
            uid, [ATTR_APP_ID, ATTR_TITLE, ATTR_SUBTITLE, ATTR_MESSAGE, ATTR_DATE]
        )
        try:
            self._control_point_proxy.WriteValue(list(cmd), {})
        except dbus.exceptions.DBusException as exc:
            _log.warning("ANCSBackend: WriteValue(ControlPoint) failed: %s", exc)
            exc_msg = str(exc).lower()
            if "not connected" in exc_msg or "att" in exc_msg:
                # LE link dropped — clear proxy immediately to stop retry spam
                self._control_point_proxy = None
                _log.warning("ANCSBackend: LE link drop on write — entering HEALING")
                self._enter_healing()

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
        self._uid_meta.pop(uid, None)  # consume to prevent memory leak
        if self._backlog_suppress:
            _log.debug("ANCSBackend: backlog suppress — dropping uid=%d", uid)
            return
        app_id = attrs.get(ATTR_APP_ID, "")
        if self._service is None:
            return
        if app_id == "com.apple.MobileSMS":
            # SMS path — unchanged
            self._service.on_message_received({
                "conversation_id": app_id,
                "body": attrs.get(ATTR_MESSAGE, ""),
                "from": attrs.get(ATTR_TITLE, ""),
                "direction": "inbound",
                "status": "unread",
                "timestamp": "",
            })
        else:
            # All other app notifications (WhatsApp, Calendar, Mail, etc.)
            if hasattr(self._service, "on_app_notification_received"):
                self._service.on_app_notification_received({
                    "app_id": app_id,
                    "title": attrs.get(ATTR_TITLE, ""),
                    "subtitle": attrs.get(ATTR_SUBTITLE, ""),
                    "body": attrs.get(ATTR_MESSAGE, ""),
                    "date": attrs.get(ATTR_DATE, ""),
                    "direction": "inbound",
                    "status": "unread",
                })
