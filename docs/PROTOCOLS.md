# Tincan — Protocol & iOS-Behavior Reference

Technical reference for the Bluetooth profiles Tincan depends on, how iOS
actually behaves over each, and the sources behind those claims. Compiled from
research on 2026-05-31. Treat anything marked **(verify)** as something to
confirm empirically on the iOS 26.5 reference device during the phase-0 spike —
much of the public iOS-MAP behavior data is old or sparse.

---

## Overview: the four profiles

| Profile | Transport | Tincan uses it for | iOS role | Linux surface |
|---------|-----------|--------------------|----------|---------------|
| **ANCS** — Apple Notification Center Service | Bluetooth **LE** (GATT) | notifications + instant "new SMS" trigger | GATT server (Notification Provider) | BlueZ GATT client (fork ancs4linux) |
| **MAP** — Message Access Profile | Bluetooth Classic (RFCOMM/OBEX) | SMS list / fetch body / **send** | MAP server (MSE) | obexd `org.bluez.obex.MessageAccess1` |
| **HFP** — Hands-Free Profile | Classic (RFCOMM control + SCO audio) | calls + call audio | Audio Gateway (AG) | oFono `hfp_hf` plugin + PipeWire |
| **PBAP** — Phone Book Access Profile | Classic (OBEX) | contact names | PBAP server | obexd |

The key insight: these are all **vendor-neutral profiles Apple supports for car
kits / accessories**. Tincan's laptop plays the *accessory / client* side of
each. This is exactly the stack Microsoft Phone Link for iPhone uses.

---

## ANCS (Apple Notification Center Service)

BLE GATT service the iPhone publishes so an accessory (the laptop, like a watch)
can consume the phone's notifications. Phone = Notification Provider / GATT
server; laptop = Notification Consumer / GATT client.

**Characteristics (UUIDs):**
- Notification Source `9FBF120D-6301-42D9-8C58-25E699A21DBD` (notify, mandatory)
- Control Point `69D1D8F3-45E1-49A8-9821-9BBDFDAAD9D9` (write-with-response)
- Data Source `22EAC6E9-24D6-4BB5-BE44-B36ACE7C7BFB` (notify)

**Per-notification attributes:** AppIdentifier (e.g. `com.apple.MobileSMS`),
Title, Subtitle, **Message** (the real body, UTF-8), MessageSize, Date,
PositiveActionLabel, NegativeActionLabel. Notification events also carry an
EventID (Added/Modified/Removed), EventFlags (Silent, Important, PreExisting,
PositiveAction, NegativeAction), and a CategoryID (IncomingCall, MissedCall,
Voicemail, Social, Email, …).

**What you get:** full title + body text — including SMS/iMessage body — **subject
to the iOS "Show Previews" setting**. If the user sets previews to "When Unlocked"
or "Never," the Message attribute is correspondingly abbreviated/empty, because
ANCS only ever sees what the notification system exposes.

**Hard limits:**
- **Only two actions exist: Positive and Negative.** No arbitrary reply, no
  generic "dismiss." (`UNNotificationDismissActionIdentifier` is an app-side
  UserNotifications concept, *not* an ANCS command.) You cannot type a reply back
  over ANCS — that's why MAP is needed for sending.
- Bonding (encrypted pairing) is **mandatory** before any characteristic works;
  then enable the CCCD on Notification Source to start receiving.
- No standardized latency or screen-unlock figure in the spec; real behavior is
  governed by iOS's per-app preview settings **(verify on 26.5)**.

