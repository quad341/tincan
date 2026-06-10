# ANCS notifications fail on Fedora kernel 7.0 — root cause: a BlueZ bug in extended-advertising marshalling

**Status:** Root cause **PROVEN** and the fix **VERIFIED end-to-end** (2026-06-10).
**Severity:** All BlueZ D-Bus LE advertising fails → ANCS (iOS notifications) cannot
start, on every adapter. Messaging/contacts (MAP/PBAP) are unaffected.
**Blame:** A latent **BlueZ** bug, newly exposed by a correct **kernel security fix**.
Not tincan, not the Bluetooth adapter.

## Symptom

`org.bluez.LEAdvertisingManager1.RegisterAdvertisement` fails with
`org.bluez.Error.Failed` for *any* advertisement, on both the built-in MediaTek
MT7925 (hci0) and the ASUS USB-BT500 / RTL8761B dongle (hci1). tincan's ANCS
backend logs `RegisterAdvertisement failed` and the iPhone never connects as an
ANCS consumer, so zero app notifications. Kernel/bluez logs show:

```
src/advertising.c:add_client_complete() Failed to add advertisement: Invalid Parameters (0x0d)
```

## Root cause (proven)

On the controllers here (which support LE Extended Advertising) BlueZ uses the
extended MGMT flow: `Add Extended Advertising Parameters (0x0054)` then
`Add Extended Advertising Data (0x0055)`. btmon shows `0x0054` **succeeds** and
`0x0055` is rejected with **Invalid Parameters (0x0d)** — and critically, the
`0x0055` command is sent with **`plen=37`** while it declares
`adv_data_len=18 + scan_rsp_len=8` (which, with the 3-byte header, is **29**).

The 8-byte overshoot is a BlueZ bug. In `bluez-5.86/src/advertising.c`, the
`MGMT_OP_ADD_EXT_ADV_DATA` sender computes the command length with the **wrong
struct**:

```c
struct mgmt_cp_add_ext_adv_data *cp = NULL;      /* the extended struct (3 bytes) */
...
param_len = sizeof(struct mgmt_cp_add_advertising) + adv_data_len + scan_rsp_len;
                    /* ^ legacy struct = 11 bytes — WRONG, should be the ext struct */
```

`mgmt_cp_add_advertising` (legacy) is 11 bytes; `mgmt_cp_add_ext_adv_data` is 3.
`11 − 3 = 8` → every `0x0055` command is 8 bytes too long (the buffer is
`malloc0`'d, so the stray bytes are zero). It is a copy-paste from the legacy
`Add Advertising (0x003e)` sender a few hundred lines above, which *correctly*
uses `mgmt_cp_add_advertising`.

### Why it broke now (the kernel side is correct)

The Linux kernel recently added **"Bluetooth: MGMT: validate Add Extended
Advertising Data length"** — a security fix for an info-leak (a length-mismatched
`0x0055` could make `add_ext_adv_data()` read out of bounds; KASAN reports an
8-byte slab-out-of-bounds read). It now rejects any command where
`len != sizeof(hdr) + adv_data_len + scan_rsp_len`. That correctly rejects
BlueZ's 8-byte-too-long command. Older kernels (e.g. 6.19) ignored the trailing
bytes, so advertising "worked" despite the latent bug. The host here runs
**kernel 7.0.11-200.fc44 + bluez-5.86**, the combination that exposes it.

## Proof chain

1. **btmon:** BlueZ sends `0x0055` with `plen=37`, declaring `18 + 8`.
2. **Raw MGMT probe** (bypasses BlueZ): the kernel **accepts** correctly-sized
   commands (`plen=29` full, `plen=3` empty, adv-only, scan-only, tiny) and
   **rejects only** the `+8` oversized one (`plen=37`) — exactly mimicking BlueZ.
3. **Source:** `advertising.c` uses `sizeof(struct mgmt_cp_add_advertising)`
   instead of the extended struct.
4. **Struct sizes:** legacy 11 vs extended 3 = 8 (the overshoot).
5. **Upstream:** BlueZ `master` already uses `param_len = sizeof(*cp)` (correct).
6. **End-to-end:** built bluez-5.86 with the one-line fix; with the patched
   `bluetoothd`, `RegisterAdvertisement` **succeeds** for every variant
   (full / solicit / minimal / localname) — vs all "Failed" on stock 5.86.

## The fix (one line)

```diff
--- a/src/advertising.c
+++ b/src/advertising.c
@@ -1487,7 +1487,7 @@
-	param_len = sizeof(struct mgmt_cp_add_advertising) + adv_data_len +
+	param_len = sizeof(struct mgmt_cp_add_ext_adv_data) + adv_data_len +
 							scan_rsp_len;
```

Patch file: [`bluez-5.86-fix-ext-adv-data-len.patch`](bluez-5.86-fix-ext-adv-data-len.patch).
This matches upstream BlueZ master.

## How to enable ANCS on this host

- **Recommended:** rebuild the `bluez-5.86` SRPM with the patch and
  `dnf install` the result (or update to a BlueZ release that includes the fix
  once Fedora ships it). Then reconnect the iPhone and ANCS advertising works.
- **Do NOT** "fix" it by booting kernel 6.19 — that only works because the older
  kernel lacks the info-leak length-validation, i.e. it reintroduces the
  security hole. The proper fix is the BlueZ patch.

## Upstream reporting (optional)

- **bluez/bluez:** `src/advertising.c` `MGMT_OP_ADD_EXT_ADV_DATA` sender uses
  `sizeof(struct mgmt_cp_add_advertising)` for `param_len`; should be the
  extended struct (fixed in master). Affects bluez-5.86 on kernels with the
  Add-Ext-Adv-Data length validation.

## Environment

Fedora 44, kernel `7.0.11-200.fc44`, `bluez-5.86-4.fc44`, dbus-broker.
Controllers: MediaTek MT7925 (hci0), RTL8761B / ASUS USB-BT500 (hci1).
Probe tool used: a raw MGMT socket sender (`mgmt_ext_adv.py`).
