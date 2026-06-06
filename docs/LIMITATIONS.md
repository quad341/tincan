# Tincan — Known Limitations

The honest list of what Tincan **cannot** do, and why. These are mostly platform
constraints baked into how Apple exposes the iPhone to Bluetooth accessories —
not bugs we can fix. Microsoft Phone Link for iPhone hits the same walls. Read
this before promising anyone a feature.

Sources for every claim here are in [PROTOCOLS.md](PROTOCOLS.md).

## Messages (SMS)

- **No full message history.** MAP gives a recent window (~10 messages in the
  inbox by default) plus live updates during a session — not an archive. You
  cannot browse arbitrary past conversations or search old texts.
- **Group-text sender attribution is lossy.** iOS omits the extra contact info for
  group messages, so "who said what" in a group thread may be ambiguous.
- **iMessage is not a first-class citizen.** Outbound messages auto-upgrade to
  iMessage when the recipient is on iMessage (good), but Tincan does not implement
  iMessage features (tapbacks, threads, blue-bubble fidelity, attachments).
  Whether *incoming* iMessages even appear over MAP is unconfirmed — evidence so
  far shows SMS only. **(to verify on iOS 26.5)**
- **Group MMS sending / media sending is unsupported / unreliable** (mirrors Phone
  Link). Treat as out of scope.
- **The iPhone must have "Show Notifications" enabled** for the paired laptop, or
  iOS drops the messaging link entirely. This is a hard requirement, surfaced in
  onboarding.

## Rich messaging (RCS receipts, typing, edits) — not available

iOS supports RCS — read receipts, delivery receipts, typing indicators, and (now
rolling out on iOS 26.x via Universal Profile 3.0) message edit/unsend — but only
*inside* the Messages app. **None of that rich metadata is reachable over the
Bluetooth profiles Tincan uses, and there is no path to it without
reverse-engineering proprietary Apple protocols** (CarPlay / iMessage — see *Out of
scope* below). Two independent walls:

- **RCS does not travel over MAP at all.** iOS routes RCS through the Messages
  app's data (IP) stack, not the legacy MAP MSE that car kits and Tincan read over
  Bluetooth. MAP surfaces SMS/MMS only — RCS messages simply do not appear in the
  MAP inbox, and changing the MAP version (1.2 → 1.4) does not change this. No RCS
  message on the MSE means there is no MAP delivery/read event to receive. This is
  the same wall every Bluetooth car kit hits with RCS.
- **ANCS carries notifications, not receipts.** A delivery receipt, a read
  receipt, or a typing indicator on *your* outgoing message does not post a
  notification on your phone, so ANCS never sees it. (An *edit* by the other party
  may re-post a notification showing the edited text, but as an opaque
  Added/Modified notification — subject to "Show Previews" — with no structured
  "this edits message X" semantics. Not a usable receipt/edit event.)

Even if iOS *did* route RCS over MAP, MAP's own data model only cleanly carries a
**delivery** receipt (the `DeliverySuccess` event); read receipts map to local
read-state (`ReadStatusChanged`), typing has no transport outside the MAP-IM
extensions iOS does not implement, and message *edits* have no MAP event at all —
and all of those ride MNS, the fragile MAP-event path Tincan deliberately avoids.

**What you still get for RCS:** an incoming RCS message posts a normal Messages
notification, so its *body* arrives over ANCS like any other text (subject to
"Show Previews"). Fetching RCS bodies over MAP is unreliable. Note the existing
"Delivered ✓" marker is a **local heuristic** — the self-sent message echoing back
to us over MAP — **not** a carrier/recipient delivery receipt; don't conflate them.

## Notifications (ANCS)

- **Body text obeys the iOS "Show Previews" setting.** If the user sets previews to
  "When Unlocked" or "Never," Tincan sees the same abbreviated/empty content — it
  cannot see more than the notification system itself reveals.
- **Only two notification actions: Positive and Negative** (e.g. answer/decline a
  call). There is **no arbitrary reply** and **no generic dismiss** over ANCS. (For
  *replying* to a text, Tincan uses MAP's send, not ANCS.)
- **No notification history** — ANCS is a live stream, not a backlog.

## Calls (HFP — phase 3)

- **Call-audio stability is hardware-dependent.** SCO audio over integrated combo
  chips (including the reference machine's MediaTek-class adapter) is historically
  unreliable; a known-good USB Bluetooth dongle may be required.
- **DTMF into phone-tree / IVR menus is flaky on iOS** — tone-dialing into "press 1
  for…" systems may not work reliably.
- **Multiparty / 3-way calling is conditional** on the carrier/phone advertising
  it; not guaranteed.
- **BT headset → computer → phone relay is unsupported.** Bridging a wireless
  headset through the computer to the phone (computer acts as HFP Audio Gateway
  to the headset *and* HFP Hands-Free to the phone simultaneously) would require
  two concurrent SCO audio links — most Bluetooth controllers support only one SCO
  link at a time. Two USB Bluetooth adapters on one host would solve it, but that
  is niche hardware and untested. The autonomous-calling use case (computer as the
  audio endpoint) does not need this relay.

## Out of scope by design

- **iMessage reverse-engineering** (pypush / Beeper Mini lineage). Ban-prone (Apple
  actively blocked Beeper Mini) and a DMCA/ToS gray area. Excluded from the core;
  if ever added, it is an isolated, clearly-labeled-risky, optional module — never
  load-bearing.
- **CarPlay as a transport.** CarPlay *does* surface RCS and richer message data
  on the car screen — but only over Apple's MFi-licensed, proprietary iAP2/CarPlay
  channel, not a vendor-neutral Bluetooth profile a Linux laptop can speak.
  Becoming a CarPlay receiver requires Apple hardware certification; reaching it
  otherwise means reverse-engineering a proprietary protocol. Out of scope for the
  same reason as iMessage RE.
- **Anything requiring a Mac** (e.g. the BlueBubbles bridge model). Defeats the
  point of a laptop-as-Bluetooth-accessory design.
- **Reading arbitrary iPhone data** (full Messages database, photos, files,
  arbitrary app data). The iOS sandbox does not expose these to a Bluetooth
  accessory, full stop.
- **Running with no app open on the iPhone but expecting app-level access.** Tincan
  works *because* it uses OS-level Bluetooth profiles; it deliberately does **not**
  rely on any companion app running on the iPhone (which the iOS sandbox would
  cripple anyway — see KDE Connect's iOS limits).

## Things to confirm (phase-0 spike may move items in or out)

- SMS body reliably available over MAP on iOS 26.5.
- Whether any iMessage content appears over MAP.
- ANCS reliably firing for Messages (with sender) on iOS 26.5.
- Built-in adapter holding simultaneous BLE (ANCS) + Classic (MAP) to one phone.
- RCS absent from the MAP inbox on iOS 26.5 — enable RCS, hold an active RCS
  conversation, then list the MAP inbox via `spikes/m01_map.py` and confirm the
  RCS messages do not appear (or appear only as SMS fallbacks). Expected: absent.