**Linux prior art:** `ancs4linux` (BlueZ + D-Bus, advertises as a peripheral) —
**author-abandoned** ("I am no longer using this project… should still work"),
code mostly 2021–2022, but a tooling refresh landed 2026-05-24. Expect to harden
reconnection (open issue #5) and pairing persistence. Also: a Rust ANCS lib
(`ianmarmour/ancs`), reference consumers on nRF / ESP32.

**Companion service — AMS (Apple Media Service):** separate BLE GATT service for
media control (now-playing metadata + play/pause/next/volume). Media only, no
messages. Optional nice-to-have, not on the critical path.

Sources:
- ANCS spec: <https://developer.apple.com/library/archive/documentation/CoreBluetooth/Reference/AppleNotificationCenterServiceSpecification/Specification/Specification.html>
- ANCS attribute/category appendix: <https://developer.apple.com/library/archive/documentation/CoreBluetooth/Reference/AppleNotificationCenterServiceSpecification/Appendix/Appendix.html>
- ancs4linux: <https://github.com/pzmarzly/ancs4linux>
- Rust ANCS: <https://github.com/ianmarmour/ancs>
- AMS spec: <https://developer.apple.com/library/archive/documentation/CoreBluetooth/Reference/AppleMediaService_Reference/Introduction/Introduction.html>

---

## MAP (Message Access Profile) — the SMS path

Laptop = MAP client (MCE); iPhone = MAP server (MSE). iOS has exposed a MAP MSE
since the iPhone 4 era; it is on automatically whenever Bluetooth is enabled
(no separate toggle).

**What iOS exposes:**
- Standard folder tree: `telecom/msg/{inbox,sent,outbox,deleted}`.
- Inbox listing returns a **recent window (~10 messages by default)**, not full
  history; other folders start empty and update live during a session.
- **`GetMessage` returns the full bMessage body** — body text, sender vCard,
  status, type, charset.
- **`PushMessage` (sending) works** — iOS treats it as a message composed in the
  Messages app; fires `Sent` on success.
- **SMS vs iMessage:** outbound auto-upgrades to iMessage when the recipient is on
  iMessage, else SMS. Inbound evidence shows **SMS_GSM** types; whether iMessage
  threads appear in the MAP inbox is **unconfirmed (verify)** — R6.

**Known iOS quirks (build around these):**
- **Hard requirement:** the paired device must have **"Show Notifications" enabled**
  in iOS Bluetooth device settings, or iOS **drops the MAP link immediately**.
- **Sent-folder bug:** `GetMessage` on a sent message reports
  `FOLDER:telecom/msg/inbox` instead of `sent`.
- **Group texts:** iOS omits the extra contact info, making sender attribution
  hard.
- Behavior with the phone **locked** is undocumented **(verify)**.

**Linux surface — obexd:** `org.bluez.obex.MessageAccess1` (driven via D-Bus, or
the `obexctl`/`test/map-client` script for poking). Methods: `SetFolder`,
`ListFolders`, `ListMessages`, `ListFilterFields`, `UpdateInbox`, **`PushMessage`**
(send). Per-message download via `org.bluez.obex.Message1.Get(targetfile,
attachment)`; status via `Read`/`Deleted`/`Status` properties. The MAP client is
functional but **lightly maintained and historically finicky** (R4) — expect to
debug, and possibly patch upstream.

**MNS (real-time new-message push) — the weak link (R1):** in MAP, the server
pushes a MAP-Event-Report over the Message Notification Service when a new SMS
arrives; in obexd these surface as new `org.bluez.obex.Message1` objects via the
`ObjectManager` `InterfacesAdded` signal. But obexd's MNS support is the weakest,
least-maintained part of MAP on Linux, and it still requires the iOS "Show
Notifications" toggle to even stay connected. **Tincan's mitigation: don't rely on
MNS — use ANCS over BLE as the instant new-SMS trigger, then fetch the body over
MAP.** Polling `UpdateInbox`/`ListMessages` is a further fallback.

**No turnkey iOS tool exists.** Prior art is thin (Raspberry Pi service-discovery
scripts; unfinished Librem5 / Sailfish attempts that never reported iOS success).
Tincan builds on the obexd D-Bus API directly.

**RCS is not exposed over MAP (R7).** iOS handles RCS in the Messages app's
IP-based stack, not the MAP MSE, so RCS messages do not appear in the MAP inbox —
Bluetooth accessories see SMS/MMS only, regardless of MAP version (1.2 → 1.4).
That means RCS **delivery/read receipts, typing indicators, and message edits are
unobtainable** over MAP: the MAP-Event-Report machinery that *would* carry them
(`DeliverySuccess`, `ReadStatusChanged`, the MAP-IM `ParticipantChatStateChanged`)
is never populated for RCS, and rides the MNS path Tincan already avoids. ANCS
can't substitute — receipts/typing post no notification, so ANCS never sees them.
Reaching RCS metadata would require proprietary protocols (CarPlay's MFi-gated
channel, or iMessage reverse-engineering), both out of scope. See
[LIMITATIONS.md](LIMITATIONS.md).

Sources:
- iOS MAP behavior (folders, live updates, "Show Notifications" required): <https://developer.apple.com/forums/thread/732226>
- iOS bMessage body, sent-folder bug, group-text quirk: <https://developer.apple.com/forums/thread/709921>
- iOS MAP since iPhone 4, "Show Notifications" requirement: <https://discussions.apple.com/thread/5067487>
- obexd MessageAccess API (incl. PushMessage): <https://man.archlinux.org/man/extra/bluez-obex/org.bluez.obex.MessageAccess.5.en>
- obex-api.txt (Message1 Get, PushMessage, properties): <https://github.com/pauloborges/bluez/blob/master/doc/obex-api.txt>
- obexd MAP listing flakiness (BlueZ 5.65): <https://github.com/bluez/bluez/issues/1301>
- MAP v1.4.3 spec: <https://www.bluetooth.com/wp-content/uploads/2025/04/MAP_v1.4.3_showing_changes_from_MAP_v1.4.2.pdf>
- MAP-Event-Report types incl. `DeliverySuccess` / `ReadStatusChanged` (HTML spec): <https://www.bluetooth.com/wp-content/uploads/Files/Specification/HTML/MAP_v1.4.3/out/en/index-en.html>
- RCS does not traverse Bluetooth MAP (car-kit reports, Android + iPhone): <https://support.google.com/messages/thread/198326358/get-rcs-messaging-to-work-over-bluetooth>, <https://www.mazda3revolution.com/threads/bluetooth-text-messages-dont-work-w-rcs-chat-features-enabled.241694/>
- iOS RCS feature set + how to enable (read/delivery receipts, typing): <https://support.apple.com/en-us/122195>, <https://support.apple.com/en-us/104972>
- iOS 26.x RCS Universal Profile 3.0 (edit/unsend, E2EE) timeline: <https://www.macrumors.com/2026/01/13/ios-26-rcs-3-future-benefits/>

---

## HFP (Hands-Free Profile) — the calls path (phase 3)

Laptop = Hands-Free (HF) unit (the "car kit / headset"); iPhone = Audio Gateway
(AG). HFP is driven by AT commands over RFCOMM, with call audio over SCO/eSCO.

**Recommended Linux stack (2025–2026):** a *split* —
- **BlueZ** for pairing + RFCOMM/SCO transport,
- **oFono** (`hfp_hf_bluez5` plugin) for **call control via D-Bus**,
- **PipeWire** for **audio**, configured `bluez5.hfphsp-backend = ofono`.

PipeWire's *native* HFP backend gives audio but only a minimal AT subset — not a
full telephony controller. oFono owns the AT/RFCOMM channel; PipeWire owns the SCO
audio node. The `phony` project is a working reference of this exact stack.

> **Caution:** don't be misled by oFono's `doc/features.txt`, which describes the
> HFP *Audio Gateway / emulator* role (oFono pretending to be a phone). The role
> Tincan needs — HF *client* controlling the iPhone — lives in the separate
> `hfp_hf_bluez5` plugin.

**Call-control operations (and their oFono D-Bus equivalents):** dial (`ATD`/
`Dial`), redial (`AT+BLDN`), answer (`ATA`/`Answer`), reject/hangup (`AT+CHUP`/
`Hangup`/`HangupAll`), hold + multiparty (`AT+CHLD`/`SwapCalls`,
`CreateMultiparty`, …), DTMF (`AT+VTS`/`SendTones`), caller ID
(`+CLIP` → `LineIdentification` property), trigger Siri (`AT+BVRA`), volume
(`AT+VGS`/`AT+VGM`). iOS supports these as a standard car-kit target.

**Integration surface for the GUI:** use **oFono's D-Bus API, not raw AT**. The
iPhone appears as a `Type=hfp` modem.
- `org.ofono.VoiceCallManager`: `Dial`, `SendTones`, `SwapCalls`,
  `ReleaseAndAnswer`, `HangupAll`, `CreateMultiparty`, `GetCalls`; signals
  `CallAdded` / `CallRemoved`.
- `org.ofono.VoiceCall` (per call): `Answer`, `Hangup`, `Deflect`; properties
  `State`, `LineIdentification` (caller number), `Name`, `Multiparty`.

**Audio:** codecs CVSD (narrowband, mandatory) → mSBC (wideband) → LC3-SWB
(super-wideband, added in PipeWire 1.2; our 1.6.4 has it). Whether the iPhone
negotiates LC3-SWB with a Linux peer is **unverified** — expect mSBC/CVSD in
practice.

**iPhone / Linux gotchas:**
- **SCO audio stability is the #1 risk (R2).** Integrated combo chips (incl.
  MediaTek-class, like our adapter) frequently misbehave on SCO; a known-good USB
  dongle (CSR8510 / BCM20702) is the documented fallback. **Prototype audio on the
  real adapter before committing the calls UI.**
