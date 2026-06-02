#!/usr/bin/env python3
"""M0.2 — ANCS notification receive. Answers OQ-3.

Two approaches are implemented below:
  Primary:  ancs4linux daemons (easier to set up if ancs4linux is installed)
  Fallback: direct GATT via BlueZ GattManager1 + LEAdvertisingManager1

Run:
    DEVICE_ADDR=XX:XX:XX:XX:XX:XX python spikes/m02_ancs.py
    python spikes/m02_ancs.py --help

Install ancs4linux (for the primary path):
    pip install git+https://github.com/pzmarzly/ancs4linux.git
    # Or: pip install ancs4linux (if available on PyPI)
    # Signal name may vary by version — inspect with:
    # busctl --user introspect se.mobiledevices.ancs4linux.observer \
    #         /se/mobiledevices/ancs4linux/observer

Audit note (tincan-z5b): m02_ancs.py does NOT call CreateSession/RemoveSession
(those are obexd APIs, not GATT APIs). No obexd API bug applies here.
All D-Bus calls below use valid BlueZ GATT Manager and LE Advertising Manager
interfaces. The only D-Bus calls that need validation are GattManager1 and
LEAdvertisingManager1, which are system-bus BlueZ interfaces.
"""
from __future__ import annotations

import argparse
import os
import signal
import struct
import subprocess
import sys
import time

import dbus
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib

# ANCS service and characteristic UUIDs
ANCS_SERVICE_UUID = "7905F431-B5CE-4E99-A40F-4B1E122D00D6"
NOTIF_SOURCE_UUID = "9FBF120D-6301-42D9-8C58-25E699A21DBD"
CONTROL_POINT_UUID = "69D1D8F3-45E1-49A8-9821-9BBDFDAAD9D9"
DATA_SOURCE_UUID = "22EAC6E9-24D6-4BB5-BE44-B36ACE7C7BFB"

# ANCS GetNotificationAttributes attribute IDs
ATTR_APP_ID = 0
ATTR_TITLE = 1
ATTR_MESSAGE = 3

# ANCS category IDs
CATEGORY_INCOMING_CALL = 1
CATEGORY_MISSED_CALL = 2
CATEGORY_SOCIAL = 6

