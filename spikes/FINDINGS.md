# Phase-0 Spike Findings

Resolved during implementation; recorded here retroactively on 2026-07-04
(the answers previously lived only inline in PLAN.md §5–6).
Reference device: iPhone / iOS 26.x
Reference host: Fedora 44, BlueZ 5.86, PipeWire

## OQ-1: SMS bodies over MAP?

[x] Yes / [ ] No / [ ] Partial

Notes: `GetMessage` returns the full body text. `ListMessages('inbox', {})`
works directly — no `SetFolder`/`ListFolders` needed — and returns up to ~10
recent messages per session. Validated by `m01_map.py` against real hardware.

## OQ-2: iMessage content over MAP?

[x] Present (TYPE=`sms-gsm`) / [ ] Absent / [ ] Indeterminate

Notes: iMessage threads appear in the MAP inbox listing; iOS rebrands the
`TYPE` field to `sms-gsm`. Full body available via `GetMessage`. Outbound
`PushMessage` also works, and iOS auto-upgrades SMS→iMessage for iMessage
contacts (OQ-SEND).

## OQ-3: ANCS fires for Messages with sender on iOS 26.x?

[x] Yes / [ ] No / [ ] Partial (sender missing)

Notes: validated in live use, with sender attribution. Requires
`bluetoothd --experimental` and a BlueZ with the ext-adv length fix —
BlueZ ≤ 5.86 breaks all LE advertising on kernels ≥ 7.0; see
`docs/ancs-bluez-ext-adv-rootcause.md` and the patch in `docs/`.
Approach used: [ ] ancs4linux wrapper  [x] direct GATT (`ANCSBackend`)

## OQ-4: Built-in MediaTek adapter holds simultaneous BLE + Classic?

[ ] Yes (stable 60+ s) / [x] No / [ ] Intermittent

Notes: the MT7925 fails ANCS advertising (`RegisterAdvertisement` NoReply)
and SCO call audio (firmware, "unknown connection handle 0xE00"). The
ASUS USB-BT500 (RTL8761B) is the reference adapter for MAP+ANCS+HFP/SCO
simultaneously; the built-in is disabled by default via udev. See
`COMPATIBILITY.md`.

## OQ-5: MMS / image-attachment bytes over MAP? (m05_mms_attachment.py)

[x] Absent for RCS/iMessage images   [ ] Untested for true carrier MMS

Date: 2026-06-29. Device iPhone / iOS 26.x via RTL8761B (hci1), BlueZ 5.86.

iOS surfaces RCS/iMessage image texts in the MAP inbox as **Type=sms-gsm** with
Subject "Attachment: 1 Image" — NOT Type=MMS. Fetching one via
Message1.Get(..., attachment=True) returns a 398-byte bMessage whose entire body is
the literal text "Attachment: 1 Image": no MIME multipart, no Content-Type: image/*,
no base64, no SMIL. The image bytes are NOT retrievable over MAP — they ride Apple's
RCS/iMessage IP stack (LIMITATIONS.md is correct).

Implications:
- Inbound media is effectively unreachable for the common modern case (RCS/iMessage).
- The daemon's MMS-attachment path (poll_inbox gates _fetch_raw_bmsg(attachment=True)
  on Type=="MMS"; _parse_mms_content extracts image/* parts) does NOT fire on real iOS
  RCS/iMessage traffic, which is typed sms-gsm. It is verified only by synthetic-MIME
  unit tests. Whether a true carrier MMS (green-bubble, Type=MMS) delivers bytes is
  still untested — needs an image from a non-iMessage / non-RCS sender.
- Achievable UX: surface a placeholder (e.g. "📷 Image") from the "Attachment: N Image"
  subject so the user knows a picture was sent, even though it can't be shown.

Re-run: stop tincand, then
  DEVICE_ADDR=<phone-mac> PYTHONPATH=<repo-root> python spikes/m05_mms_attachment.py

## OQ-6: Group MMS send over MAP?

[x] Not possible — iOS delivers to the first recipient only

Date: 2026-06-29. iPhone / iOS 26.x via RTL8761B (hci1), BlueZ 5.86.

Probed by pushing a TYPE:MMS bMessage with two recipient VCARDs via
MapBackend.send_group_message(). Two layers had hidden this:

1. A real bug: send_group_message called obexd PushMessage with 2 args
   (sourcefile, args), but the signature is `ssa{sv}` — (sourcefile, FOLDER, args).
   It raised TypeError before anything left the host. That is why group send
   "instantly failed." The mocked unit tests passed because they mock PushMessage
   and never exercised the real arg count — the path was never tested against real
   obexd/iOS.
2. With the call corrected to PushMessage(tmp, "outbox", {}) (mirroring the working
   1:1 send), obexd + iOS ACCEPTED the multi-recipient push (transfer completed) —
   but iOS delivered ONLY to the first recipient VCARD, as a 1:1. The second
   recipient received nothing and no group thread was created.

Conclusion: group MMS send is not possible over MAP on iOS (matches Phone Link).
With no way to reply to a group either, group participation over Bluetooth is out.
Decision 2026-06-29: remove the group surface; surface inbound group messages as
1:1 by sender.

## Amendments to PLAN.md

- R2 realized in the strong form: the built-in adapter is unusable for
  ANCS and SCO — a known-good USB dongle is required reference hardware,
  not just a fallback (`COMPATIBILITY.md`).
- IPC decision confirmed: D-Bus session service `im.tincan.Daemon`.
- New hard requirement added as design principle 5 (2026-07-04): echo-free
  call audio (AEC) is release-gated — without it the calls stack is moot.
