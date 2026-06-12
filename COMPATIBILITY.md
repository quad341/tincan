# Bluetooth Adapter Compatibility

Verified test results for HFP call audio, SCO, ANCS, and MAP on Fedora 44 with BlueZ 5.86 and PipeWire 1.6.4+.

## Quick reference

| Adapter | MAP (SMS) | ANCS notifications | HFP call control | SCO call audio |
|---|---|---|---|---|
| RTL8761B / ASUS USB-BT500 | ✅ | ✅ | ✅ | ✅ (CVSD; see notes) |
| MediaTek MT7925 (built-in) | ✅ | ❌ | ✅ | ❌ (firmware) |

## RTL8761B — ASUS USB-BT500

**USB ID:** `0b05:1bf6` | **BT MAC:** `A0:AD:9F:7A:15:8E` | **BlueZ hci1**

Tested 2026-06-11 on Fedora 44 (iPhone iOS 26.x via oFono + WirePlumber + PipeWire).

| Feature | Status | Notes |
|---|---|---|
| MAP / SMS messaging | ✅ Working | Send + receive + MAP body fetch |
| ANCS app notifications | ✅ Working | LE solicitation advertising works reliably |
| HFP call control | ✅ Working | Dial, answer, hangup; oFono SLC established |
| SCO call audio (CVSD) | ✅ Working | 2-way audio confirmed; see requirements below |
| SCO call audio (mSBC) | ⚠️ Untested | oFono negotiated CVSD; mSBC not yet attempted |

**Requirements for SCO call audio:**

1. **SELinux policy** — load `tincan_hfp_sco.te` (shipped in package; auto-loaded by `%post`). Without it, `dbus-broker` silently drops the SCO fd under Enforcing and oFono disconnects. See `docs/hfp-sco-selinux-rootcause.md`.

2. **USB autosuspend off** — the dongle's USB autosuspend causes "corrupted SCO packet" garbling. Disable it:
   ```bash
   # Temporary (per-boot):
   echo on > /sys/bus/usb/devices/3-2.4/power/control
   # Durable (udev rule — installed by tincand):
   /etc/udev/rules.d/52-tincan-usb-bt500-no-autosuspend.rules
   ```

3. **oFono as HFP backend** — WirePlumber must be configured with `bluez5.hfphsp-backend = "ofono"` and restarted **before** oFono starts. If oFono starts first, BlueZ rejects its `RegisterProfile` ("UUID already registered") and the HFP modem stays offline.

## MediaTek MT7925 (built-in)

**BT MAC:** `50:2E:91:1A:87:01` | **BlueZ hci0** | **USB ID:** `13d3:3608`

| Feature | Status | Notes |
|---|---|---|
| MAP / SMS messaging | ✅ Working | Classic Bluetooth OBEX; fully functional |
| ANCS app notifications | ❌ Not working | `RegisterAdvertisement` returns NoReply — controller does not acknowledge the LE advertising HCI command reliably |
| HFP call control | ✅ Working | SLC + RFCOMM signaling path proven |
| SCO call audio | ❌ Not working | Kernel: "SCO/ACL packet for unknown connection handle 0xE00" — firmware-level failure; no bluez_input/bluez_output PipeWire nodes ever created |

This adapter is **disabled by default** on the reference setup (udev rule `/etc/udev/rules.d/99-disable-builtin-mt7925-bt.rules`). If you only need MAP + SMS (no calls, no ANCS), re-enable it by removing the rule.

## Tested configuration

- **OS:** Fedora 44, Linux 7.x
- **BlueZ:** 5.86
- **PipeWire:** 1.6.4+
- **oFono:** system service with WirePlumber ofono-backend
- **iPhone:** iOS 26.x
- **ANCS:** requires `bluetoothd --experimental` (SolicitUUIDs support)

## Unsupported configurations

- **Bluetooth headset relay** (headset → computer → iPhone bridge): requires two simultaneous SCO links on a single controller; most chips support only one SCO link at a time. Would need two BT adapters — not supported.
