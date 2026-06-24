# HFP Modem Selection — Adapter-Aware Binding (tincan-3puyb)

**PM bead:** tincan-rl848 (design review complete 2026-06-24)  
**PRD:** docs/PRD.md  
**Architecture bead:** tincan-t9met (CLOSED — A1 approved)  
**Designer review bead:** tincan-fv4j0 (CLOSED — A1 approved with 2 required fixes)  
**Date:** 2026-06-24

---

## Goal

Fix `CallController._discover_modem()` so that at cold start and during
runtime, the controller always binds the HFP modem on the configured
adapter (`--adapter /org/bluez/hci1`) rather than whichever modem appears
first in `GetModems()`.

All changes are daemon-internal (`tincand/call_controller.py`). No GUI
surface changes, no new QSettings keys, no new D-Bus object imports.

---

## Context

When the iPhone is paired on both adapters, two oFono modems match:

```
/hfp/org/bluez/hci0/dev_D0_6B_78_33_46_20   ← built-in (phantom, no SCO audio)
/hfp/org/bluez/hci1/dev_D0_6B_78_33_46_20   ← dongle (working SCO audio)
```

At cold start both are `Online=false` so the Online-first sort cannot
disambiguate. The controller binds hci0, SCO audio fails. Manual fix
required after every reboot.

`self._adapter_hci` already holds the configured value ("hci1") but is
never consulted in `_discover_modem()`.

---

## Designer Verdict (tincan-rl848, 2026-06-24)

Approve PRD. No GUI surface, no new QSettings key. Two FR5 log-line
additions incorporated into PRD:

- **Gap 1 (FR2):** INFO on deferred-bind entry: "preferred adapter hci1 modem is Offline — deferring bind, watching PropertyChanged"
- **Gap 2 (FR3):** INFO on re-bind: "re-binding to preferred adapter hci1 modem (was bound to /hfp/org/bluez/hci0/dev_...)"

---

## Architecture Status

tincan-t9met is CLOSED. Architect selected A1 (rank-then-defer with PropertyChanged watch).
FR6 (proactive SetProperty Powered=true) deferred to tincan-odlh9.

## Designer Review (tincan-fv4j0, 2026-06-24)

Designer approved A1. Two required changes before implementation closes:

- **R2 (required):** Re-bind log missing from `_bind_modem()`. When switching
  from non-preferred to preferred modem at runtime, the log is indistinguishable
  from cold-start bind. Add pre-check: if `self._modem_path` is set and differs
  from `path`, emit INFO "re-binding to HFP modem %s (was bound to %s)". → tincan-5jeeu
- **T1–T4 (required):** Test infrastructure for §A–§J needs `adapter_hci` param
  in `_make_controller_with_modems`, oFono-format paths, PropertyChanged callback
  capture, and §J hci10/hci1 disambiguation test. → tincan-aggkh (updated)

Also recommended (P2–P3, non-blocking):
- R1 (P2): Merge deferred-bind rationale into `_subscribe_modem_online` log wording
- R3 (P3): Remove duplicate WARN from `_discover_modem()` fallback path
- R4 (P3): Add DEBUG log in stale-path guard → tincan-eld4u

---

## Bead Tree

```
tincan-t9met  [architect — CLOSED]
    ├── tincan-3vc85  [builder — CLOSED] Adapter-aware modem selection (FR1–FR5)
    │   ├── tincan-5jeeu  [builder — open] R2: re-bind detection log in _bind_modem()
    │   ├── tincan-aggkh  [validator — in progress] Unit tests §A–§J (updated T1–T4)
    │   └── tincan-eld4u  [builder — open] Log polish (R1/R3/R4)
    └── tincan-odlh9  [builder, deferred] FR6: proactive SetProperty Powered=true
```

---

## Beads

