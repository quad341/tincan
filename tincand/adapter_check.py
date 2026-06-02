"""Detect whether the active Bluetooth adapter supports LE advertising."""
from __future__ import annotations

import logging

import dbus

_log = logging.getLogger(__name__)

CAPABLE = "CAPABLE"
NOT_CAPABLE = "NOT_CAPABLE"
ADAPTER_ABSENT = "ADAPTER_ABSENT"

_BLUEZ_SERVICE = "org.bluez"
_OBJ_MGR_IFACE = "org.freedesktop.DBus.ObjectManager"
_LE_ADV_MGR_IFACE = "org.bluez.LEAdvertisingManager1"


def detect_adapter_le_capability(adapter_path: str = "/org/bluez/hci0", bus=None) -> str:
    """Query BlueZ for LE advertising capability on adapter_path.

    Returns CAPABLE, NOT_CAPABLE, or ADAPTER_ABSENT.
    Pass a mock bus to test without hardware.
    """
    if bus is None:
        bus = dbus.SystemBus()

    try:
        bluez_root = bus.get_object(_BLUEZ_SERVICE, "/")
        obj_mgr = dbus.Interface(bluez_root, _OBJ_MGR_IFACE)
        objects = obj_mgr.GetManagedObjects()
    except dbus.DBusException as exc:
        _log.warning("BlueZ ObjectManager unavailable (%s): %s", adapter_path, exc)
        return ADAPTER_ABSENT

    if adapter_path not in objects:
        _log.warning(
            "Adapter %s not in BlueZ managed objects → %s", adapter_path, ADAPTER_ABSENT
        )
        return ADAPTER_ABSENT

    result = CAPABLE if _LE_ADV_MGR_IFACE in objects[adapter_path] else NOT_CAPABLE
    _log.info("Adapter %s via %s → %s", adapter_path, _LE_ADV_MGR_IFACE, result)
    return result


def check_adapter_le_capable(adapter_path: str = "/org/bluez/hci0", bus=None) -> bool:
    """Return True iff the adapter supports LE advertising."""
    return detect_adapter_le_capability(adapter_path, bus) == CAPABLE
