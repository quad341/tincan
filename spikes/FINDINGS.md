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

## Amendments to PLAN.md

- R2 realized in the strong form: the built-in adapter is unusable for
  ANCS and SCO — a known-good USB dongle is required reference hardware,
  not just a fallback (`COMPATIBILITY.md`).
- IPC decision confirmed: D-Bus session service `im.tincan.Daemon`.
- New hard requirement added as design principle 5 (2026-07-04): echo-free
  call audio (AEC) is release-gated — without it the calls stack is moot.
