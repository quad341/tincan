# Architecture: Phone Calls — HFP + PipeWire Audio (tincan-iaf2m)

## Problem Statement

Tincan's roadmap includes placing and receiving calls via the iPhone over
Bluetooth HFP (Hands-Free Profile). This involves:
1. **Call control** via the oFono `hfp_hf_bluez5` plugin → D-Bus API
2. **Call audio** via PipeWire (SCO audio node)
3. **Call state** in the tincand daemon (D-Bus surface for GUI)
4. **Call UI** in tincan_gui (incoming call dialog, in-call controls)

This is the most complex feature on the roadmap. The bead instruction says:
**mail the operator with open design questions rather than guessing**.
This document captures the architecture framework and all open questions.

---

## Technology Stack

Sourced from `docs/PROTOCOLS.md`:

| Component | Technology | Role |
|-----------|-----------|------|
| Call control | oFono `hfp_hf_bluez5` plugin + `org.ofono.VoiceCallManager` D-Bus API | AT command exchange over RFCOMM |
| Call audio | PipeWire 1.x (1.6.4 on dev system) with `bluez5.hfphsp-backend = ofono` | SCO audio node; mSBC wideband; LC3-SWB on PW 1.2+ |
| Bluetooth transport | BlueZ 5.x (pairing + RFCOMM/SCO) | Underlying transport |
| iPhone interface | iOS as HFP Audio Gateway (AG) | Exposes calls, caller ID, hold, DTMF |

**oFono packaging caveat:** oFono is NOT packaged on Fedora. The packaging bead
(`tincan-j9wvv`) must account for this dependency.

---

## Architecture Framework

### Layer diagram

```
+-------------------+    D-Bus     +-------------------+
|   tincan_gui      | <~~~~~~~~~~> |   tincand         |
|   Call UI:        |  im.tincan.  |   CallController  |
|   - Incoming call |  Calls.*     |   (new module)    |
|   - In-call panel |              +--------+----------+
|   - DTMF keypad   |                       |
+-------------------+                  D-Bus (Session)
                                            |
                               +------------+----------+
                               |   oFono               |
                               |   hfp_hf_bluez5       |
                               |   org.ofono.*         |
                               +------------+----------+
                                            |
                               +------------+----------+
                               |   BlueZ + PipeWire    |
                               |   SCO audio           |
                               +-------------------+---+
                                                   |
                                               iPhone (HFP AG)
```

**Two-hop design:** tincan_gui talks to tincand, which talks to oFono, which
manages BlueZ. tincan_gui never speaks to oFono directly.

This mirrors the existing MAP pattern (gui → tincand → obexd) and keeps the
GUI insulated from oFono API details.

---

## Proposed D-Bus Surface (im.tincan.Calls)

New D-Bus interface on the existing `im.tincan.Daemon` bus object:

### Methods

| Method | In | Out | Description |
|--------|----|----|-------------|
| `GetCalls` | — | `aa{sv}` | List active calls |
| `Dial` | `s number` | `s call_id` | Place an outgoing call |
| `Answer` | `s call_id` | — | Answer incoming call |
| `Hangup` | `s call_id` | — | Hang up a specific call |
| `HangupAll` | — | — | Hang up all calls |
| `SendTones` | `s call_id, s tones` | — | DTMF tones (IVR navigation) |
| `SwapCalls` | — | — | Swap active/held calls |
| `HoldCall` | `s call_id` | — | Put call on hold |
| `GetAudioStatus` | — | `a{sv}` | PipeWire node status, codec, volume |
| `SetVolume` | `u percent` | — | Microphone/speaker volume |

### Signals

| Signal | Args | Description |
|--------|------|-------------|
| `CallAdded` | `a{sv} call_dict` | New call appeared (incoming or outgoing) |
| `CallRemoved` | `s call_id` | Call ended |
| `CallStateChanged` | `s call_id, s state` | `incoming | dialing | active | held | terminated` |
| `AudioStateChanged` | `a{sv} audio_dict` | SCO node connected/disconnected, codec |

