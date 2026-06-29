# Phase-0 Spike Findings

Date: <ISO date>
Reference device: iPhone <model> / iOS <version>
Reference host: <uname -r>, BlueZ <version>

## OQ-1: SMS bodies over MAP?

[ ] Yes / [ ] No / [ ] Partial

Notes:

## OQ-2: iMessage content over MAP?

[ ] Present (TYPE=<value>) / [ ] Absent / [ ] Indeterminate

Notes:

## OQ-3: ANCS fires for Messages with sender on iOS 26.5?

[ ] Yes / [ ] No / [ ] Partial (sender missing)

Notes:
Approach used: [ ] ancs4linux wrapper  [ ] direct GATT

## OQ-4: Built-in MediaTek adapter holds simultaneous BLE + Classic?

[ ] Yes (stable 60+ s) / [ ] No / [ ] Intermittent

Notes:

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

## Amendments to PLAN.md

List any assumptions that need revision.
