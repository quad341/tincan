#!/usr/bin/env python3
"""M0.5 — does iOS deliver MMS image *bytes* over MAP?

Reuses the daemon's own MapBackend. The obexd/iOS/BlueZ-version quirks — CreateSession
(not the old Connect), telecom/msg navigation, the post-5.66 Message1.Get fetch (GetMessage
was removed), and the transfer-vanish race — are all already solved there; reimplementing
them from scratch is exactly how the m01 spike went stale. We connect, list the inbox, and
for the chosen MMS dump the RAW bMessage so we can see exactly what iOS hands us:
    image/* parts with base64 bytes  ->  we can receive media
    a reference / SMIL only          ->  structure, no picture
    text only                        ->  media not delivered over MAP
We also run the daemon's own _parse_mms_content() over the raw bytes — if it yields
attachments, the receive path already works end-to-end.

PREREQS
  * Stop tincand first so this owns the MAP session:  systemctl --user stop tincand
    (and restart after:  systemctl --user start tincand)
  * A RECENT image message in the inbox (MAP exposes only a recent window).
  * NOTE: RCS / iMessage may not traverse MAP at all (see docs/LIMITATIONS.md). If the
    inbox shows no MMS, the definitive media test needs a green-bubble (SMS/MMS) image
    from a non-iMessage contact.

USAGE
  DEVICE_ADDR=AA:BB:CC:DD:EE:FF PYTHONPATH=<repo-root> python spikes/m05_mms_attachment.py
  # optional: target a specific message path (MSG_PATH) shown in the listing above
  DEVICE_ADDR=...  MSG_PATH=...  python spikes/m05_mms_attachment.py

This spike intentionally reaches into MapBackend internals (_msg_access, _retry,
_fetch_raw_bmsg) — it is a diagnostic, not production code.
"""
import os
import re
import sys

import dbus
import dbus.mainloop.glib

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

from tincand.backends.bluez_map import MapBackend, _parse_mms_content  # noqa: E402

DEVICE_ADDR = os.environ.get("DEVICE_ADDR") or (sys.argv[1] if len(sys.argv) > 1 else None)
if not DEVICE_ADDR:
    print("Set DEVICE_ADDR=AA:BB:CC:DD:EE:FF (your iPhone's BT MAC; or pass as argv[1])")
    raise SystemExit(2)
WANT_PATH = os.environ.get("MSG_PATH")  # optional: force-fetch a specific message path

backend = MapBackend(message_store=None)
print(f"Connecting MAP to {DEVICE_ADDR} ...")
backend.connect(DEVICE_ADDR)  # CreateSession + iOS consent handling
try:
    ma = backend._msg_access
    # Navigate telecom/msg exactly like poll_inbox does.
    for _ in range(2):
        try:
            ma.SetFolder("")
        except dbus.exceptions.DBusException:
            pass
    backend._retry(ma.SetFolder, "telecom")
    backend._retry(ma.SetFolder, "msg")
    inbox = backend._retry(ma.ListMessages, "inbox", {})  # dict: path -> props

    items = list(inbox.items())
    print(f"\n--- MAP Inbox ({len(items)} messages) ---")
    # An "attachment candidate" is anything that might carry media: a real MMS type,
    # OR an sms-gsm message whose Subject is iOS's "Attachment: N Image" placeholder
    # (iOS types image texts as sms-gsm, so a Type==MMS filter misses them entirely).
    candidates = []  # (path, type, subject)
    for path, props in items:
        mtype = str(props.get("Type", "?"))
        subj = str(props.get("Subject", "?"))
        is_cand = mtype.upper() == "MMS" or bool(
            re.search(r"attachment|image", subj, re.IGNORECASE)
        )
        flag = "  <-- attachment candidate" if is_cand else ""
        sender = props.get("Sender", "?")
        print(f"  {path}")
        print(f"      Type={mtype}  Sender={sender}  Subject={subj[:48]!r}{flag}")
        if is_cand:
            candidates.append((str(path), mtype, subj))

    if not items:
        print("\nINBOX EMPTY — is 'Show Notifications' enabled for this device on the iPhone?")
        raise SystemExit(1)

    if WANT_PATH:
        target = WANT_PATH
        print(f"\nUsing MSG_PATH override: {target}")
    elif candidates:
        target, ctype, csubj = candidates[0]
        print(f"\nAuto-selected attachment candidate: {target}")
        print(f"   Type={ctype}  Subject={csubj!r}")
    else:
        print("\nNo MMS or attachment-subject message in the inbox. If your image arrived via")
        print("RCS/iMessage it may not surface over MAP at all (docs/LIMITATIONS.md).")
        raise SystemExit(1)

    print("\nFetching raw bMessage with attachment=True ...")
    raw = backend._fetch_raw_bmsg(target, attachment=True)
    if raw is None:
        print("Fetch returned None (transfer failed or handle was skipped).")
        raise SystemExit(1)

    saved = f"/tmp/tincan-mms-{re.sub(r'[^A-Za-z0-9]', '', target)[-16:]}.bmsg"
    with open(saved, "w") as fh:
        fh.write(raw)

    print(f"\n=== RAW bMESSAGE ({len(raw)} bytes) — full copy at {saved} ===")
    print(raw[:2000])
    if len(raw) > 2000:
        print(f"... [display truncated; full {len(raw)} chars in {saved}] ...")

    # Run the daemon's OWN parser — if it extracts attachments, receive works end-to-end.
    body, attachments = _parse_mms_content(raw)
    print("\n=== daemon _parse_mms_content() ===")
    print(f"  body: {body[:120]!r}")
    print(f"  attachments extracted: {len(attachments)}")
    for i, att in enumerate(attachments):
        nbytes = len(att["data"]) * 3 // 4
        print(f"    [{i}] {att['mime_type']}  {len(att['data'])} b64 chars (~{nbytes} bytes)")

    has_img = bool(re.search(r"Content-Type:\s*image/", raw, re.IGNORECASE))
    has_smil = bool(re.search(r"application/smil", raw, re.IGNORECASE))
    print("\n=== ANALYSIS ===")
    print(f"  image/* MIME part: {has_img}   application/smil: {has_smil}   "
          f"parser attachments: {len(attachments)}")

    if attachments:
        verdict = ("(a) IMAGE BYTES PRESENT — iOS delivers media over MAP and the daemon already "
                   "captures it. Next: confirm the GUI surfaces it.")
    elif has_img:
        verdict = ("(b) image/* part present but the parser extracted no bytes — a reference/"
                   "placeholder, or an encoding the parser misses. Inspect the dump.")
    elif has_smil:
        verdict = ("(b/c) SMIL structure but no image part/bytes — the picture was not delivered "
                   "over MAP.")
    else:
        verdict = ("(c) TEXT ONLY — no media in the bMessage. Confirm this was actually an MMS "
                   "image (not SMS or an RCS/iMessage that bypassed MAP).")
    print(f"\n  VERDICT: {verdict}")
    print(f"  Eyeball {saved} to confirm.")
finally:
    backend.disconnect()
    print("\nMAP session removed.  (Restart the daemon:  systemctl --user start tincand)")
