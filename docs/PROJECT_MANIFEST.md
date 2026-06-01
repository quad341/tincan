# Project Manifest: Tincan

## Overview

Tincan is a Linux desktop "phone companion" for the iPhone — an open, Linux-native
equivalent of Microsoft Phone Link. It pairs with an iPhone over **standard,
vendor-neutral Bluetooth profiles** (ANCS, MAP, HFP, PBAP) — no jailbreak, no
Apple-ID risk, no companion app on the phone — and lets a user **send/receive SMS,
place/answer calls, mirror notifications, and browse contacts** from a desktop GUI.
The primary user is a Linux desktop owner with an iPhone who wants desk-side message
and call handling. It is deliberately architected as a headless bridge daemon plus
thin clients so that a **phase-2 "secretary" AI agent** (Claude, via an MCP server)
can later drive the same capabilities programmatically — read/send SMS, transcribe
calls, and eventually synthesize voice onto a call.

## Tech Stack

| Layer    | Technology | Notes |
|----------|-----------|-------|
| GUI client | PySide6 (Qt for Python) | `tincan-gui`; pure client of the daemon — renders conversations, call state, notifications; sends commands back |
| Bridge daemon | Python 3.14 (`tincand`) | Headless; owns all Bluetooth machinery; normalizes raw profile data into the domain model; emits events; handles pairing, reconnect, capability detection |
| IPC / event stream | D-Bus session service (tentative) | Internal API + event stream between daemon and clients; to be confirmed against a plain local socket / JSON-RPC during the phase-0/M1.1 spike |
| Bluetooth core | BlueZ 5.86 + obexd | Pairing, GATT (ANCS), OBEX (MAP/PBAP); present on the reference host, no build needed |
| Messaging transport | MAP via obexd `org.bluez.obex.MessageAccess1` | SMS list / fetch body / `PushMessage` send |
| Notification trigger | ANCS over BLE GATT (fork the ancs4linux approach) | Instant "new SMS" trigger and (phase 2) full notification mirroring |
| Calls (phase 3) | oFono `hfp_hf` + PipeWire | HFP Hands-Free control via `org.ofono.VoiceCallManager`; SCO audio via PipeWire (`bluez5.hfphsp-backend = ofono`); oFono built from source / COPR |
| Agent interface (phase 5) | `tincan-mcp` (MCP server) | A second client of the `tincand` API plus a push mechanism into a Claude session |
| Testing | pytest *(default — update when scaffolded)* | Unit + integration; on-device manual validation for real iOS profile behavior (phase 0) |
| Linting | ruff + black *(default — update when scaffolded)* | Formatting + lint for the Python codebase |

## Project Structure

*(proposed — update when scaffolded)*

```
tincan/
├── docs/                  # PLAN.md, PROTOCOLS.md, LIMITATIONS.md, manifests (this folder)
├── tincand/               # headless bridge daemon (Python)
│   ├── bluetooth/         # BlueZ / obexd / oFono D-Bus adapters
│   │   ├── ancs.py        # BLE GATT consumer (notification + new-SMS trigger)
│   │   ├── map.py         # MAP client: list / fetch body / PushMessage
│   │   ├── pbap.py        # contact-name resolution
│   │   └── hfp.py         # (phase 3) oFono call control
│   ├── domain/            # Message, Conversation, Call, Notification, Contact + normalization
│   ├── api/               # internal API + event stream (D-Bus service or local socket)
│   └── pairing.py         # pairing, reconnect, capability detection
├── tincan-gui/            # PySide6 desktop client
├── tincan-mcp/            # (phase 5) MCP server — second client of tincand
├── spikes/                # phase-0 throwaway validation scripts (M0.1–M0.3)
└── tests/
```

## Domain Model

Owned and normalized by `tincand`; clients only ever see these clean types, never raw
profile data. (Quirk-absorption — e.g. the sent-folder mislabel and group-text
attribution loss — happens here, never in the UI.)

- **Message**: `id`, `conversation_id`, `direction` (inbound|outbound),
  `sender` (number / vCard), `body` (UTF-8), `timestamp`, `type` (SMS_GSM; iMessage
  inbound unconfirmed — R6), `status` (read|sent|delivered). Body fetched over MAP
  `GetMessage`; arrival triggered by ANCS.
