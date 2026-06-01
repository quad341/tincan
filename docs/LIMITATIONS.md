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

## Out of scope by design

- **iMessage reverse-engineering** (pypush / Beeper Mini lineage). Ban-prone (Apple
  actively blocked Beeper Mini) and a DMCA/ToS gray area. Excluded from the core;
  if ever added, it is an isolated, clearly-labeled-risky, optional module — never
  load-bearing.
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