- **Profile auto-switch:** an iPhone may land on A2DP-only and not surface HFP;
  may need forcing the `hands-free` profile via WirePlumber.
- DTMF into IVR phone-trees is reported as **flaky on iOS**.
- **CallKit is unrelated** — it governs VoIP apps *on* the iPhone, not what an
  external Bluetooth HF accessory can do. Don't conflate.
- oFono is **not packaged on Fedora** — build from source / COPR (phase-3 prereq).

Sources:
- oFono `hfp_hf_bluez5` plugin: <https://github.com/rilmodem/ofono/blob/master/plugins/hfp_hf_bluez5.c>
- oFono VoiceCallManager API: <https://github.com/rilmodem/ofono/blob/master/doc/voicecallmanager-api.txt>
- oFono VoiceCall API: <https://github.com/rilmodem/ofono/blob/master/doc/voicecall-api.txt>
- PipeWire Bluetooth config: <https://pipewire.pages.freedesktop.org/wireplumber/daemon/configuration/bluetooth.html>
- PipeWire props (HFP backend, mSBC): <https://docs.pipewire.org/page_man_pipewire-props_7.html>
- `phony` reference HFP-HF stack: <https://github.com/littlecraft/phony>
- HFP AT-command reference: <https://www.silabs.com/documents/public/application-notes/AN992.pdf>

