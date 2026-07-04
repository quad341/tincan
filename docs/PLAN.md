# Tincan — Project Plan

> Status: **historical planning document** — the implementation has since
> shipped (see the root [README](../README.md) for current status). Kept for
> the vision, design principles, risk register, and resolved-open-question
> record. Last updated 2026-07-04.

## 1. Vision

A Linux application that pairs with an iPhone over standard Bluetooth profiles
and acts as a desktop **phone companion**: send and receive SMS, place and
answer phone calls, mirror notifications, and browse contacts — all from a
desktop GUI, with no jailbreak and no Apple-account risk.

The longer arc: build the bridge so a **phase-2 "secretary" agent** (Claude) can
later use the *same* internal API to read and send SMS, listen to / transcribe
calls, and eventually synthesize voice onto a call. Phase 1 does not build the
agent, but every architectural decision in phase 1 is made so phase 2 is cheap.

**Analogy / existence proof:** Microsoft Phone Link for iPhone (Windows 11,
April 2023) already delivers calls + SMS + notifications + contacts over
Bluetooth alone. The full feature set is therefore *proven possible over
vendor-neutral profiles*. No equivalent integrated project exists on Linux —
only abandoned single-purpose hobby daemons. Tincan fills that gap.

## 2. Design principles

1. **Standard Bluetooth profiles only.** ANCS, MAP, HFP, PBAP — all vendor-neutral
   and supported by Apple for car kits / accessories. No jailbreak. **No iMessage
   reverse-engineering in the core** (that path — pypush / Beeper lineage — is a
   ToS / Apple-ID-ban minefield and is explicitly out of scope; if ever wanted it
   is an isolated, clearly-labeled-risky module, never load-bearing).
2. **Version-resilient — never lock to an iOS version or iPhone model.** Locking
   in is a failure. We use iPhone 15 Pro / iOS 26.5 as the *reference target*, not
   the spec. Apple periodically tightens how messages/notifications are surfaced;
   we survive that with **capability detection + graceful degradation**, never with
   hardcoded version assumptions.
3. **Clean separation of bridge and clients.** A headless daemon owns all the
   Bluetooth machinery and exposes one stable internal API + event stream. The GUI
   is just a client. The phase-2 MCP/agent is just another client. This boundary is
   the single most important structural decision.
4. **Honest about limits.** Whatever the platform can't do, we document for
   ourselves (see [LIMITATIONS.md](LIMITATIONS.md)) rather than discovering it in
   front of a user.
5. **Echo-free call audio is table stakes.** Without echo cancellation the far
   party hears themselves and will simply refuse to stay on the call — which
   makes the entire calls/secretary stack moot. AEC on every call is a hard,
   release-gated requirement (tincan-97mlk.2), not a quality nicety, for both
   tincan and iris.

## 3. Architecture

Three layers, mapped onto the profile stack:

```
            ┌─────────────────────────────────────────────┐
            │  Clients                                      │
            │  ┌──────────────┐      ┌────────────────────┐ │
            │  │ tincan-gui   │      │ tincan-mcp (P2)    │ │
            │  │ (PySide6)    │      │ + push-to-Claude   │ │
            │  └──────┬───────┘      └─────────┬──────────┘ │
            └─────────┼────────────────────────┼────────────┘
                      │   internal API + event stream
                      │   (D-Bus session service — tentative)
            ┌─────────┴────────────────────────────────────┐
            │  tincand  (headless bridge daemon, Python)    │
            │  domain model: Messages · Calls ·             │
            │                Notifications · Contacts       │
            │  + pairing / reconnect / capability detection │
            └───┬─────────────┬──────────────┬─────────────┘
                │             │              │
          obexd (D-Bus)   BlueZ GATT     oFono hfp_hf + PipeWire
          MAP + PBAP      ANCS (BLE)     HFP control + SCO audio
                │             │              │
            ┌───┴─────────────┴──────────────┴─────────────┐
            │                  iPhone                       │
            └───────────────────────────────────────────────┘
```

**Components**

- **`tincand`** — headless bridge daemon (Python). Owns BlueZ / obexd (and later
  oFono) over D-Bus. Normalizes raw profile data into a clean domain model
  (`Message`, `Conversation`, `Call`, `Notification`, `Contact`) and emits events.
  Handles pairing, reconnection, and per-feature capability detection. Tentatively
  exposed itself as a **D-Bus session service** (idiomatic on Linux; lets multiple
  clients subscribe to the same event stream) — to be confirmed against a plain
  local socket / JSON-RPC during the phase-0 spike.
- **`tincan-gui`** — PySide6 desktop app. A pure client of `tincand`: renders
  conversations, call state, notifications; sends commands back.
- **`tincan-mcp`** *(phase 2)* — an MCP server that is *another* client of the
  same `tincand` API, plus a push mechanism into a Claude session.

