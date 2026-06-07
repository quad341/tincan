# PRD: Phone Calls — HFP + PipeWire Audio (Phase 3)

**Bead:** tincan-dzb0g (spike prerequisite) → implementation TBD  
**Type:** Feature  
**Priority:** P2  
**Roadmap phase:** Phase 3  
**Date:** 2026-06-07  
**Architect analysis:** tincan-iaf2m (closed — full architecture framework + open questions documented)

---

## Problem Statement

**What:** Tincan users cannot currently place or receive phone calls from the Linux desktop. The iPhone is paired and messaging works, but there is no HFP call-control path and no SCO audio path.

**Who:** Any Tincan user who wants to handle calls at their desk without picking up their phone.

**Impact:** Phase 3 on the roadmap. Without this, the product is messaging-only. Call handling is the feature that makes Tincan a full phone companion rather than just an SMS mirror.

**Approach:** Call control via oFono `hfp_hf_bluez5` (iPhone appears as HFP Audio Gateway modem); voice audio via PipeWire SCO audio node (`bluez5.hfphsp-backend = ofono`). tincand exposes an `im.tincan.Calls` D-Bus interface consumed by tincan_gui. This mirrors the existing MAP pattern (gui → tincand → obexd) and keeps the GUI insulated from oFono API details.

**Highest risk:** SCO audio instability on the integrated MediaTek-class Bluetooth adapter. **All implementation work is blocked until the SCO audio spike (see §Spike Prerequisite) passes on a known-good USB adapter (RTL8761B / CSR8510).**

---

## Goals

| ID | Goal | Measurable Outcome |
|----|------|--------------------|
| G1 | User can answer incoming calls from the desktop | Desktop notification appears within 2 s of ring; user clicks "Answer" → call goes active, audio flows |
| G2 | User can hang up from the desktop | "Hang Up" button ends the call on both iPhone and tincan_gui |
| G3 | User can dial outgoing calls | User enters a number in tincan_gui, clicks Dial → iPhone places the call |
| G4 | Voice audio works bidirectionally | Microphone and speaker both active; no audio on one side is an error, not a degraded state |
| G5 | Caller ID resolved from PBAP contacts | Caller name shows for contacts; falls back to number only for unknowns |

## Non-Goals

- **No call recording** in Phase 3 (deferred to Phase 5 with explicit consent UX).
- **No multiparty conference initiating** — hold/resume and call-swap are in scope; merging into a conference call is not.
- **No DTMF in MVP** — iOS DTMF is unreliable; DTMF is a stretch goal with a mandatory "may be unreliable on iOS" warning in UI.
- **No audio transcription, no AI summarization** (Phase 5).
- **No Windows/macOS** — Linux desktop only.
- **No standalone oFono UI** — tincan_gui is the only call-control surface.

---

## Spike Prerequisite

> **⛔ No implementation work begins until this spike passes.**

The SCO audio hardware risk is rated highest in the roadmap (R2). Before writing any daemon or GUI code, the following must be validated end-to-end on real hardware:

### Spike acceptance criteria

| # | Criterion | Pass condition |
|---|-----------|----------------|
| S1 | oFono `hfp_hf_bluez5` discovers iPhone as HFP modem | `gdbus call -e -d org.ofono -o / -m org.ofono.Manager.GetModems` returns a modem object with `Type=hfp` |
| S2 | PipeWire SCO audio node establishes after call answer | `pw-cli ls` shows a BlueTooth SCO device object with `s.status=running` |
| S3 | Bidirectional voice audio | Speech from iPhone microphone is audible on desktop speakers; speech into desktop mic is audible on iPhone |
| S4 | mSBC (wideband) codec negotiated | `bt-device -i <addr>` or PipeWire log shows mSBC rather than CVSD where possible |
| S5 | All tests use RTL8761B or CSR8510 USB dongle | MediaTek integrated adapter must NOT be used — results on MediaTek do not count |

### Spike open questions (answered by spike execution)

- **OQ-4a:** Which PipeWire version is the minimum for reliable SCO audio? (Dev system: 1.6.4)
- **OQ-4b:** Is LC3-SWB negotiation observed in practice, or does the iPhone fall back to mSBC?
- **OQ-4c:** Any additional WirePlumber config required beyond `bluez5.hfphsp-backend = ofono`?

The spike findings must be recorded in bead notes and used to update this PRD before architecture is finalized.

