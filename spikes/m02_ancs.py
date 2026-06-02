#!/usr/bin/env python3
"""M0.2 — ANCS notification receive (correct GATT consumer model). Answers OQ-3.

Architecture: iPhone IS the GATT server; Linux IS the GATT consumer.
Do NOT register a local GattApplication for the ANCS UUID — that was backwards.

Flow:
  1. Register NoInputNoOutput pairing agent (enables LE bond + iOS access grant).
  2. Register SolicitUUIDs=[ANCS_SERVICE_UUID] advertisement via LEAdvertisingManager1.
  3. Wait for PropertiesChanged: Device1.Connected=True.
  4. Call Device1.Pair() if not already bonded.
  5. Enumerate BlueZ's view of iPhone GATT services via ObjectManager.
  6. Find Notification Source / Control Point / Data Source char paths.
  7. StartNotify on Notification Source and Data Source.
  8. On Notification Source value: parse 8-byte LE packet; filter category 4/6;
     write GetNotifAttrs to Control Point.
  9. On Data Source value: accumulate TLV; parse; print sender/preview.

Run:
    sudo python spikes/m02_ancs.py --device XX:XX:XX:XX:XX:XX
    # (sudo needed to register GATT agent on system bus)

Requirements:
    pip install dbus-python (already a tincand dep)
    Bluetooth service running: systemctl start bluetooth
    No ancs4linux required.
"""
from __future__ import annotations

import argparse
import os
import signal
import sys

import dbus
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib

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

# ---------------------------------------------------------------------------
# D-Bus constants
# ---------------------------------------------------------------------------

_GATT_CHAR_IFACE = "org.bluez.GattCharacteristic1"
_LE_ADV_IFACE = "org.bluez.LEAdvertisement1"
_PROPS_IFACE = "org.freedesktop.DBus.Properties"
_OBJ_MANAGER_IFACE = "org.freedesktop.DBus.ObjectManager"
_LE_ADV_MANAGER_IFACE = "org.bluez.LEAdvertisingManager1"
_AGENT_MANAGER_IFACE = "org.bluez.AgentManager1"
_AGENT_IFACE = "org.bluez.Agent1"
_DEVICE_IFACE = "org.bluez.Device1"
_ADAPTER_IFACE = "org.bluez.Adapter1"

_ADV_PATH = "/org/tincan/m02/advertisement0"
_AGENT_PATH = "/org/tincan/m02/agent"

# ---------------------------------------------------------------------------
# Pairing agent — NoInputNoOutput, auto-accept
# ---------------------------------------------------------------------------


class _PairingAgent(dbus.service.Object):
    CAPABILITY = "NoInputNoOutput"

    def __init__(self, bus: dbus.Bus) -> None:
        super().__init__(bus, _AGENT_PATH)

    @dbus.service.method(_AGENT_IFACE, in_signature="o", out_signature="s")
    def RequestPinCode(self, device): return "0000"  # noqa: E704

    @dbus.service.method(_AGENT_IFACE, in_signature="o", out_signature="u")
    def RequestPasskey(self, device): return dbus.UInt32(0)  # noqa: E704

    @dbus.service.method(_AGENT_IFACE, in_signature="ouq")
    def DisplayPasskey(self, device, passkey, entered): pass  # noqa: E704

    @dbus.service.method(_AGENT_IFACE, in_signature="ou")
    def RequestConfirmation(self, device, passkey): pass  # noqa: E704

    @dbus.service.method(_AGENT_IFACE, in_signature="o")
    def RequestAuthorization(self, device): pass  # noqa: E704

    @dbus.service.method(_AGENT_IFACE, in_signature="os")
    def AuthorizeService(self, device, uuid): pass  # noqa: E704

    @dbus.service.method(_AGENT_IFACE)
    def Cancel(self): pass  # noqa: E704

    @dbus.service.method(_AGENT_IFACE)
    def Release(self): pass  # noqa: E704


# ---------------------------------------------------------------------------
# SolicitUUIDs advertisement — NOT ServiceUUIDs (Linux is the consumer)
# ---------------------------------------------------------------------------


class _SolicitAdvertisement(dbus.service.Object):
    def __init__(self, bus: dbus.Bus) -> None:
        super().__init__(bus, _ADV_PATH)
        self._props = {
            "Type": dbus.String("peripheral"),
            "SolicitUUIDs": dbus.Array([ANCS_SERVICE_UUID], signature="s"),
            "LocalName": dbus.String("TincanANCS"),
        }

    @dbus.service.method(_PROPS_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):  # noqa: N802
        if interface == _LE_ADV_IFACE:
            return dbus.Dictionary(self._props, signature="sv")
        raise dbus.exceptions.DBusException(name="org.freedesktop.DBus.Error.InvalidArgs")

    @dbus.service.method(_LE_ADV_IFACE)
    def Release(self):  # noqa: N802
        pass