**Capability → profile mapping**

| Capability    | Profile / mechanism | Linux surface |
|---------------|---------------------|---------------|
| Messages      | **MAP** (Message Access Profile) | obexd `org.bluez.obex.MessageAccess1` |
| New-msg trigger | **ANCS** (Apple Notification Center Service, BLE) | BlueZ GATT (fork the ancs4linux approach) |
| Calls         | **HFP** Hands-Free role | oFono `hfp_hf` → `org.ofono.VoiceCallManager`; audio via PipeWire |
| Notifications | **ANCS** (BLE) | BlueZ GATT |
| Contacts      | **PBAP** (Phone Book Access Profile) | obexd |

See [PROTOCOLS.md](PROTOCOLS.md) for what each profile actually exposes on iOS,
the known iOS quirks, and sources.

## 4. Phased roadmap

### Phase 0 — Validation spike (de-risk before committing)
The research on iOS MAP behavior is partly old and sparse; **validate it
empirically on iOS 26.5 before building.** Small, throwaway scripts only.

- **M0.1** Pair the iPhone; bring up an obexd MAP session; list the inbox; fetch
  one message *body*. Confirms the core SMS assumption on the real target.
- **M0.2** Stand up an ANCS consumer (fork / run ancs4linux); receive a Messages
  notification including sender. Confirms the BLE trigger path.
- **M0.3** Confirm the built-in MediaTek adapter can hold **BLE (ANCS) + Classic
  (MAP)** to the same phone simultaneously.
- **Output:** a short findings note that confirms or amends this plan. Open
  questions to answer are listed in §6.

### Phase 1 — SMS MVP  *(chosen v1)*
Definition of done: **hold a real SMS conversation from the desktop, reliably.**

- **M1.1** `tincand` skeleton: D-Bus/obex session management, pairing + reconnect
  handling, the internal API/event-stream boundary.
- **M1.2** ✅ *Implemented.* Inbound: `poll_inbox()` via MAP UpdateInbox/ListMessages/
  GetMessage with retry; ANCS backend (AncsBackend, pending hardware validation
  tincan-r23) for instant trigger; conversation grouping by Sender. Risk R1 mitigated:
  MAP polling is the primary read path; ANCS is an instant supplement.
- **M1.3** ✅ *Implemented.* Outbound: `build_bmsg()` + `MapBackend.send_message()`
  via `PushMessage` + Transfer1 watch. iOS auto-upgrades to iMessage for iMessage
  contacts (confirmed in spike). GUI `SendMessage` still stub — wire-up is next.
- **M1.4** PySide6 GUI: conversation list, thread view, compose/send; contact-name
  resolution via PBAP.
- **M1.5** Hardening: reconnect, onboarding UX for the iOS "Show Notifications"
  requirement (R7), capability detection for graceful degradation.

### Phase 2 — Notifications (broaden ANCS)
Extend the ANCS consumer built for the SMS trigger into full notification
mirroring: all apps, categories, positive/negative actions (e.g. answer/decline),
and desktop-notification integration. Much of the plumbing already exists from
phase 0/1.

### Phase 3 — Calls (the deferred high-risk piece)
- **M3.1** Install / build **oFono** (not packaged on Fedora — build from source or
  find a COPR). HFP Hands-Free control via `org.ofono.VoiceCallManager`:
  dial / answer / reject / hang up / DTMF / caller-ID in the GUI.
- **M3.2** SCO call audio via PipeWire (`bluez5.hfphsp-backend = ofono`). **This is
  where the integrated-adapter risk bites (R2)** — de-risk with a dedicated audio
  spike first; fall back to a known-good USB BT dongle if the built-in chip can't
  hold stable SCO.

### Phase 4 — Contacts polish (PBAP)
Likely partly done for name-resolution in phase 1; finish full sync / search here.

### Phase 5 — Secretary agent  *(separate-ish project, enabled by phases 1–4)*
- **`tincan-mcp`**: expose send/read SMS, call control, and the notification stream
  as MCP tools (a second client of the existing `tincand` API).
- **Push into a Claude session**: the genuinely hard part — get phone events into a
  live agent loop. Options to evaluate: a long-running agent that subscribes to the
  `tincand` event stream; a push primitive; a scheduled/triggered run. Spike
  separately.
- **Call transcription**: tap the PipeWire SCO *source* → speech-to-text. Reachable
  because PipeWire owns the audio nodes once phase 3 lands.
- **Voice synthesis onto a call**: TTS → inject into the SCO *sink*. Same enabler.
- **Consent / legal**: recording and transcribing calls carries jurisdiction-specific
  consent obligations. Flag prominently; make recording explicit and opt-in.

## 5. Risk register

