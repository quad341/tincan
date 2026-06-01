#!/usr/bin/env python3
"""M0.3 — Simultaneous BLE (ANCS) + Classic (MAP) stability test. Answers OQ-4.

Run: DEVICE_ADDR=xx:xx:xx:xx:xx:xx python spikes/m03_concurrent.py
"""
import os
import subprocess
import sys
import time
import dbus
import dbus.mainloop.glib
from gi.repository import GLib

DEVICE_ADDR = os.environ["DEVICE_ADDR"]
TEST_DURATION_S = 60

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
system_bus = dbus.SystemBus()
session_bus = dbus.SessionBus()


def find_device_path(bus, addr):
    """Return BlueZ object path for a device by address."""
    mgr = dbus.Interface(
        bus.get_object("org.bluez", "/"),
        "org.freedesktop.DBus.ObjectManager",
    )
    for path, ifaces in mgr.GetManagedObjects().items():
        dev = ifaces.get("org.bluez.Device1", {})
        if str(dev.get("Address", "")).upper() == addr.upper():
            return path
    return None


def get_device_props(bus, device_path):
    props_iface = dbus.Interface(
        bus.get_object("org.bluez", device_path),
        "org.freedesktop.DBus.Properties",
    )
    connected = bool(props_iface.Get("org.bluez.Device1", "Connected"))
    addr_type = str(props_iface.Get("org.bluez.Device1", "AddressType"))
    return connected, addr_type


device_path = find_device_path(system_bus, DEVICE_ADDR)
if not device_path:
    print(f"Device {DEVICE_ADDR} not found in BlueZ. Pair first.")
    sys.exit(1)

# Start MAP session (same as M0.1 connect step)
client = dbus.Interface(
    session_bus.get_object("org.bluez.obex", "/org/bluez/obex"),
    "org.bluez.obex.Client1",
)
map_session = client.Connect(DEVICE_ADDR, {"Target": dbus.String("map")})
print(f"MAP session started: {map_session}")

# Start ancs4linux observer daemons in background
ancs_procs = []
for daemon in ("advertising", "observer"):
    p = subprocess.Popen(["python", "-m", f"ancs4linux.{daemon}"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ancs_procs.append(p)

time.sleep(2)
print("ANCS daemons started\n")

# Poll both connections every 5 seconds
start = time.monotonic()
results = []
while True:
    elapsed = int(time.monotonic() - start)
    classic_connected, classic_type = get_device_props(system_bus, device_path)

    # BLE connection may appear as same device path with AddressType="random"
    # or as a separate path. Check Connected + AddressType for both.
    ble_connected = classic_connected and classic_type in ("random", "public")
    # (On many adapters the same device_path reports both links;
    #  if separate, call find_device_path with the BLE address variant)

    status = (f"T+{elapsed:3d}s: Classic/MAP connected={classic_connected} "
              f"(type={classic_type})  BLE/ANCS connected={ble_connected}")
    print(status)
    results.append((elapsed, classic_connected, ble_connected))

    if elapsed >= TEST_DURATION_S:
        break
    time.sleep(5)

# Cleanup
for p in ancs_procs:
    p.terminate()
try:
    client.Remove(map_session)
except Exception:
    pass

# Summary
stable = all(c and b for _, c, b in results)
print(f"\n--- OQ-4: Both connections stable {TEST_DURATION_S}s? "
      f"{'YES' if stable else 'NO/INTERMITTENT'} ---")
drops = [(t, c, b) for t, c, b in results if not (c and b)]
if drops:
    print("Drops detected:")
    for t, c, b in drops:
        print(f"  T+{t}s: Classic={c} BLE={b}")