# ---------------------------------------------------------------------------
# Main spike runner
# ---------------------------------------------------------------------------


def run(device_addr: str | None) -> None:
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    loop = GLib.MainLoop()

    # Find the BlueZ adapter
    obj_mgr = dbus.Interface(bus.get_object("org.bluez", "/"), _OBJ_MANAGER_IFACE)
    objects = obj_mgr.GetManagedObjects()
    adapter_path = next(
        (str(p) for p, ifaces in objects.items() if _ADAPTER_IFACE in ifaces), None
    )
    if adapter_path is None:
        sys.exit("ERROR: No BlueZ adapter found. Is bluetooth running?")
    print(f"Adapter: {adapter_path}")

    # 1. Register pairing agent
    agent = _PairingAgent(bus)  # noqa: F841
    try:
        agent_mgr = dbus.Interface(bus.get_object("org.bluez", "/org/bluez"), _AGENT_MANAGER_IFACE)
        agent_mgr.RegisterAgent(_AGENT_PATH, _PairingAgent.CAPABILITY)
        agent_mgr.RequestDefaultAgent(_AGENT_PATH)
        print("Pairing agent registered (NoInputNoOutput)")
    except dbus.exceptions.DBusException as exc:
        print(f"Warning: RegisterAgent failed (may already exist): {exc}")

    # 2. Register SolicitUUIDs advertisement (NOT ServiceUUIDs — we are the consumer)
    adv = _SolicitAdvertisement(bus)  # noqa: F841
    adv_mgr = None
    try:
        adv_mgr = dbus.Interface(
            bus.get_object("org.bluez", adapter_path), _LE_ADV_MANAGER_IFACE
        )
        adv_mgr.RegisterAdvertisement(_ADV_PATH, {})
        print(f"SolicitUUIDs advertisement registered: {ANCS_SERVICE_UUID}")
    except dbus.exceptions.DBusException as exc:
        sys.exit(f"ERROR: RegisterAdvertisement failed: {exc}")

    # State
    data_buffer = ANCSDataBuffer()
    control_point_proxy = [None]  # list so inner functions can rebind

    # 5. Data Source: accumulate TLV + parse
    def on_data_source_changed(iface, changed, invalidated):
        if "Value" not in changed:
            return
        chunk = bytes(changed["Value"])
        if len(chunk) < 5:
            return
        import struct
        uid = struct.unpack_from("<L", chunk, 1)[0]
        complete = data_buffer.accumulate(uid, chunk)
        if complete is None:
            return
        try:
            result = parse_data_source(complete)
        except Exception as exc:
            print(f"ERROR: parse_data_source failed (uid={uid}): {exc}")
            data_buffer.clear(uid)
            return
        data_buffer.clear(uid)
        attrs = result.get("attrs", {})
        app_id = attrs.get(ATTR_APP_ID, "")
        title = attrs.get(ATTR_TITLE, "")
        message = attrs.get(ATTR_MESSAGE, "")
        print(f"\n--- ANCS Notification (uid={uid}) ---")
        print(f"  AppID:   {app_id}")
        print(f"  Title:   {title}  (sender)")
        print(f"  Message: {message}")
        if app_id == "com.apple.MobileSMS":
            sender_ok = bool(title and title != "iPhone")
            answer = "YES" if sender_ok else "PARTIAL (sender missing)"
            print(f"\n--- OQ-3: ANCS fires for Messages with sender? {answer} ---")

    # 4. Notification Source: parse 8-byte header, filter, write Control Point
    def on_notif_source_changed(iface, changed, invalidated):
        if "Value" not in changed:
            return
        try:
            parsed = parse_notification_source(bytes(changed["Value"]))
        except ValueError as exc:
            print(f"Warning: parse_notification_source: {exc}")
            return
        print(
            f"NotifSource: event={parsed['event_id']} cat={parsed['category_id']} "
            f"({parsed['category']}) uid={parsed['notification_uid']}"
        )
        if parsed["event_id"] != 0 or parsed["category_id"] not in (4, 6):
            return
        uid = parsed["notification_uid"]
        data_buffer.clear(uid)
        ctrl = control_point_proxy[0]
        if ctrl is None:
            return
        cmd = build_get_attrs_cmd(uid, [ATTR_APP_ID, ATTR_TITLE, ATTR_MESSAGE])
        try:
            ctrl.WriteValue(list(cmd), {})
            print(f"GetNotifAttrs written for uid={uid}")
        except dbus.exceptions.DBusException as exc:
            print(f"Warning: WriteValue(ControlPoint) failed: {exc}")

    # 3. Device connected: pair + find ANCS chars + StartNotify
    def on_device_connected(device_path: str) -> None:
        print(f"\nDevice connected: {device_path}")

        # Check device address filter
        if device_addr:
            try:
                dev_iface = dbus.Interface(
                    bus.get_object("org.bluez", device_path), _DEVICE_IFACE
                )
                addr = str(dev_iface.Get(_DEVICE_IFACE, "Address"))
            except dbus.exceptions.DBusException as exc:
                print(f"Warning: cannot read device address: {exc}")
                return
            if addr.upper() != device_addr.upper():
                print(f"  Ignoring {addr} (filter: {device_addr})")
                return
            print(f"  Device address matches: {addr}")

        # Pair / bond
        try:
            dev_iface = dbus.Interface(
                bus.get_object("org.bluez", device_path), _DEVICE_IFACE
            )
            bonded = bool(dev_iface.Get(_DEVICE_IFACE, "Bonded"))
            if not bonded:
                print("  Requesting LE bond (will trigger iOS notification access prompt)…")
                dev_iface.Pair()
                print("  LE bond established")
            else:
                print("  Already bonded")
        except dbus.exceptions.DBusException as exc:
            print(f"  Warning: Pair() failed: {exc}")
            print("  Continuing anyway (may already be bonded)")

        # Enumerate GATT objects on iPhone's device path
        all_objects = obj_mgr.GetManagedObjects()
        notif_src = ctrl_pt = data_src = None
        for path, ifaces in all_objects.items():
            if _GATT_CHAR_IFACE not in ifaces:
                continue
            if not str(path).startswith(str(device_path)):
                continue
            uuid = str(ifaces[_GATT_CHAR_IFACE].get("UUID", "")).upper()
            if uuid == NOTIF_SOURCE_UUID.upper():
                notif_src = str(path)
            elif uuid == CONTROL_POINT_UUID.upper():
                ctrl_pt = str(path)
            elif uuid == DATA_SOURCE_UUID.upper():
                data_src = str(path)

        if not all((notif_src, ctrl_pt, data_src)):
            print(
                f"  ANCS service not found on {device_path}\n"
                "  (iOS may not have granted notification access yet;\n"
                "   check iPhone Bluetooth settings and accept the prompt if shown)"
            )
            return

        print(f"  NotifSource: {notif_src}")
        print(f"  ControlPoint: {ctrl_pt}")
        print(f"  DataSource:   {data_src}")

        # Store ControlPoint proxy
        control_point_proxy[0] = dbus.Interface(
            bus.get_object("org.bluez", ctrl_pt), _GATT_CHAR_IFACE
        )

        # StartNotify on NotifSource and DataSource
        for path, name in ((notif_src, "NotifSource"), (data_src, "DataSource")):
            try:
                char = dbus.Interface(bus.get_object("org.bluez", path), _GATT_CHAR_IFACE)
                char.StartNotify()
                print(f"  StartNotify OK: {name}")
            except dbus.exceptions.DBusException as exc:
                print(f"  Warning: StartNotify failed for {name}: {exc}")

        # Subscribe to PropertiesChanged on the iPhone's chars
        bus.add_signal_receiver(
            on_notif_source_changed,
            signal_name="PropertiesChanged",
            dbus_interface=_PROPS_IFACE,
            path=notif_src,
        )
        bus.add_signal_receiver(
            on_data_source_changed,
            signal_name="PropertiesChanged",
            dbus_interface=_PROPS_IFACE,
            path=data_src,
        )
        print("  Subscribed to ANCS characteristics — waiting for notifications…")

    def on_properties_changed(iface, changed, invalidated, path=None):
        if iface != _DEVICE_IFACE:
            return
        if "Connected" in changed:
            if changed["Connected"]:
                on_device_connected(str(path))
            else:
                print(f"\nDevice disconnected: {path}")
                control_point_proxy[0] = None
                data_buffer._buffers.clear()

    bus.add_signal_receiver(
        on_properties_changed,
        signal_name="PropertiesChanged",
        dbus_interface=_PROPS_IFACE,
        path_keyword="path",
    )

    def cleanup(*_: object) -> None:
        print("\nShutting down…")
        if adv_mgr is not None:
            try:
                adv_mgr.UnregisterAdvertisement(_ADV_PATH)
            except dbus.exceptions.DBusException:
                pass
        try:
            agent_mgr.UnregisterAgent(_AGENT_PATH)
        except dbus.exceptions.DBusException:
            pass
        loop.quit()

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    filter_msg = f" (filter: {device_addr})" if device_addr else " (any device)"
    print(f"\nListening for ANCS device connection{filter_msg}…")
    print("Send an SMS to the iPhone to trigger a notification.")
    print("Ctrl+C to stop\n")
    loop.run()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="M0.2 ANCS spike — correct GATT consumer model",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--device",
        default=os.environ.get("DEVICE_ADDR"),
        metavar="ADDR",
        help="Bluetooth device address to filter on (or set DEVICE_ADDR env var)",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    run(args.device)


if __name__ == "__main__":
    main()