---

## User Stories

1. **Incoming call — known contact**
   As a Tincan user, when my iPhone rings for an incoming call from a saved contact, I see a desktop notification with the contact's name and a photo (if available), and "Answer" / "Decline" buttons; clicking Answer takes the call and opens the in-call panel with a call timer.

2. **Incoming call — unknown number**
   As a Tincan user, when my iPhone rings from an unknown number, I see the raw phone number and can still Answer or Decline; there is no crash or missing-contact error.

3. **Outgoing call**
   As a Tincan user, I can type or paste a phone number into the tincan_gui dial field and click Dial; the iPhone dials, and I see the call state transition from `dialing` → `active`.

4. **In-call controls**
   As a user in an active call, I see a timer, a Hang Up button, and a Hold button; clicking Hold pauses the call and shows `held` state; clicking Resume restores it.

5. **Audio failure detection**
   As a user, if SCO audio fails to establish within 5 s of answering, I see a clear error ("Audio failed to connect") rather than a silent "active" call with no audio.

6. **oFono unavailable**
   As a user, if oFono is not running or not installed, tincan_gui shows a dismissible banner ("Call support requires oFono") and all other messaging features continue to work normally.

---

## Functional Requirements

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-1 | tincand discovers the iPhone as an oFono HFP modem on Bluetooth connect | `CallController` watches `org.ofono.Manager.GetModems()` + `ModemAdded` signal; iPhone `Type=hfp` modem is detected within 3 s of BT connection |
| FR-2 | Incoming call reaches GUI within 2 s of ring | oFono `CallAdded` → tincand `CallAdded` D-Bus signal → tincan_gui dialog appears; measured round-trip ≤ 2 s on reference hardware |
| FR-3 | Answer, Hangup, Dial buttons are wired end-to-end | Each action reaches oFono (`VoiceCall.Answer()`, `VoiceCall.Hangup()`, `VoiceCallManager.Dial()`) and changes call state |
| FR-4 | SCO audio establishes; timeout error emitted if it does not | PipeWire SCO node connects on answer; if not connected within 5 s, tincand emits `AudioStateChanged({connected: false, reason: "timeout"})` |
| FR-5 | Caller ID resolved from ContactStore (PBAP) | Known numbers show contact name + photo (if cached); unknown numbers show E.164 number only |
| FR-6 | Hold / Resume | `HoldCall` / `SwapCalls` on oFono `VoiceCall`; GUI reflects `held` state |
| FR-7 | Volume control | `im.tincan.Calls.SetVolume(percent)` maps 0–100 → 0–15 (oFono `AT+VGS` range); daemon validates and clamps range |
| FR-8 | Graceful degradation when oFono absent | If `org.ofono` is not on session bus, tincand logs a warning and exposes an empty `im.tincan.Calls` interface; call UI shows a banner, nothing crashes |
| FR-9 | DTMF (stretch goal, with warning) | If implemented, `SendTones(call_id, digits)` works for IVR navigation; GUI shows tooltip "DTMF may be unreliable on iOS" |

---

## Non-Functional Requirements

| ID | Requirement | Metric |
|----|-------------|--------|
| NFR-1 | SCO audio latency | One-way voice latency ≤ 250 ms (measured on reference hardware with RTL8761B) |
| NFR-2 | Call state reaction time | Call state change (incoming / active / held / ended) reflected in GUI ≤ 500 ms after oFono signal |
| NFR-3 | No daemon crash on missing oFono | tincand starts and stays up if `org.ofono` is absent; no `ImportError` for oFono D-Bus bindings |
| NFR-4 | Clean shutdown | Hanging up a call and then disconnecting BT does not leave orphaned PipeWire SCO nodes |
| NFR-5 | Python style | `ruff` + `black` clean; type hints on all `CallController` public methods and D-Bus interface |

---

## Technical Constraints

Sourced from `docs/PROJECT_MANIFEST.md` and architect analysis (`tincan-iaf2m`):

