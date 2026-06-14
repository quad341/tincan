# Spike Execution Protocol: SCO Audio Validation on RTL8761B (tincan-xy2sb)

_Architect: tincan/architect · 2026-06-07 · Updated 2026-06-09 (reference HW confirmed: ASUS USB-BT500 dongle; WP config path/format fixed; gdbus bus flag fixed; oFono in Fedora repos)_

---

## Purpose

Validate that SCO/mSBC audio works end-to-end on a known-good USB BT adapter
before any HFP call-control code is written. The spike has five acceptance
criteria (S1–S5, from PRD §Spike Prerequisite) and three open questions
(OQ-4a/4b/4c). All implementation work is gated on this spike passing.

**Executor:** tincan/investigator (hardware access required)  
**Reference: tincan-iaf2m** (architect framework, closed)  
**Blocks:** tincan-xohrx (finalize architecture), tincan-fx79v.* (design beads)

---

## Hard Prerequisites (verify before starting)

| # | Check | Command |
|---|-------|---------|
| P1 | ASUS USB-BT500 (RTL8761B) dongle is plugged in | `lsusb \| grep -i 'realtek'` — expect 0b05:1bf6 on ASUS USB-BT500 |
| P2 | Dongle (hci1) is the active default HCI adapter | `bluetoothctl show` — expect controller A0:AD:9F:7A:15:8E; hci0 = built-in MT7925 (leave enabled but not active) |
| P3 | Paired iPhone connected to dongle | `bluetoothctl devices` — confirm your iPhone is Paired:yes Trusted:yes on dongle controller |
| P4 | oFono installed | `ofonod --version` or `which ofonod` |
| P5 | PipeWire running | `pw-cli --version` |
| P6 | WirePlumber running | `wpctl status` |

If P4 (oFono) is not installed on Fedora:
```bash
sudo dnf install ofono          # ofono-2.19-2.fc44 available in Fedora 44 default repos
sudo systemctl enable --now ofono
```
**OQ-1 answered:** Fedora default repo (dnf), no COPR or source build required.

WirePlumber HFP config (create if absent — WP 0.5.x SPA-JSON format, NOT the old Lua form):
```bash
mkdir -p ~/.config/wireplumber/wireplumber.conf.d/
cat > ~/.config/wireplumber/wireplumber.conf.d/50-bluez-ofono.conf <<'EOF'
monitor.bluez.properties = {
  bluez5.hfphsp-backend = "ofono"
}
EOF
systemctl --user restart wireplumber
```
Verified working path: `/home/jaword/.config/wireplumber/wireplumber.conf.d/50-bluez-ofono.conf`

---

## S5 First: Confirm Adapter Identity

Before any other test — verify ASUS USB-BT500 dongle is the active default controller.

```bash
lsusb | grep -i realtek
# Expected: Bus xxx Device yyy: ID 0b05:1bf6 ASUSTek Computer, Inc. Bluetooth Adapter
bluetoothctl show
# Expected: Controller A0:AD:9F:7A:15:8E  roglet #2  [default]
# (hci0 = built-in MT7925; hci1 = ASUS dongle — leave both enabled; dongle must be default)
```

Do NOT disable the built-in MT7925 (hci0). The dongle (hci1) must be the default; confirm via `[default]` in `bluetoothctl show`.

Record:
```
S5 adapter: ASUS USB-BT500 RTL8761B (0b05:1bf6) confirmed as default? [PASS/FAIL]
bluetoothctl show controller MAC:
```

---

## S1: oFono Discovers iPhone as HFP Modem

```bash
sudo systemctl start ofono  # or: sudo ofonod -d &
sleep 3

# If iPhone not already connected:
bluetoothctl connect <IPHONE_MAC>
sleep 2

# Check modems
gdbus call -y -d org.ofono -o / -m org.ofono.Manager.GetModems
```

**Pass condition:** output contains a modem object with `Type: hfp` (not `hci` which
is a local modem). Example:
```
([objectpath '/hfp/org/bluez/hci1/dev_XX_XX_XX_XX_XX_XX', {'Online': <true>, 'Type': <'hfp'>, ...}],)
```

If no HFP modem appears after 5 s of BT connect, also check:
```bash
gdbus call -y -d org.ofono -o / -m org.ofono.Manager.GetModems
dbus-monitor --system "type=signal,sender=org.ofono"
```

Record:
```
S1 result: [PASS/FAIL]
GetModems output:
```

---

## S2 + S3 + S4: Audio During a Live Call

These three criteria are validated during an actual phone call. Set up `pw-cli`
monitoring BEFORE answering/placing the call.

### Terminal 1 — PipeWire monitor
```bash
pw-cli ls -m  # list nodes; re-run after call starts
# Or live:
pw-mon
```

### Terminal 2 — oFono call watch
```bash
dbus-monitor --system "type=signal,interface=org.ofono.VoiceCallManager"
dbus-monitor --system "type=signal,interface=org.ofono.VoiceCall"
```

### Terminal 3 — PipeWire log (for codec)
```bash
journalctl -f -u pipewire --since now | grep -iE 'codec|msbc|cvsd|lc3|sco|hfp'
```

### Place/receive a call

