#!/usr/bin/env python3
"""M0.2 — ANCS notification receive. Answers OQ-3.
Primary: ancs4linux daemons. Fallback: direct GATT (see below).

Run: DEVICE_ADDR=xx:xx:xx:xx:xx:xx python spikes/m02_ancs.py
"""
import os
import signal
import subprocess
import sys
import time

import dbus
import dbus.mainloop.glib
from gi.repository import GLib

DEVICE_ADDR = os.environ["DEVICE_ADDR"]

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
session_bus = dbus.SessionBus()
loop = GLib.MainLoop()

# 1. Start ancs4linux daemons
procs = []
for daemon in ("advertising", "observer"):
    p = subprocess.Popen(
        ["python", "-m", f"ancs4linux.{daemon}"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    procs.append(p)
    print(f"Started ancs4linux.{daemon} (pid={p.pid})")


def cleanup(*_):
    for p in procs:
        p.terminate()
    sys.exit(0)


signal.signal(signal.SIGINT, cleanup)
time.sleep(2)   # allow daemons to register D-Bus names

# 2. Connect to ancs4linux D-Bus observer interface
# ancs4linux observer registers: se.mobiledevices.ancs4linux.observer;
# confirm with: busctl --user list | grep ancs
try:
    observer = session_bus.get_object(
        "se.mobiledevices.ancs4linux.observer",
        "/se/mobiledevices/ancs4linux/observer",
    )
    notifications_iface = dbus.Interface(
        observer, "se.mobiledevices.ancs4linux.Observer1"
    )
    print("ancs4linux observer D-Bus object found")
except dbus.exceptions.DBusException as e:
    print(f"Could not connect to ancs4linux observer: {e}")
    print("Check: busctl --user list | grep ancs")
    print("If daemons fail to start, use the direct GATT fallback below.")
    cleanup()


# 3. Subscribe to notification signal
def on_notification_received(uid, app_id, title, message, subtitle=""):
    print("\n--- ANCS Notification ---")
    print(f"  UID:      {uid}")
    print(f"  AppID:    {app_id}")
    print(f"  Title:    {title}")
    print(f"  Message:  {message}")
    print(f"  Subtitle: {subtitle}")
    if app_id == "com.apple.MobileSMS":
        sender_present = bool(title and title != "iPhone")
        print(f"\n--- OQ-3: ANCS fires for Messages with sender? "
              f"{'YES' if sender_present else 'PARTIAL (sender missing)'} ---")


# Connect to whatever signal ancs4linux observer emits
# (Inspect with dbus-monitor after starting; exact signal name may vary by version)
session_bus.add_signal_receiver(
    on_notification_received,
    signal_name="NotificationReceived",
    dbus_interface="se.mobiledevices.ancs4linux.Observer1",
    bus_name="se.mobiledevices.ancs4linux.observer",
)

print("\nWaiting for ANCS notifications — send an SMS to the iPhone now...")
print("Ctrl+C to stop\n")
loop.run()


# ============================================================
# FALLBACK: Direct GATT (use only if ancs4linux daemons fail)
# ============================================================
# Uncomment the block below and run as a separate script if the
# ancs4linux approach above fails to start or connect.
#
# ANCS UUIDs
# ANCS_SERVICE_UUID   = "7905F431-B5CE-4E99-A40F-4B1E122D00D6"
# NOTIF_SOURCE_UUID   = "9FBF120D-6301-42D9-8C58-25E699A21DBD"
# CONTROL_POINT_UUID  = "69D1D8F3-45E1-49A8-9821-9BBDFDAAD9D9"
# DATA_SOURCE_UUID    = "22EAC6E9-24D6-4BB5-BE44-B36ACE7C7BFB"
#
# ANCS attribute IDs
# ATTR_APP_ID = 0; ATTR_TITLE = 1; ATTR_MESSAGE = 3
#
# Full direct GATT requires registering a GattApplication via
# org.bluez.GattManager1 so BlueZ accepts the BLE connection from the iPhone.
# ~80 lines of dbus.service.Object subclasses for GattApplication,
# GattService, GattCharacteristic:
#
# 1. Register minimal GATT application:
#    manager = dbus.Interface(system_bus.get_object("org.bluez", adapter_path),
#                             "org.bluez.GattManager1")
#    manager.RegisterApplication(app_path, {})
#
# 2. Enable BLE advertising so iPhone initiates connection:
#    adv_manager = dbus.Interface(..., "org.bluez.LEAdvertisingManager1")
#    adv_manager.RegisterAdvertisement(adv_path, {})
#
# 3. On DeviceConnected, find ANCS service in GATT attribute table:
#    org.bluez.GattService1 with UUID == ANCS_SERVICE_UUID
#
# 4. Enable notifications on Notification Source (write CCCD 0x0100):
#    char.StartNotify()
#
# 5. on_notification_source_changed(value):
#    event_id, event_flags, category_id, category_count, notif_uid = \
#        struct.unpack("<BBBBL", bytes(value))
#    if event_id == 0 and category_id in (6, 4):  # Social or IncomingCall
#        cmd = struct.pack("<BL", 0, notif_uid)  # CommandGetNotificationAttributes
#        for attr_id in [ATTR_APP_ID, ATTR_TITLE, ATTR_MESSAGE]:
#            if attr_id in [ATTR_TITLE, ATTR_MESSAGE]:
#                cmd += struct.pack("<BH", attr_id, 255)
#            else:
#                cmd += struct.pack("<B", attr_id)
#        control_point_char.WriteValue(list(cmd), {})
#
# 6. on_data_source_changed(value):
#    Parse TLV: command_id(1), notif_uid(4), then [attr_id(1), len(2), value(len)]
#    Extract AppIdentifier, Title, Message — print same format as primary approach