- **oFono not packaged on Fedora.** Must resolve via COPR, bundle, or manual build — see OQ-1.
- **SCO audio adapter restriction.** MediaTek-class adapters unreliable for SCO. Dev/test must use RTL8761B (ASUS USB-BT500) or CSR8510 USB adapter.
- **PipeWire WirePlumber config required.** `~/.config/wireplumber/bluetooth.lua.d/50-hfp-ofono.lua` with `bluez5.hfphsp-backend = ofono` must be documented in onboarding/README.
- **Two-hop architecture is mandatory.** tincan_gui must NOT talk to oFono directly — all call control flows through tincand. Mirrors the MAP pattern.
- **Standard BT profiles only.** HFP `hfp_hf` role only; no proprietary Apple extensions; no iMessage path.
- **No hardcoded iOS version.** iPhone 15 Pro / iOS 26.5 is the reference target, not the spec. Capability detection required.
- **D-Bus interface namespace.** `im.tincan.Calls` on the existing `im.tincan.Daemon` bus object — consistent with the rest of the tincand API.
- **Volume range mapping.** oFono `AT+VGS` is 0–15; tincan API must expose 0–100 and normalize.
- **Audio error contract.** If SCO audio does not establish within 5 s of `Answer()`, emit `AudioStateChanged({connected: false, reason: "timeout"})`. GUI must surface this error — never show a silent "active" call.

---

## Dependencies

| Dependency | Notes |
|------------|-------|
| oFono (`hfp_hf_bluez5`) | NOT packaged on Fedora — packaging strategy is OQ-1 |
| PipeWire 1.x (bluez5 plugin) | `bluez5.hfphsp-backend = ofono`; min version TBD (OQ-4) |
| WirePlumber 0.5.x | Config for HFP backend |
| BlueZ 5.86 | Already on reference host |
| RTL8761B or CSR8510 USB BT dongle | Required for SCO spike and development; MediaTek not usable |
| Existing ContactStore (PBAP) | Caller ID resolution — must not introduce a new contact lookup path |
| Existing tincand D-Bus service | `im.tincan.Calls` added to existing daemon bus object |
| Existing tincan_gui dbus_client | Must subscribe to the new `im.tincan.Calls.*` signals |

---

## Open Questions (require operator input before design is finalized)

> These were surfaced by the architect in tincan-iaf2m. **Implementation is blocked until OQ-1 and OQ-3 are answered and the spike (OQ-2) passes.**

| ID | Question | Options |
|----|----------|---------|
| **OQ-1** | **oFono packaging strategy for Fedora?** | (a) COPR package — maintained alongside tincan; (b) bundle oFono binary in tincan's COPR package; (c) document manual `make install` from source; (d) pursue upstream Fedora packaging (long lead time). Which is acceptable for the target user? |
| **OQ-2** | **Spike first?** (answered: YES) | Spike must pass before implementation begins. |
| **OQ-3** | **MVP call scope?** | Minimum: answer + hangup + basic dial. Full: + hold/resume + DTMF + call-swap. Which features are in scope for the first implementation? |
| **OQ-4** | **Minimum PipeWire version?** | Dev system has 1.6.4. Should the minimum be documented? What's the Fedora 44 default? (Spike findings will inform this.) |
| **OQ-5** | **In-call UI placement?** | (A) Floating persistent widget always-on-top when a call is active; (B) Main window hijacked — conversation list slides away, call UI takes over; (C) System notification + minimal call controls in tray. Which matches the intended UX? |

---

## Architecture Scope (brief, for downstream routing)

The architect's full framework is in tincan-iaf2m (closed). Key elements requiring architectural finalization after spike passes:

- `tincand/call_controller.py` — new daemon module
- `im.tincan.Calls` D-Bus interface on `im.tincan.Daemon`
- Modem discovery retry strategy (race between BT connect and oFono modem add)
- PipeWire audio error detection and timeout logic
- Volume mapping and normalization

All of the above are **blocked on OQ-1 (packaging), OQ-3 (MVP scope), and spike pass**.

---

## Risks

| Risk | Likelihood | Impact | PRD mitigation |
|------|-----------|--------|---------------|
| SCO audio fails on MediaTek (R2) | High | High | Spike required on RTL8761B before any build work |
| oFono not available on Fedora (OQ-1) | Certain | High | Packaging question is a blocker — must answer before architecture finalized |
| iPhone not surfacing HFP when A2DP active | Medium | Medium | WirePlumber `hands-free` profile forcing is a technical constraint |
| oFono modem discovery race | Medium | Medium | Architect must design retry/watch strategy in CallController |
| DTMF unreliable on iOS | Medium | Low | Deferred to stretch goal; mandatory warning in UI if implemented |