### Call dict schema

```python
{
    "id": str,           # oFono object path shortform
    "state": str,        # incoming | dialing | active | held | terminated
    "line_id": str,      # caller phone number (if available from CLIP)
    "name": str,         # resolved contact name (if PBAP-available)
    "direction": str,    # inbound | outbound
    "multiparty": bool,
}
```

---

## Module: `tincand/call_controller.py`

New daemon module that:
1. Connects to oFono D-Bus (`org.ofono`) and monitors modem state
2. Subscribes to `CallAdded`/`CallRemoved`/`PropertyChanged` signals on
   `org.ofono.VoiceCallManager` and `org.ofono.VoiceCall`
3. Maintains in-memory call state dict
4. Exposes the `im.tincan.Calls` D-Bus interface via `TincanService`
5. Resolves caller phone numbers against `ContactStore` for display names

**oFono modem discovery:** The iPhone appears as an oFono modem object of type
`hfp` when connected via `hfp_hf_bluez5`. The `CallController` must watch
`org.ofono.Manager.GetModems()` and subscribe to modem add/remove.

---

## UI Components

### Incoming Call Dialog (`tincan_gui/call_dialog.py`)

A non-blocking `QDialog` (or custom top-level widget):
- Shows caller name + number
- "Answer" button → calls `Answer(call_id)` on daemon
- "Decline" button → calls `Hangup(call_id)` on daemon
- Auto-dismisses when `CallRemoved` fires

### In-Call Panel (integrated into `tincan_gui/main.py` or separate widget)

Active call state: timer, caller name, hold/resume, hang up, DTMF keypad.
Shown as a collapsible panel at the top of the main window or as a persistent
floating widget.

### DTMF Keypad