```bash
# Option A: Call the phone from somewhere (incoming on iPhone → desktop)
# Option B: Dial out from oFono
MODEM_PATH=$(gdbus call -y -d org.ofono -o / -m org.ofono.Manager.GetModems \
  | grep -oP "'/[^']+'(?=.*Type.*hfp)" | head -1)
gdbus call -y -d org.ofono -o "$MODEM_PATH" -m org.ofono.VoiceCallManager.Dial \
  "+15555551234" ""
```

### S2 check (SCO node) — run during active call:
```bash
pw-cli ls | grep -iE 'bluetooth.*sco|sco.*bluetooth|bluez.*sco'
# Expected: node with s.status=running or similar
pw-dump | python3 -c "
import sys, json
for n in json.load(sys.stdin):
    if 'sco' in str(n).lower() or 'hfp' in str(n).lower():
        print(n)
"
```

### S3 check (bidirectional audio) — manual:
- Speak into desktop microphone → confirm audible on iPhone speaker
- Speak into iPhone → confirm audible on desktop speakers
- **Record:** which direction failed if either does

### S4 check (mSBC codec):
```bash
# During active call — check PipeWire log (Terminal 3 above)
# Or:
bt-device -a <IPHONE_MAC> | grep -i codec
# Or from WirePlumber:
wpctl inspect $(wpctl status | grep -i hfp | head -1 | awk '{print $1}') | grep codec
```

**Pass condition (S4):** log or device info shows `msbc` (not `cvsd`).
If only CVSD observed: record as FAIL with note (wideband not negotiated).

Record:
```
S2 SCO node: [PASS/FAIL]
  pw-cli ls output (relevant lines):
S3 audio bidirectional: [PASS/FAIL]
  Desktop→iPhone: [OK/NO AUDIO]
  iPhone→Desktop: [OK/NO AUDIO]
S4 codec: [PASS=mSBC / FAIL=CVSD / FAIL=none seen]
  Codec log lines:
```

---

## OQ-4a: PipeWire Version

```bash
pipewire --version
pw-cli --version
```

Record: `OQ-4a: PipeWire version = X.Y.Z`

The question is whether this version was sufficient (spike passes) or what the
minimum should be documented as.

---

## OQ-4b: LC3-SWB Observed?

During the call, watch the PipeWire log (Terminal 3 from above) for `lc3` or
`LC3-SWB`. If seen: record codec negotiation log lines. If only mSBC/CVSD: record
`OQ-4b: LC3-SWB NOT observed — iPhone fell back to mSBC`.

---

## OQ-4c: WirePlumber Config Sufficient?

After the spike (pass or fail), note whether the `50-bluez-ofono.conf` config in the
prerequisite section was sufficient, or if additional WirePlumber config was
required.

Record:
```
OQ-4c: Config sufficient? [YES/NO]
Additional config applied (if any):
```

---

## What to Record in the Bead Notes

At the end of the spike, post a structured result block:

```
SPIKE RESULT — 2026-06-07

Adapter: [RTL8761B / CSR8510 / other]
oFono install method: [Fedora dnf / other]
PipeWire version: X.Y.Z

S1 oFono HFP modem: [PASS / FAIL — reason]
S2 SCO node running: [PASS / FAIL — reason]
S3 Bidirectional audio: [PASS / FAIL — Desktop→iPhone: OK/NO, iPhone→Desktop: OK/NO]
S4 mSBC codec: [PASS / FAIL — observed: mSBC/CVSD/none]
S5 RTL8761B confirmed: [PASS / FAIL]

OQ-4a PipeWire min version: X.Y.Z [sufficient / needs newer]
OQ-4b LC3-SWB: [observed / not observed — fell back to mSBC/CVSD]
OQ-4c WirePlumber config: [50-bluez-ofono.conf sufficient / additional config: ...]

OVERALL: [PASS — all 5 criteria met / FAIL — failing criteria: S1, S2, ...]
```

If OVERALL PASS → close this bead and mail tincan/architect with results.  
If OVERALL FAIL → add `needs-investigation` label, document failure details, mail tincan/architect.

---

## Common Failure Modes

| Symptom | Likely cause | Action |
|---------|-------------|--------|
| `GetModems` returns only `hci0` type modem | oFono `hfp_hf_bluez5` plugin not loaded OR iPhone not in BT range | Check `ofonod -d` output for plugin load; reconnect BT |
| SCO node never appears | WirePlumber not configured for oFono HFP backend | Verify `50-bluez-ofono.conf` in `wireplumber.conf.d/`; restart WirePlumber |
| Audio one-way only | Microphone sink not selected | `wpctl set-default-sink / set-default-source` for the BT device |
| Only CVSD, not mSBC | iPhone or BlueZ mSBC capability mismatch | Check `hciconfig hci1 features` for eSCO/mSBC bit |
| `org.ofono not found` | oFono not started | `sudo systemctl start ofono` or `sudo ofonod &` |

---

## Guardrails

- **ASUS USB-BT500 (RTL8761B) dongle is the reference HW.** Run the spike on the dongle only. If the dongle is unavailable, block the spike and mail tincan/architect. The built-in MediaTek MT7925 (hci0) may remain enabled but is not the spike target — do not report results from it as passing.
- **oFono packaging method must be recorded.** This answers OQ-1 in the PRD
  and is a blocker for the packaging bead (tincan-j9wvv).
- **Results are for the architect, not for a builder PR.** The investigator's output
  is: a spike result block in bead notes + mail to tincan/architect. No code is
  written during this spike.