- **Conversation**: `id`, `participants[]`, `display_name` (resolved via PBAP),
  `last_message_at`. Grouping must cope with the iOS group-text attribution bug (R5).
- **Call** *(phase 3)*: `id`, `line_identification` (caller number), `name`,
  `direction`, `state` (incoming|active|held|ended), `multiparty`. Mapped from
  oFono `org.ofono.VoiceCall` properties.
- **Notification**: `id`, `app_identifier` (e.g. `com.apple.MobileSMS`), `title`,
  `subtitle`, `message` (body, subject to iOS "Show Previews"), `date`,
  `category` (IncomingCall|MissedCall|Voicemail|Social|Email|…), `event_flags`,
  `positive_action_label`, `negative_action_label`. Only two actions exist
  (positive/negative) — no arbitrary reply over ANCS.
- **Contact**: `phone_number` (identity key), `name`, vCard fields. Resolved via
  PBAP; no separate account entity (Customer-style identity is the phone number).

## Conventions

*(default — update when scaffolded)*

- **File naming:** `snake_case.py` modules; one Bluetooth profile per module under `tincand/bluetooth/`
- **Test files:** `test_*.py` under `tests/`, mirroring package layout; mark on-device tests that need a paired iPhone
- **API routes:** D-Bus interface names `<reverse.dns.domain>.Tincan.*` (placeholder — pick a real reverse-DNS namespace when scaffolding) (or local-socket JSON-RPC methods) — decided in M1.1; methods named after domain actions (`SendMessage`, `ListConversations`), signals for the event stream (`MessageReceived`, `CallStateChanged`)
- **Commits:** Conventional Commits (`feat:`, `fix:`, `docs:`, `spike:`)
- **Branches:** feature branch per work item — `tincan-<feature>`

## Constraints

- **Standard Bluetooth profiles only** (ANCS, MAP, HFP, PBAP). No jailbreak, no
  Apple-ID risk, no iPhone companion app.
- **No iMessage reverse-engineering in the core** (pypush / Beeper Mini lineage) —
  ToS / Apple-ID-ban minefield, explicitly out of scope; if ever added it is an
  isolated, clearly-labeled-risky, optional module, never load-bearing.
- **Version-resilient — never lock to an iOS version or iPhone model.** iPhone 15 Pro
  / iOS 26.5 is the *reference target*, not the spec. Survive Apple tightening via
  **capability detection + graceful degradation**, never hardcoded version assumptions.
- **Clean separation of bridge and clients.** The daemon owns all Bluetooth; GUI and
  MCP are just clients of one stable internal API. This boundary is load-bearing.
- **No full message history** — MAP exposes only a recent window (~10 inbox messages)
  plus live session updates; not an archive.
- **No external DB server / cloud** — single-machine, local.
- **Don't rely on MAP MNS** for real-time push (R1) — use ANCS over BLE as the
  new-SMS trigger; poll `UpdateInbox`/`ListMessages` as a further fallback.
- **No online payments, no Mac dependency, no reading arbitrary iPhone data** (the iOS
  sandbox does not expose the Messages DB, photos, or files to a BT accessory).
- The paired iPhone **must have "Show Notifications" enabled** or iOS drops the MAP
  link — a hard requirement surfaced in onboarding (R7).
- **Calls deferred to phase 3**; SCO audio on the integrated MediaTek-class adapter is
  the #1 hardware risk (R2) — USB BT dongle (CSR8510 / BCM20702) is the fallback.

---

## Task Inputs

*(pipeline-critical — verify before running factory)*

| Agent     | Receives                  | From                     |
|-----------|--------------------------|--------------------------|
| Planner   | Feature request (e.g. "ANCS-triggered inbound SMS") + this manifest | Human / roadmap §4 |
| Architect | Planner work package + Tech Stack & Constraints sections | Planner |
| Designer  | Architect ADR + Domain Model section (Message/Conversation/Call/Notification/Contact) | Architect (after Gate 1) |
| Coder     | Designer spec + Conventions & Task Inputs sections | Designer |
| Reviewer  | Code diff + Review Standards section | Coder |
| Deployer  | Reviewer report + Release Criteria section | Reviewer (after Gate 2) |