Standard 12-button layout (0–9, *, #). Sends `SendTones(call_id, digits)` on
each button press.

---

## Sequence: Incoming Call

```mermaid
sequenceDiagram
    autonumber
    participant iPhone as iPhone (HFP AG)
    participant BlueZ as BlueZ + oFono
    participant Ctrl as tincand/CallController
    participant Service as TincanService (im.tincan.Calls)
    participant GUI as tincan_gui IncomingCallDialog

    iPhone->>BlueZ: RING / +CLIP (caller ID)
    BlueZ->>oFono: SCO link up; VoiceCall state=incoming
    oFono->>Ctrl: CallAdded(call_path, {State: incoming, LineIdentification: number})
    Ctrl->>Ctrl: resolve number → contact name via ContactStore
    Ctrl->>Service: emit CallAdded(call_dict)
    Service->>GUI: (D-Bus signal → dbus_client)
    GUI->>GUI: show IncomingCallDialog(caller_name, number)
    GUI->>Service: Answer(call_id)
    Service->>Ctrl: answer_call(call_id)
    Ctrl->>oFono: VoiceCall.Answer()
    oFono->>BlueZ: SCO audio negotiation (mSBC/CVSD)
    BlueZ->>BlueZ: PipeWire SCO node connects
    Ctrl->>Service: emit CallStateChanged(id, "active")
    Service->>GUI: CallStateChanged → show in-call panel
```

1–2. iPhone rings; BlueZ/oFono detects incoming call.
3. oFono fires `CallAdded` with call object + state.
4. `CallController` resolves the caller's number against `ContactStore`.
5. Emits `im.tincan.Calls.CallAdded` on D-Bus.
6. `TincandClient` in tincan_gui receives the signal.
7. Incoming call dialog appears with caller info.
8. User clicks "Answer" in the dialog.
9–10. `CallController` calls `VoiceCall.Answer()` on oFono.
11. oFono + BlueZ negotiate SCO audio codec (mSBC preferred).
12. PipeWire SCO audio node becomes active.
13–14. `CallStateChanged` fires; GUI transitions to in-call panel.

---

## Audio Architecture

```
iPhone audio (SCO/mSBC)
    ↓
BlueZ SCO socket
    ↓
PipeWire bluez5 plugin
  (bluez5.hfphsp-backend = ofono)
    ↓
PipeWire audio graph
    ↓
System speakers / microphone
```

**PipeWire configuration required:**
```lua
-- ~/.config/wireplumber/bluetooth.lua.d/50-hfp-ofono.lua
bluez_monitor.properties = {
  ["bluez5.hfphsp-backend"] = "ofono",
}
```

tincand owns call control; PipeWire owns audio. tincand does NOT directly
manage SCO sockets or audio routing — that's PipeWire's job once oFono
establishes the call.

**Volume control:** oFono exposes `AT+VGS`/`AT+VGM` via `SetVolume` on the
modem/call object. tincand exposes this via `im.tincan.Calls.SetVolume`.

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| **SCO audio instability (R2 — highest risk)** | High (MediaTek adapters) | High | Prototype audio on real hardware BEFORE committing to call UI; document USB adapter requirement |
| oFono not packaged on Fedora | High | High | Must resolve in packaging (tincan-j9wvv); COPR or bundled build |
| iPhone may not surface HFP when A2DP is active | Medium | Medium | Force `hands-free` profile via WirePlumber / `bluez5.profile = headset-head-unit` |
| DTMF flaky on iOS | Medium | Low | Known iOS behavior; warn users; defer DTMF UX polish |
| LC3-SWB codec negotiation unverified | Medium | Low | Expect mSBC/CVSD in practice; don't advertise LC3 until verified |
| oFono modem discovery timing (race with HFP connection) | Medium | Medium | Use `GetModems()` + `ModemAdded` signal subscription with retry |

---

## Open Design Questions for Operator

These questions require operator input before the design can be finalized:

**OQ-1: oFono installation strategy for Fedora?**
oFono is not in Fedora repos. Options: (a) COPR package, (b) bundle oFono binary in tincan's COPR package, (c) document manual build from source, (d) pursue upstream Fedora packaging. Which is acceptable for the target user?

**OQ-2: Audio prototype first?**
Given SCO audio instability on MediaTek adapters (the known-good adapter on dev is MediaTek-class), should audio be prototyped on the real device with a known-good USB BT dongle BEFORE committing design and builder time to the full call UI? Recommended: spike before implementing.

**OQ-3: Target call scope for MVP?**
Full call features: dial, answer, hangup, hold, DTMF, call swap, multiparty.
Minimum viable: answer, hangup, basic dial. Which features are in-scope for the first implementation?

**OQ-4: PipeWire version dependency?**
The dev system has PipeWire 1.6.4 (LC3-SWB capable). Should the minimum PipeWire version for calls be documented in requirements? And what's the target distro's PipeWire version?

**OQ-5: In-call UI placement?**
Option A: floating persistent widget (always-on-top) when a call is active.
Option B: hijacks the main window (conversation list slides away, call UI takes over).
Option C: system notification + minimal call controls in tray.
Which matches the intended UX?

---

## Guardrails

- `CallController` must NOT bridge calls between two phones or forward audio.
- DTMF warning must appear in UI: "DTMF may be unreliable on iOS."
- If SCO audio fails to establish within 5 seconds of `Answer()`, tincand must emit `AudioStateChanged({connected: false, reason: "timeout"})` and the GUI must display an audio error — not silently show an "active" call with no audio.
- Volume ranges: 0–15 (oFono `AT+VGS` scale). Normalize to 0–100 percent in the D-Bus API.

---

## Recommendation

**Do not begin builder implementation until:**
1. OQ-1 (oFono packaging) is resolved.
2. OQ-2 (audio prototype) is complete and SCO audio is confirmed working.
3. OQ-3 (MVP scope) is decided.

Create a spike bead (`needs-spike` label) for SCO audio validation before
spawning implementation beads. This is the highest-risk item in the whole roadmap.