# Notification Source event ID
EVENT_ID_ADDED = 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="M0.2 ANCS spike — receive iOS notifications via ANCS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--device",
        default=os.environ.get("DEVICE_ADDR", ""),
        metavar="ADDR",
        help="Bluetooth device address (or set DEVICE_ADDR env var)",
    )
    parser.add_argument(
        "--direct-gatt",
        action="store_true",
        help="Use direct BlueZ GATT instead of ancs4linux (requires root / capabilities)",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Primary path: ancs4linux
# ---------------------------------------------------------------------------

def run_ancs4linux(device_addr: str) -> None:
    """Start ancs4linux daemons and subscribe to their D-Bus signal."""
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    session_bus = dbus.SessionBus()
    loop = GLib.MainLoop()

    procs: list[subprocess.Popen] = []

    def cleanup(*_: object) -> None:
        for p in procs:
            p.terminate()
        loop.quit()

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    for daemon in ("advertising", "observer"):
        p = subprocess.Popen(
            [sys.executable, "-m", f"ancs4linux.{daemon}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        procs.append(p)
        print(f"Started ancs4linux.{daemon} (pid={p.pid})")

    time.sleep(2)

    try:
        observer = session_bus.get_object(
            "se.mobiledevices.ancs4linux.observer",
            "/se/mobiledevices/ancs4linux/observer",
        )
        notifications_iface = dbus.Interface(  # noqa: F841
            observer, "se.mobiledevices.ancs4linux.Observer1"
        )
        print("ancs4linux observer D-Bus object found")
    except dbus.exceptions.DBusException as exc:
        print(f"Could not connect to ancs4linux observer: {exc}")
        print("Hint: busctl --user list | grep ancs")
        print("Try --direct-gatt for the fallback path.")
        cleanup()
        return

    def on_notification(uid: int, app_id: str, title: str, message: str, subtitle: str = "") -> None:  # noqa: E501
        print("\n--- ANCS Notification ---")
        print(f"  UID:      {uid}")
        print(f"  AppID:    {app_id}")
        print(f"  Title:    {title}")
        print(f"  Message:  {message}")
        print(f"  Subtitle: {subtitle}")
        if app_id == "com.apple.MobileSMS":
            sender_present = bool(title and title != "iPhone")
            answer = "YES" if sender_present else "PARTIAL (sender missing)"
            print(f"\n--- OQ-3: ANCS fires for Messages with sender? {answer} ---")

    session_bus.add_signal_receiver(
        on_notification,
        signal_name="NotificationReceived",
        dbus_interface="se.mobiledevices.ancs4linux.Observer1",
        bus_name="se.mobiledevices.ancs4linux.observer",
    )

    print(f"\nWaiting for ANCS notifications from {device_addr or 'any device'}…")
    print("Ctrl+C to stop\n")
    loop.run()


# ---------------------------------------------------------------------------
# Fallback path: direct GATT via BlueZ
# ---------------------------------------------------------------------------

# D-Bus paths for the GATT application and advertisement
_GATT_APP_PATH = "/org/tincan/ancs"
_GATT_SVC_PATH = f"{_GATT_APP_PATH}/service0"
_GATT_NOTIF_SRC_PATH = f"{_GATT_SVC_PATH}/char0"
_GATT_CTRL_PT_PATH = f"{_GATT_SVC_PATH}/char1"
_GATT_DATA_SRC_PATH = f"{_GATT_SVC_PATH}/char2"
_ADV_PATH = "/org/tincan/ancs/advertisement0"

_GATT_APP_IFACE = "org.bluez.GattApplication1"
_GATT_SVC_IFACE = "org.bluez.GattService1"
_GATT_CHAR_IFACE = "org.bluez.GattCharacteristic1"
_ADV_IFACE = "org.bluez.LEAdvertisement1"


class AncsApplication(dbus.service.Object):
    """Minimal GATT application to satisfy BlueZ GattManager1.RegisterApplication."""

    DBUS_IFACE = "org.bluez.GattApplication1"
    DBUS_PATH = _GATT_APP_PATH

    def __init__(self, bus: dbus.Bus) -> None:
        super().__init__(bus, self.DBUS_PATH)

    @dbus.service.method(
        "org.freedesktop.DBus.ObjectManager",
        out_signature="a{oa{sa{sv}}}",
    )
    def GetManagedObjects(self) -> dict:
        return {}


class AncsService(dbus.service.Object):
    """GATT service object exposing ANCS service UUID."""

    def __init__(self, bus: dbus.Bus) -> None:
        super().__init__(bus, _GATT_SVC_PATH)
        self._props = {
            "UUID": dbus.String(ANCS_SERVICE_UUID),
            "Primary": dbus.Boolean(True),
            "Characteristics": dbus.Array([], signature="o"),
        }

    @dbus.service.method(_GATT_SVC_IFACE, out_signature="a{sv}")
    def GetAll(self, interface: str) -> dict:  # noqa: ARG002
        return self._props


class AncsNotificationSourceChar(dbus.service.Object):
    """ANCS Notification Source characteristic — emits events for each iOS notification."""

    def __init__(self, bus: dbus.Bus, on_notify: object) -> None:
        super().__init__(bus, _GATT_NOTIF_SRC_PATH)
        self._on_notify = on_notify
        self._notifying = False

    @dbus.service.method(_GATT_CHAR_IFACE)
    def StartNotify(self) -> None:
        self._notifying = True
        print("NotificationSource: notifications enabled")

    @dbus.service.method(_GATT_CHAR_IFACE)
    def StopNotify(self) -> None:
        self._notifying = False

    @dbus.service.signal(_GATT_CHAR_IFACE, signature="ay")
    def PropertiesChanged(self, value: bytes) -> None:  # noqa: ARG002
        pass

    def handle_notification(self, value: bytes) -> None:
        """Called by BlueZ PropertiesChanged when a notification arrives."""
        if len(value) < 8:
            return
        event_id, event_flags, category_id, category_count, notif_uid = struct.unpack(
            "<BBBBL", bytes(value[:8])
        )
        print(
            f"NotifSource: event={event_id} flags={event_flags:#04x} "
            f"cat={category_id} count={category_count} uid={notif_uid}"
        )
        if event_id == EVENT_ID_ADDED and category_id in (
            CATEGORY_SOCIAL, CATEGORY_INCOMING_CALL, CATEGORY_MISSED_CALL
        ):
            self._on_notify(notif_uid)  # type: ignore[operator]


class AncsControlPointChar(dbus.service.Object):
    """ANCS Control Point — used to request notification attributes."""

    def __init__(self, bus: dbus.Bus) -> None:
        super().__init__(bus, _GATT_CTRL_PT_PATH)
        self._char_obj: object | None = None

    def set_bluez_char(self, char_obj: object) -> None:
        self._char_obj = char_obj

    def request_attributes(self, notif_uid: int) -> None:
        """Send GetNotificationAttributes for *notif_uid* to the iPhone."""
        # CommandID=0 (GetNotificationAttributes), then UID (4 bytes LE),
        # then pairs of (attr_id, max_len) for string attrs
        cmd = struct.pack("<BL", 0, notif_uid)
        cmd += struct.pack("<B", ATTR_APP_ID)
        cmd += struct.pack("<BH", ATTR_TITLE, 255)
        cmd += struct.pack("<BH", ATTR_MESSAGE, 255)

        if self._char_obj is not None:
            try:
                self._char_obj.WriteValue(list(cmd), {})  # type: ignore[attr-defined]
            except dbus.exceptions.DBusException as exc:
                print(f"ControlPoint WriteValue failed: {exc}")


class AncsDataSourceChar(dbus.service.Object):
    """ANCS Data Source — receives attribute responses from the iPhone."""

    def __init__(self, bus: dbus.Bus) -> None:
        super().__init__(bus, _GATT_DATA_SRC_PATH)

    @dbus.service.method(_GATT_CHAR_IFACE)
    def StartNotify(self) -> None:
        print("DataSource: notifications enabled")

    def handle_response(self, value: bytes) -> None:
        """Parse GetNotificationAttributes TLV response."""
        data = bytes(value)
        if len(data) < 5:
            return
        # command_id (1), notif_uid (4), then TLV entries: attr_id (1), len (2), value (len)
        command_id, notif_uid = struct.unpack("<BL", data[:5])
        if command_id != 0:
            return
        offset = 5
        attrs: dict[int, str] = {}
        while offset < len(data):
            if offset + 3 > len(data):
                break
            attr_id = data[offset]
            attr_len = struct.unpack_from("<H", data, offset + 1)[0]
            offset += 3
            if offset + attr_len > len(data):
                break
            attrs[attr_id] = data[offset : offset + attr_len].decode("utf-8", errors="replace")
            offset += attr_len

        app_id = attrs.get(ATTR_APP_ID, "")
        title = attrs.get(ATTR_TITLE, "")
        message = attrs.get(ATTR_MESSAGE, "")

        print(f"\n--- ANCS Notification (uid={notif_uid}) ---")
        print(f"  AppID:   {app_id}")
        print(f"  Title:   {title}")
        print(f"  Message: {message}")

        if app_id == "com.apple.MobileSMS":
            sender_present = bool(title and title != "iPhone")
            answer = "YES" if sender_present else "PARTIAL (sender missing)"
            print(f"\n--- OQ-3: ANCS fires for Messages with sender? {answer} ---")


class AncsAdvertisement(dbus.service.Object):
    """LE advertisement announcing this host as a Notification Consumer."""

    def __init__(self, bus: dbus.Bus) -> None:
        super().__init__(bus, _ADV_PATH)

    @dbus.service.method(_ADV_IFACE, out_signature="a{sv}")
    def GetAll(self, interface: str) -> dict:  # noqa: ARG002
        return {
            "Type": dbus.String("peripheral"),
            "ServiceUUIDs": dbus.Array([dbus.String(ANCS_SERVICE_UUID)], signature="s"),
            "LocalName": dbus.String("TincanANCS"),
        }

    @dbus.service.method(_ADV_IFACE)
    def Release(self) -> None:
        print("Advertisement released")


def run_direct_gatt(device_addr: str) -> None:
    """Register a GATT application + LE advertisement and wait for ANCS events."""
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    system_bus = dbus.SystemBus()
    loop = GLib.MainLoop()

    # Find the BlueZ adapter
    manager = dbus.Interface(
        system_bus.get_object("org.bluez", "/"),
        "org.freedesktop.DBus.ObjectManager",
    )
    objects = manager.GetManagedObjects()
    adapter_path = None
    for path, ifaces in objects.items():
        if "org.bluez.Adapter1" in ifaces:
            adapter_path = str(path)
            break
    if adapter_path is None:
        sys.exit("No BlueZ adapter found. Is bluetooth running?")

    print(f"Using adapter: {adapter_path}")

    ctrl_char = AncsControlPointChar(system_bus)

    def on_new_notification(notif_uid: int) -> None:
        ctrl_char.request_attributes(notif_uid)

    notif_src = AncsNotificationSourceChar(system_bus, on_new_notification)  # noqa: F841
    data_src = AncsDataSourceChar(system_bus)  # noqa: F841
    app = AncsApplication(system_bus)  # noqa: F841
    adv = AncsAdvertisement(system_bus)  # noqa: F841

    # Register GATT application
    gatt_manager = dbus.Interface(
        system_bus.get_object("org.bluez", adapter_path),
        "org.bluez.GattManager1",
    )
    gatt_manager.RegisterApplication(
        _GATT_APP_PATH,
        {},
        reply_handler=lambda: print("GattApplication registered"),
        error_handler=lambda e: print(f"GattApplication registration failed: {e}"),
    )

    # Register LE advertisement
    adv_manager = dbus.Interface(
        system_bus.get_object("org.bluez", adapter_path),
        "org.bluez.LEAdvertisingManager1",
    )
    adv_manager.RegisterAdvertisement(
        _ADV_PATH,
        {},
        reply_handler=lambda: print("Advertisement registered"),
        error_handler=lambda e: print(f"Advertisement registration failed: {e}"),
    )

    # Subscribe to PropertiesChanged on ANCS characteristics once device connects
    def on_properties_changed(
        iface: str,
        changed: dict,
        invalidated: list,
        sender: str = "",
        path: str = "",
    ) -> None:
        if "Value" not in changed:
            return
        value = bytes(changed["Value"])
        # Dispatch to the right handler based on object path
        if NOTIF_SOURCE_UUID.lower() in path.lower() or path == _GATT_NOTIF_SRC_PATH:
            notif_src.handle_notification(value)
        elif DATA_SOURCE_UUID.lower() in path.lower() or path == _GATT_DATA_SRC_PATH:
            data_src.handle_response(value)

    system_bus.add_signal_receiver(
        on_properties_changed,
        signal_name="PropertiesChanged",
        dbus_interface="org.freedesktop.DBus.Properties",
        path_keyword="path",
        sender_keyword="sender",
    )

    def cleanup(*_: object) -> None:
        try:
            adv_manager.UnregisterAdvertisement(_ADV_PATH)
        except dbus.exceptions.DBusException:
            pass
        try:
            gatt_manager.UnregisterApplication(_GATT_APP_PATH)
        except dbus.exceptions.DBusException:
            pass
        loop.quit()

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    print(
        f"\nWaiting for ANCS notifications from {device_addr or 'any device'}…\n"
        "Ensure the iPhone has Bluetooth enabled and is paired.\n"
        "Ctrl+C to stop\n"
    )
    loop.run()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    args = _parse_args()

    if not args.device:
        print(
            "Usage: DEVICE_ADDR=XX:XX:XX:XX:XX:XX python spikes/m02_ancs.py\n"
            "   or: python spikes/m02_ancs.py --device XX:XX:XX:XX:XX:XX\n"
            "   or: python spikes/m02_ancs.py --help\n\n"
            "No device address provided. Set DEVICE_ADDR or use --device."
        )
        sys.exit(1)

    if args.direct_gatt:
        print(f"Running direct-GATT ANCS receiver for {args.device}")
        run_direct_gatt(args.device)
    else:
        print(f"Running ancs4linux ANCS receiver for {args.device}")
        run_ancs4linux(args.device)


if __name__ == "__main__":
    main()
