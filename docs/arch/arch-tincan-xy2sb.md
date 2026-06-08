# Spike Execution Protocol: SCO Audio Validation on RTL8761B (tincan-xy2sb)

_Architect: tincan/architect · 2026-06-07_

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
| P1 | RTL8761B (ASUS USB-BT500) or CSR8510 is plugged in | `lsusb \| grep -iE 'realtek\|cambridge'` |
| P2 | RTL8761B is the active HCI adapter, NOT MediaTek | `hciconfig \| head -4` — note hci0 vs hci1 |
| P3 | iPhone paired to RTL8761B adapter | `bluetoothctl devices` shows the iPhone MAC |
| P4 | oFono installed | `ofonod --version` or `which ofonod` |
| P5 | PipeWire running | `pw-cli --version` |
| P6 | WirePlumber running | `wpctl status` |

If P4 (oFono) is not installed on Fedora:
```bash
# Option A: COPR (if available)
sudo dnf copr enable <copr-repo>
sudo dnf install ofono

# Option B: Build from source
git clone git://git.kernel.org/pub/scm/network/ofono/ofono.git
cd ofono && ./bootstrap && ./configure --prefix=/usr --disable-dundee
make -j$(nproc) && sudo make install
```
**Record which installation method was used — this answers OQ-1.**

WirePlumber HFP config (create if absent):
```bash
mkdir -p ~/.config/wireplumber/bluetooth.lua.d/
cat > ~/.config/wireplumber/bluetooth.lua.d/50-hfp-ofono.lua <<'EOF'
bluez_monitor.properties = {
  ["bluez5.hfphsp-backend"] = "ofono",
}
EOF
systemctl --user restart wireplumber
```

---

## S5 First: Confirm Adapter Identity

Before any other test — verify RTL8761B is in use and MediaTek is excluded.

```bash
lsusb | grep -iE 'realtek|cambridge|cambridge silicon'
hciconfig
# Expected: one or two hci entries; note which is RTL8761B
# If two adapters: disable the MediaTek one for the duration
sudo hciconfig hci0 down   # disable MediaTek (adjust hci index as needed)
```

Record:
```
S5 adapter: [RTL8761B/CSR8510/other]
hciconfig output:
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
gdbus call -e -d org.ofono -o / -m org.ofono.Manager.GetModems
```

**Pass condition:** output contains a modem object with `Type: hfp` (not `hci` which
is a local modem). Example:
```
([objectpath '/hfp/org/bluez/hci1/dev_XX_XX_XX_XX_XX_XX', {'Online': <true>, 'Type': <'hfp'>, ...}],)
```

If no HFP modem appears after 5 s of BT connect, also check:
```bash
gdbus call -e -d org.ofono -o / -m org.ofono.Manager.GetModems
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
dbus-monitor --session "type=signal,interface=org.ofono.VoiceCallManager"
dbus-monitor --session "type=signal,interface=org.ofono.VoiceCall"
```

### Terminal 3 — PipeWire log (for codec)
```bash
journalctl -f -u pipewire --since now | grep -iE 'codec|msbc|cvsd|lc3|sco|hfp'
```

### Place/receive a call

```bash
# Option A: Call the phone from somewhere (incoming on iPhone → desktop)
# Option B: Dial out from oFono
MODEM_PATH=$(gdbus call -e -d org.ofono -o / -m org.ofono.Manager.GetModems \
  | grep -oP "'/[^']+'(?=.*Type.*hfp)" | head -1)
gdbus call -e -d org.ofono -o "$MODEM_PATH" -m org.ofono.VoiceCallManager.Dial \
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

After the spike (pass or fail), note whether the `50-hfp-ofono.lua` config in the
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
oFono install method: [COPR / source build / package]
PipeWire version: X.Y.Z

S1 oFono HFP modem: [PASS / FAIL — reason]
S2 SCO node running: [PASS / FAIL — reason]
S3 Bidirectional audio: [PASS / FAIL — Desktop→iPhone: OK/NO, iPhone→Desktop: OK/NO]
S4 mSBC codec: [PASS / FAIL — observed: mSBC/CVSD/none]
S5 RTL8761B confirmed: [PASS / FAIL]

OQ-4a PipeWire min version: X.Y.Z [sufficient / needs newer]
OQ-4b LC3-SWB: [observed / not observed — fell back to mSBC/CVSD]
OQ-4c WirePlumber config: [50-hfp-ofono.lua sufficient / additional config: ...]

OVERALL: [PASS — all 5 criteria met / FAIL — failing criteria: S1, S2, ...]
```

If OVERALL PASS → close this bead and mail tincan/architect with results.  
If OVERALL FAIL → add `needs-investigation` label, document failure details, mail tincan/architect.

---

## Common Failure Modes

| Symptom | Likely cause | Action |
|---------|-------------|--------|
| `GetModems` returns only `hci0` type modem | oFono `hfp_hf_bluez5` plugin not loaded OR iPhone not in BT range | Check `ofonod -d` output for plugin load; reconnect BT |
| SCO node never appears | WirePlumber not configured for oFono HFP backend | Verify `50-hfp-ofono.lua` config; restart WirePlumber |
| Audio one-way only | Microphone sink not selected | `wpctl set-default-sink / set-default-source` for the BT device |
| Only CVSD, not mSBC | iPhone or BlueZ mSBC capability mismatch | Check `hciconfig hci1 features` for eSCO/mSBC bit |
| `org.ofono not found` | oFono not started | `sudo systemctl start ofono` or `sudo ofonod &` |

---

## Guardrails

- **MediaTek NOT acceptable.** Results on the built-in MediaTek-class adapter do
  not count. If RTL8761B is not available, block the spike and mail
  tincan/architect.
- **oFono packaging method must be recorded.** This answers OQ-1 in the PRD
  and is a blocker for the packaging bead (tincan-j9wvv).
- **Results are for the architect, not for a builder PR.** The investigator's output
  is: a spike result block in bead notes + mail to tincan/architect. No code is
  written during this spike.