---

## PBAP (Phone Book Access Profile) — contacts

Laptop = client; iPhone = PBAP server (`Phonebook Access Server` UUID `112f`,
which the iPhone exposes). Used to resolve phone numbers → contact names in the
UI. Low risk, standard. Driven via obexd (`org.bluez.obex` phonebook API).
Likely implemented incidentally for name-resolution in phase 1, then finished in
phase 4.

---

## Cross-cutting: why not the alternatives?

- **KDE Connect / GSConnect on iOS:** crippled by the iOS app sandbox — an iOS app
  *cannot* read other apps' notifications and *cannot* run a background daemon.
  This is why the **Bluetooth-profile approach (ANCS/MAP/HFP) is the only viable
  path** — those run at the iPhone's OS/BT-stack level, independent of any app.
- **iMessage reverse-engineering (pypush / Beeper Mini, BlueBubbles):** out of
  core scope. pypush-lineage is ban-prone (Apple actively blocked Beeper Mini) and
  a DMCA/ToS gray area; BlueBubbles needs a real Mac, defeating the
  laptop-as-accessory model. See LIMITATIONS.md.

Sources:
- KDE Connect iOS limits: <https://github.com/KDE/kdeconnect-ios>, <https://tidbits.com/2022/05/12/kde-connect-brings-iphone-connectivity-to-linux/>
- Microsoft Phone Link for iPhone (existence proof + its documented limits): <https://support.microsoft.com/en-us/topic/phone-link-requirements-and-setup-cd2a1ee7-75a7-66a6-9d4e-bf22e735f9e3>, <https://support.microsoft.com/en-us/topic/troubleshooting-for-messages-in-the-phone-link-818c988d-a3b3-5ae1-39b2-095763da5a0f>
- pypush: <https://github.com/JJTech0130/pypush>; BlueBubbles: <https://github.com/BlueBubblesApp/bluebubbles-server>
