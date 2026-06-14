"""Detect Bluetooth adapter capabilities: LE advertising and HFP/SCO support."""
from __future__ import annotations

import logging
import pathlib
import re

import dbus

_log = logging.getLogger(__name__)

CAPABLE = "CAPABLE"
NOT_CAPABLE = "NOT_CAPABLE"
ADAPTER_ABSENT = "ADAPTER_ABSENT"

_BLUEZ_SERVICE = "org.bluez"
_OBJ_MGR_IFACE = "org.freedesktop.DBus.ObjectManager"
_LE_ADV_MGR_IFACE = "org.bluez.LEAdvertisingManager1"
_ADAPTER_IFACE = "org.bluez.Adapter1"

_ADAPTER_PATH_RE = re.compile(r"^/org/bluez/hci\d+$")
_USB_MODALIAS_RE = re.compile(r"^usb:v([0-9A-Fa-f]{4})p([0-9A-Fa-f]{4})")

# Known HFP/SCO capable/incapable USB adapters (vendor_id, product_id) -> bool.
# Non-USB adapters or unknown IDs return None (capability unknown).
_HFP_SCO_USB_CAPABLE: dict[tuple[str, str], bool] = {
    ("0bda", "8761"): True,  # Realtek RTL8761B (e.g. ASUS USB-BT500) — confirmed HFP/SCO working
}


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


def detect_adapter_hfp_sco_capability(modalias: str) -> bool | None:
    """Detect HFP/SCO capability from a USB modalias string.

    Returns True (known capable), False (known incapable), or None (unknown/non-USB).
    """
    if not modalias:
        return None
    m = _USB_MODALIAS_RE.match(modalias)
    if not m:
        return None
    vid, pid = m.group(1).lower(), m.group(2).lower()
    return _HFP_SCO_USB_CAPABLE.get((vid, pid))


def _read_modalias(hci_name: str) -> str:
    """Read the USB modalias for a bluetooth HCI device from sysfs."""
    try:
        return pathlib.Path(f"/sys/class/bluetooth/{hci_name}/device/modalias").read_text().strip()
    except OSError:
        return ""


def list_adapters(bus=None) -> list[dict]:
    """Enumerate all BlueZ adapters with capability info.

    Makes exactly ONE GetManagedObjects() call. Returns [] if BlueZ is unavailable.
    Each dict has: path, alias, address, powered, hfp_sco_capable, le_capable.
    """
    if bus is None:
        bus = dbus.SystemBus()

    try:
        bluez_root = bus.get_object(_BLUEZ_SERVICE, "/")
        obj_mgr = dbus.Interface(bluez_root, _OBJ_MGR_IFACE)
        objects = obj_mgr.GetManagedObjects()
    except dbus.DBusException as exc:
        _log.warning("BlueZ ObjectManager unavailable: %s", exc)
        return []

    adapters = []
    for path, interfaces in objects.items():
        if not _ADAPTER_PATH_RE.match(str(path)):
            continue
        adapter_props = interfaces.get(_ADAPTER_IFACE, {})
        if not adapter_props:
            continue

        hci_name = str(path).rsplit("/", 1)[-1]
        modalias = _read_modalias(hci_name)

        adapters.append({
            "path": str(path),
            "alias": str(adapter_props.get("Alias", adapter_props.get("Name", ""))),
            "address": str(adapter_props.get("Address", "")),
            "powered": bool(adapter_props.get("Powered", False)),
            "hfp_sco_capable": detect_adapter_hfp_sco_capability(modalias),
            "le_capable": _LE_ADV_MGR_IFACE in interfaces,
        })

    return adapters