| # | Risk | Severity | Mitigation |
|---|------|----------|------------|
| R1 | MAP real-time new-message push (MNS) is the flakiest, least-maintained piece on Linux | High → **resolved** | MNS not used. **MAP polling** (`UpdateInbox`/`ListMessages`/`GetMessage`) is the primary read path, implemented and validated. ANCS (AncsBackend) is the instant trigger supplement, pending hardware validation (tincan-r23). |
| R2 | HFP **SCO call audio** unreliable on the integrated MediaTek-class adapter | High | **Deferred to phase 3.** Try built-in first; keep a known-good USB BT dongle (CSR8510 / BCM20702) as fallback. Dedicated audio de-risk spike before committing the calls UI. |
| R3 | Apple tightens message/notification surfacing across iOS versions | Medium (ongoing) | Capability detection + graceful degradation; **no hardcoded version assumptions** (design principle #2). |
| R4 | obexd's MAP client is functional but lightly maintained / historically buggy | Medium | Drive the `org.bluez.obex` D-Bus API directly; be prepared to patch obexd and contribute upstream. |
| R5 | iOS group-text sender attribution is lossy; sent-folder path is mislabeled | Low–Med | Absorb in the daemon's normalization layer; don't leak the quirk into the UI. |
| R6 | iMessage-incoming over MAP is unconfirmed (evidence shows SMS only) | **RESOLVED** | Spike confirmed: iMessage threads ARE present in MAP inbox, listed as `sms-gsm` type (iOS rebrands the TYPE field). Full body available via `GetMessage`. |
| R7 | iOS drops the MAP link unless the paired device has "Show Notifications" enabled | Low but UX-critical | Onboarding flow must instruct the user and detect the condition. |

## 6. Open questions (resolve in phase 0)

- ✅ **OQ-1:** Does iOS 26.5 reliably expose **SMS message bodies** over MAP?
  **YES.** Spike confirmed: `GetMessage` returns full body text. `ListMessages`
  returns up to ~10 recent messages per session. No `SetFolder`/`ListFolders`
  needed — `ListMessages('inbox', {})` works directly.
- ✅ **OQ-2:** Does iOS 26.5 expose **iMessage** content in the MAP inbox? **YES.**
  iMessage threads appear in the inbox listing. `TYPE` field is always `sms-gsm`
  (iOS rebrands it). Use `GetMessage` for full body. R6 resolved.
- ✅ **OQ-SEND:** Does `PushMessage` (outbound send) work? **YES.** iOS delivers the
  message and auto-upgrades SMS→iMessage for iMessage contacts.
- ✅ **OQ-3:** Does **ANCS** reliably fire for Messages *with sender* on 26.x?
  **YES** — validated in live use. Requires `bluetoothd --experimental` and a
  BlueZ with the ext-adv length fix
  (see [ancs-bluez-ext-adv-rootcause.md](ancs-bluez-ext-adv-rootcause.md)).
- ✅ **OQ-4:** Can the **built-in MediaTek adapter** hold simultaneous BLE (ANCS) +
  Classic (MAP)? **NO** — the MT7925 fails ANCS advertising and SCO audio; the
  ASUS USB-BT500 is the reference adapter (see [../COMPATIBILITY.md](../COMPATIBILITY.md)).
- ✅ **IPC decision:** `tincand` is a **D-Bus session service** (`im.tincan.Daemon`
  on session bus). Decided during M1.1.

## 7. Environment & prerequisites

Reference host (verified 2026-05-31, Fedora 44, "roglet"):

| Component | Status |
|-----------|--------|
| BlueZ | **5.86** — current, no build needed ✓ |
| obexd | present (`/usr/libexec/bluetooth/obexd`) — the MAP/PBAP engine ✓ |
| PipeWire / WirePlumber | **1.6.4 / 0.5.14** — modern base for later audio ✓ |
| Python | **3.14**, with `python-dbus 1.4.0` + PyGObject/Gio ✓ |
| PySide6 | **not installed** — add when GUI work starts |
| `obexctl` | not shipped — not required (drive obexd via D-Bus); install `bluez-tools` only as a manual poking aid |
| oFono | **not installed, not packaged on Fedora** — build from source / COPR for **phase 3 only** (not a v1 blocker) |
| BT adapter | integrated MediaTek-class (IMC Networks `13d3:3608`) — fine for SMS (RFCOMM/OBEX, no audio); the at-risk component for phase-3 SCO audio (R2) |

**Role note:** by default the adapter advertises MAP/PBAP *server* + HFP *AG*
records (i.e. it looks like "the phone"). Tincan needs the opposite — the laptop
as **client** (MAP MCE / PBAP / HFP-HF). obexd's client API provides exactly that;
this is just called out so nobody gets confused about role direction mid-build.

## 8. Distribution (future, not now)

Eventually figure out a clean install path for other people: likely a Flatpak or
COPR for the GUI, systemd *user* services for `tincand`, and a setup flow for the
pairing + "Show Notifications" requirement. Out of scope until the core works.
