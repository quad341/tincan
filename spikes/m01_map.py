#!/usr/bin/env python3
"""M0.1 — MAP inbox list and body fetch. Answers OQ-1, OQ-2."""
import os
import re
import time
import dbus
import dbus.mainloop.glib
from gi.repository import GLib

DEVICE_ADDR = os.environ["DEVICE_ADDR"]   # e.g. "AA:BB:CC:DD:EE:FF"

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
system_bus = dbus.SystemBus()
session_bus = dbus.SessionBus()
loop = GLib.MainLoop()

# 1. Get obex.Client1 on the SESSION bus (obexd lives on session bus)
client = dbus.Interface(
    session_bus.get_object("org.bluez.obex", "/org/bluez/obex"),
    "org.bluez.obex.Client1",
)

# 2. Connect MAP session
session_path = client.Connect(
    DEVICE_ADDR,
    {"Target": dbus.String("map")},
)
print(f"MAP session: {session_path}")

# 3. Get MessageAccess1 at the session path
msg_access = dbus.Interface(
    session_bus.get_object("org.bluez.obex", session_path),
    "org.bluez.obex.MessageAccess1",
)

# 4. Navigate to inbox
msg_access.SetFolder("inbox")

# 5. List messages (metadata only, no bodies)
messages = msg_access.ListMessages("", {})
print(f"\n--- MAP Inbox ({len(messages)} messages) ---")
for handle, props in messages:
    print(f"  Handle: {handle}  Type: {props.get('Type', '?')}  "
          f"Sender: {props.get('Sender', '?')}  "
          f"Datetime: {props.get('Datetime', '?')}  "
          f"Read: {props.get('Read', '?')}")

if not messages:
    print("INBOX EMPTY — verify 'Show Notifications' is enabled on iPhone")
    raise SystemExit(1)

# 6. Fetch the first message body
first_handle, first_props = messages[0]

# GetMessage triggers an OBEX GET; obexd writes the bMessage to a temp file
transfer_path, transfer_props = msg_access.GetMessage(
    first_handle,
    {"Attachment": dbus.Boolean(False)},
)
print(f"\nTransfer: {transfer_path}  Initial status: {transfer_props.get('Status', '?')}")

# 7. Get Transfer1 proxy and watch PropertiesChanged
transfer_obj = session_bus.get_object("org.bluez.obex", transfer_path)
transfer_props_iface = dbus.Interface(transfer_obj, "org.freedesktop.DBus.Properties")

result = {}


def on_properties_changed(interface, changed, invalidated):
    if "Status" in changed:
        status = str(changed["Status"])
        print(f"  Transfer status → {status}")
        if status == "complete":
            result["filename"] = str(transfer_props_iface.Get(
                "org.bluez.obex.Transfer1", "Filename"
            ))
            loop.quit()
        elif status == "error":
            print("  ERROR: transfer failed")
            loop.quit()


transfer_obj.connect_to_signal(
    "PropertiesChanged",
    on_properties_changed,
    dbus_interface="org.freedesktop.DBus.Properties",
)

# 8. Run MainLoop — blocks until transfer completes or errors
GLib.timeout_add_seconds(30, lambda: (print("TIMEOUT waiting for transfer"), loop.quit(), False)[2])
loop.run()


# 9. Parse bMessage file (RFC 5322-like format)
def parse_bmessage(path):
    """Return dict with keys: type, sender, body, folder."""
    try:
        text = open(path).read()
    except FileNotFoundError:
        return {"type": "ERROR", "sender": "?", "body": "FILE NOT FOUND", "folder": "?"}

    def field(name):
        m = re.search(rf"^{name}:(.+)$", text, re.MULTILINE | re.IGNORECASE)
        return m.group(1).strip() if m else "?"

    # Extract body between BEGIN:BBODY…END:BBODY
    body_m = re.search(
        r"BEGIN:BBODY.*?^(?:LENGTH:\d+\s*)?(.+?)END:BBODY",
        text, re.DOTALL | re.MULTILINE | re.IGNORECASE,
    )
    body = body_m.group(1).strip() if body_m else "?"

    # Sender: prefer FN from vCard, fall back to TEL
    fn_m = re.search(r"^FN:(.+)$", text, re.MULTILINE)
    tel_m = re.search(r"^TEL:(.+)$", text, re.MULTILINE)
    sender = (fn_m.group(1).strip() if fn_m
              else (tel_m.group(1).strip() if tel_m else "?"))

    return {
        "type": field("TYPE"),
        "sender": sender,
        "body": body,
        "folder": field("FOLDER"),
    }


# 10. Print results
filename = result.get("filename")
if filename:
    msg = parse_bmessage(filename)
    print(f"\n--- Fetched Message ---")
    print(f"  TYPE:   {msg['type']}")
    print(f"  FOLDER: {msg['folder']}")
    print(f"  SENDER: {msg['sender']}")
    print(f"  BODY:   {msg['body'][:200]}")

    # OQ findings
    oq1 = "YES" if msg["body"] not in ("?", "") else "NO"
    oq2 = ("PRESENT" if "imessage" in msg["type"].lower()
           else ("INDETERMINATE" if msg["type"] == "?" else "ABSENT"))
    print(f"\n--- OQ-1: SMS body non-empty?      {oq1} ---")
    print(f"--- OQ-2: iMessage type in MAP?    {oq2} (TYPE={msg['type']}) ---")

    # 11. Clean up temp file
    try:
        os.unlink(filename)
    except OSError:
        pass

# 12. Optional PushMessage sub-test (uncomment to run):
# test_to = os.environ.get("SEND_TO")   # target phone number
# if test_to:
#     bmsg_path = "/tmp/test_out.bmsg"
#     with open(bmsg_path, "w") as f:
#         f.write(
#             "BEGIN:BMESSAGE\r\nVERSION:1.0\r\nSTATUS:UNREAD\r\nTYPE:SMS_GSM\r\n"
#             "FOLDER:telecom/msg/outbox\r\nBEGIN:BENV\r\nBEGIN:VCARD\r\n"
#             f"VERSION:3.0\r\nFN:{test_to}\r\nTEL:{test_to}\r\n"
#             "END:VCARD\r\nBEGIN:BBODY\r\nCHARSET:UTF-8\r\n"
#             "Hello from tincan M0.1 spike\r\n"
#             "END:BBODY\r\nEND:BENV\r\nEND:BMESSAGE\r\n"
#         )
#     push_transfer_path, _ = msg_access.PushMessage(bmsg_path, "outbox", {})
#     print(f"\n--- PushMessage transfer: {push_transfer_path} ---")
#     # Watch transfer status (same pattern as GetMessage above)