| ID | Title | Status | Target | Depends on |
|----|-------|--------|--------|------------|
| tincan-3vc85 | Adapter-aware modem selection (FR1–FR5) | CLOSED | builder | tincan-t9met |
| tincan-5jeeu | R2: re-bind detection log in _bind_modem() | open | builder | tincan-3vc85 |
| tincan-aggkh | Unit tests: modem selection §A–§J (NF1) | in progress | validator | tincan-3vc85 |
| tincan-eld4u | Log polish: R1/R3/R4 | open | builder | tincan-3vc85 |
| tincan-odlh9 | FR6: proactive SetProperty Powered=true | open (deferred) | builder | tincan-t9met + architect approval |

---

## Core Builder Bead — Acceptance Criteria

**FR1:** `_discover_modem()` ranks candidates: preferred+Online (0) → preferred+Offline (1) → non-preferred+Online (2) → non-preferred+Offline (3). When `adapter_hci` is empty, all candidates rank equally (no regression).

**FR2:** When top candidate is preferred+Offline, controller subscribes to `org.ofono.Modem::PropertyChanged` and defers bind. Binds within 1s of `Online=true` signal. Emits FR5 Gap 1 log line at deferral entry.

**FR3:** `_on_modem_added` re-binds to preferred-adapter modem if currently bound to non-preferred. `_on_modem_removed` / PropertyChanged handler re-binds immediately if preferred is already Online. Emits FR5 Gap 2 log line on re-bind.

**FR4:** Falls back to any available iPhone HFP modem with WARN log when no preferred-adapter modem exists.

**FR5:** Every `_bind_modem()` call emits INFO (preferred) or WARN (fallback). Deferred-bind and re-bind transitions emit additional INFO lines per designer review.

**NF2:** No new `GetManagedObjects()` / `GetProperties()` calls per modem event — `self._adapter_hci` is used directly.

**NF3:** Existing `_RETRY_STEPS` ladder (1→2→4→8→15s) preserved as last-resort when no modem found at all.

**NF4:** Every `PropertyChanged` subscription on a candidate modem path is cancelled on: bind, modem-removed, or re-bind to a different modem.

---

## Validator Bead — Test Scenarios (NF1)

Must run without a live oFono bus (mock D-Bus):

| Scenario | Expected behaviour |
|----------|--------------------|
| Cold start: both hci0+hci1 Offline | Defers bind; binds hci1 within 1s of Online signal; does NOT bind hci0 |
| Preferred Online at discovery | Binds hci1 immediately with INFO log |
| Only non-preferred Online | Binds hci0 with WARN log (fallback) |
| Re-bind: running on hci0, hci1 comes Online | Re-binds to hci1 with Gap 2 INFO log |
| No adapter configured (`adapter_hci=""`) | Falls through to existing sort-by-Online; no regression |
| Subscription cleanup | No stale `PropertyChanged` subscriptions after bind or modem-removed |

---

## Deferred: FR6 Bead

If architect approves FR6 (OQ2), a separate builder bead will implement
`SetProperty Powered=true` on the preferred Offline modem to proactively
trigger SLC establishment. FR6 is subordinate to FR2 (the Online watch must
work regardless of whether FR6 is present).

---

## Dependencies

| Bead | Notes |
|------|-------|
| tincan-gnmdv | `verify_dongle_adapter()` fix — MUST NOT be mixed into this work; separate PR |
| tincan-j16uo | `--device` auto-discover — separate bead; `_is_hfp_iphone_modem()` MAC-fragment matching is out of scope here |

---

## Build Order

1. ~~tincan-t9met closes (architect) → unblocks builder~~ DONE
2. ~~Builder implements FR1–FR5 in `call_controller.py`~~ DONE (tincan-3vc85)
3. Builder fixes re-bind log in `_bind_modem()` (tincan-5jeeu) — unblocked
4. Validator completes unit tests §A–§J with T1–T4 infrastructure (tincan-aggkh) — in progress
5. Builder applies log polish R1/R3/R4 (tincan-eld4u) — unblocked, P3
6. (Deferred) FR6 builder bead if architect approves (tincan-odlh9)