## Services to Connect

| Service | Purpose | Config |
|---------|---------|--------|
| BlueZ 5.86 | Pairing, BLE GATT (ANCS), Classic transport | System D-Bus `org.bluez`; adapter in client/HF role (MAP MCE / PBAP / HFP-HF), not server |
| obexd | MAP + PBAP engine (OBEX) | `/usr/libexec/bluetooth/obexd`; driven via `org.bluez.obex` D-Bus API |
| oFono (`hfp_hf_bluez5`) | HFP call control *(phase 3)* | Not packaged on Fedora — build from source / COPR; iPhone appears as `Type=hfp` modem |
| PipeWire / WirePlumber 1.6.4 / 0.5.14 | SCO call audio *(phase 3)* | `bluez5.hfphsp-backend = ofono`; may need forcing `hands-free` profile |
| Claude session (MCP) | Phase-5 secretary agent | `tincan-mcp` as a second client; push mechanism TBD |

## Success Criteria

### Per-Feature Success

- [ ] User can read inbound SMS bodies on the desktop, triggered in real time (ANCS → MAP fetch)
- [ ] User can compose and send an SMS that arrives on the recipient's phone (`PushMessage`)
- [ ] Conversations are grouped correctly, with contact names resolved via PBAP
- [ ] SMS-vs-iMessage auto-routing reality is surfaced to the user honestly, not hidden
- [ ] Pairing, reconnect, and the iOS "Show Notifications" requirement are handled with clear onboarding UX
- [ ] Unsupported/degraded capabilities degrade gracefully (capability detection), never crash

### Factory-Level Success

- [ ] **Phase-1 definition of done: hold a real SMS conversation from the desktop, reliably**
- [ ] Phase-0 spike findings confirm or amend the plan before phase-1 build commits
- [ ] Daemon/client API boundary is stable — GUI and a future MCP client both consume it unchanged
- [ ] No hardcoded iOS-version assumptions anywhere in the codebase
- [ ] App runs on the reference host (Fedora 44, BlueZ 5.86) without cloud setup

---

## Review Standards

*(default — customize for this project)*

### Spec Compliance

- Implementation matches the Designer spec's domain types and event contract
- No raw Bluetooth/profile data leaks past `tincand` into a client — all clients see only normalized domain types
- iOS quirks (sent-folder mislabel, group-text attribution, "Show Notifications" requirement) are absorbed in the daemon, per spec
- Capability detection present for any feature that can be unavailable; graceful degradation, not failure

### Style

- Python: passes `ruff` + `black`; type hints on public daemon API and domain models
- D-Bus/IPC interface names and signals follow the Conventions section
- One Bluetooth profile per module; daemon logic is testable without a live phone (adapters mockable)

### Security

- No iMessage reverse-engineering or any path that risks the user's Apple ID
- No code that pulls data the iOS sandbox does not sanction (Messages DB, photos, files)
- Call recording / transcription (phase 5) is explicit, opt-in, and flags jurisdiction-specific consent obligations
- Pairing/bonding handled correctly; no plaintext storage of pairing secrets

### Severity Scale

- **Low**: cosmetic issues, minor inconsistencies
- **Medium**: functional gaps, missing edge cases, a quirk leaking into the UI
- **High**: data loss, security/Apple-ID risk, spec violation, hardcoded version assumption

---

## Release Criteria

*(default — customize for this project)*

### Required (all must PASS)

1. [ ] Phase definition-of-done met (for phase 1: a real SMS conversation held end-to-end on the reference device)
2. [ ] All automated tests pass on a clean checkout; daemon unit tests run without a phone
3. [ ] Lint/format clean (`ruff`, `black`)
4. [ ] No hardcoded iOS-version or iPhone-model assumptions introduced
5. [ ] LIMITATIONS.md updated if the change alters what the platform can/cannot do
6. [ ] Onboarding still surfaces the "Show Notifications" requirement and reconnect handling

### Informational (reported but non-blocking)

- On-device validation notes (which iOS-behavior assumptions were re-confirmed this cycle)
- Adapter/SCO audio observations relevant to the phase-3 R2 risk
