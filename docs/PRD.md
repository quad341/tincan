# PRD: HFP Modem Selection Race — Adapter-Aware Binding (tincan-3puyb)

**Status:** Approved (designer review complete 2026-06-24; pending architect approach decision for FR1–FR3)  
**Author:** tincan/planner  
**Date:** 2026-06-24  
**Source bead:** tincan-3puyb  
**Type:** Bug fix  
**Priority:** P2

---

## Problem Statement

`CallController._discover_modem()` selects an HFP modem by matching the
**remote device MAC fragment** in the oFono modem path. When the iPhone is
paired on two adapters (hci0 = built-in MT7925 / Intel; hci1 = RTL8761B /
ASUS USB-BT500 dongle) **both** oFono HFP modem paths match:

```
/hfp/org/bluez/hci0/dev_D0_6B_78_33_46_20   ← built-in, phantom
/hfp/org/bluez/hci1/dev_D0_6B_78_33_46_20   ← dongle (working SCO audio)
```

The sort-by-`Online` tie-breaker that would normally disambiguate cannot
help **at cold start** because neither modem has completed its
service-level connection (SLC) yet — both are `Online=false`. The
controller then binds whatever `GetModems()` returns first, which is
consistently `hci0` (the wrong adapter, whose SCO path produces no audio).

The `--adapter /org/bluez/hci1` flag passed to `tincand` is never
consulted during modem candidate selection; `self._adapter_hci` is stored
but not used in `_discover_modem()`. Once the controller binds `hci0`, it
never re-binds: `_on_modem_added` is a no-op when `_modem_path` is
already set, and there is no handler for the `Online` property transition.

**Who is affected:** Any tincan user where the iPhone is paired to both the
built-in adapter (hci0) and a dongle (hci1) and the machine has been
rebooted. This is the live roglet configuration post-tincan-zye6c.

**Current impact:** After a cold boot, every call silently routes through
the wrong adapter. SCO audio fails. Manual workaround: `busctl SetProperty
Powered=true` on the hci1 modem, then `systemctl --user restart tincand`.
This is not a user-survivable failure mode.

---

## Goals

| # | Goal | Measurable Outcome |
|---|------|--------------------|
| G1 | Prefer the configured adapter during modem selection | At cold start, `CallController` binds the modem on the `--adapter` hciN, never a phantom on another adapter |
| G2 | Bind the correct modem even when it is Offline at discovery time | Controller defers commitment; binds hci1 modem when it goes Online, not hci0 because it happened to appear first in `GetModems()` |
| G3 | Re-bind if the active modem goes Offline and a better candidate appears | Controller re-selects when the preferred modem comes Online while the current binding is absent or Offline |
| G4 | Honour `--adapter` / `TINCAN_ADAPTER` / QSettings adapter_path in modem selection | The resolved adapter_hci already in `self._adapter_hci` is actually used to rank or filter candidates |
| G5 | No regressions on single-adapter setups | When only one HFP modem exists (one adapter), behaviour is unchanged |

## Non-Goals

- Fixing `verify_dongle_adapter()` false-positive WARNING — covered by tincan-gnmdv (separate bead, separate PR)
- Auto-discovering the phone device and dropping `--device` — covered by tincan-j16uo
- Changing SCO audio routing, PipeWire wiring, or `setup_sco_routing()` — separate concern
- Adding any user-visible UI changes — this is entirely daemon-internal
- Implementing a persistent adapter preference in QSettings (adapter_path already flows through `_resolve_adapter_path()` → `adapter_hci` → `CallController`; no new config surface needed)
- Supporting more than two adapters or arbitrary multi-adapter topologies — the fix must be correct for N adapters but is only tested on the 2-adapter (hci0 + hci1) reference configuration

---

## User Stories

| ID | Story |
|----|-------|
| US1 | As a developer rebooting roglet, I want tincand to automatically bind the dongle (hci1) modem when it goes Online, without any manual busctl commands, so calls work immediately after boot. |
| US2 | As a tincan user on a single-adapter machine, I want modem selection to work exactly as before, so this fix does not introduce regressions for the common case. |
| US3 | As a developer reading tincand logs after a boot, I want to see a clear log line identifying which HFP modem was selected and why (preferred adapter vs fallback), so I can diagnose future selection failures. |
| US4 | As a user whose dongle is temporarily disconnected, I want the controller to fall back to any available HFP modem, not wait forever for the preferred one, so calls can still work in degraded mode. |

---

## Functional Requirements

### FR1 — Adapter-preference in candidate ranking

`_discover_modem()` MUST rank candidates by adapter preference BEFORE the
`Online` sort:

```
Preferred adapter (hciN matches self._adapter_hci) AND Online   → rank 0
Preferred adapter (hciN matches self._adapter_hci) AND Offline  → rank 1
Non-preferred adapter AND Online                                 → rank 2
Non-preferred adapter AND Offline                                → rank 3
```

When `self._adapter_hci` is empty (no adapter configured), all candidates
are treated as equally preferred (no change from current behaviour).

**Acceptance criterion:** After a cold boot with both hci0 and hci1 modems
Offline, the controller schedules a retry (does not bind immediately) and
binds the hci1 modem when it transitions to Online, not hci0.

### FR2 — Watch `PropertyChanged("Online")` on candidate modems

When `_discover_modem()` finds an Offline preferred-adapter modem but no
Online preferred-adapter modem, the controller MUST subscribe to
`org.ofono.Modem::PropertyChanged` on that modem path and bind when
`Online=true` is received.

This subscription replaces (or supplements) the existing retry loop for the
cold-start case, giving sub-second bind time instead of the 1–15s retry
ladder.

**Acceptance criterion:** On a warm-ish reboot where the hci1 SLC settles
3–10s after tincand starts, the controller binds the hci1 modem within 1s
of the `Online=true` signal, without any manual intervention.

### FR3 — Re-bind when a better modem becomes available

`_on_modem_added` currently no-ops if `_modem_path is not None`. Instead:

- If the new modem is on the preferred adapter AND the current binding is
  on a non-preferred adapter (or no binding), the controller MUST re-bind
  to the new modem.
- If the current binding goes Offline (`_on_modem_removed`) and a
  preferred-adapter modem is already Online, the controller MUST bind it
  immediately (not wait for `ModemAdded`).

**Acceptance criterion:** If tincand is running with the wrong modem bound
(hci0) and the hci1 modem comes Online, the controller re-binds to hci1
and logs the switch.

### FR4 — Fallback to non-preferred adapter when preferred is absent

If no modem matching `self._adapter_hci` exists (e.g., dongle unplugged),
the controller MUST fall back to any available iPhone HFP modem, preserving
current degraded-mode behaviour. A WARNING log MUST be emitted when a
non-preferred modem is bound.

**Acceptance criterion:** With hci1 unplugged, the controller binds the
hci0 modem (with a WARNING) and calls proceed (even if SCO audio is
degraded).

### FR5 — Log adapter selection rationale

Every `_bind_modem()` call MUST include a log line stating the bound modem
path and whether it is the preferred adapter or a fallback.

```
INFO  CallController: bound to HFP modem /hfp/org/bluez/hci1/dev_... (preferred adapter hci1)
WARN  CallController: bound to HFP modem /hfp/org/bluez/hci0/dev_... (fallback — preferred adapter hci1 not available)
```

Additionally, two states introduced by FR2 and FR3 MUST also emit log lines
(added per designer review 2026-06-24, tincan-rl848):

**FR2 deferred-bind entry (Gap 1):** When the preferred modem is found but
Offline, and the controller defers binding to wait for `PropertyChanged`:

```
INFO  CallController: preferred adapter hci1 modem is Offline — deferring bind, watching PropertyChanged
```

**FR3 re-bind event (Gap 2):** When the controller switches from a
non-preferred modem to the preferred one that has come Online:

```
INFO  CallController: re-binding to preferred adapter hci1 modem (was bound to /hfp/org/bluez/hci0/dev_...)
```

All log lines MUST use the bare `hciN` name (not the full adapter path) in
the parenthetical and MUST include the full modem path as the primary
identifier, consistent with the `CallController:` prefix convention.

### FR6 — Optional: proactively force preferred modem Online

If the preferred-adapter modem is found in `GetModems()` but is Offline,
the controller MAY call `SetProperty Powered=true` on it via
`org.ofono.Modem` to proactively initiate SLC establishment. This is the
"deterministic force" option from the bead (direction 3).

This requirement is marked **optional (SHOULD)**: the architect decides
whether to couple modem bring-up to the controller or leave it to oFono /
BlueZ. If implemented, FR6 is subordinate to FR2 (the Online watch must
work regardless).

**Acceptance criterion (if implemented):** tincand log shows modem
`Powered=true` set before the SLC settles, reducing the time-to-Online
on cold start.

---

## Non-Functional Requirements

| # | Requirement | Metric |
|---|-------------|--------|
| NF1 | Test coverage | Unit tests MUST cover: cold start (both Offline → deferred bind on Online transition); preferred Online (immediate bind); non-preferred Online only (fallback bind with WARNING); re-bind when better modem appears; no adapter configured (existing sort-by-Online behaviour). Tests MUST run without a live oFono bus. |
| NF2 | No D-Bus calls on the hot path | The adapter-preference check uses `self._adapter_hci` (resolved at startup). No new `GetManagedObjects()` or `GetProperties()` calls per modem event. |
| NF3 | Retry ladder preserved | The existing `_RETRY_STEPS` ladder (1 → 2 → 4 → 8 → 15s) MUST remain as the last-resort fallback when no modem is found at all, so the controller does not spin-poll. The `PropertyChanged` subscription from FR2 is the fast path. |
| NF4 | Signal subscription cleanup | Any `PropertyChanged` subscription on a candidate modem path MUST be cancelled when that modem is removed or when the controller binds a different modem, to prevent stale subscriptions accumulating across re-bind cycles. |

---

## Technical Constraints

From `docs/PROJECT_MANIFEST.md` and live code review:

1. **`self._adapter_hci` is already available** — extracted from the
   configured adapter path at startup in `__main__.py` (line 170:
   `adapter_hci = _hci_m.group(1) if _hci_m else ""`). No constructor
   change needed to pass it in; it is already a `CallController` field.

2. **oFono modem path format confirmed** — `/hfp/org/bluez/hciN/dev_<remote-mac>`
   (verified live on roglet 2026-06-23). Extracting the hciN segment for
   comparison is safe; this is the canonical oFono path format.

3. **`_on_modem_added` is the correct hook for re-bind** — already wired to
   `ModemAdded` signal; extend its logic rather than adding a new signal.

4. **`PropertyChanged` signal** — on the `org.ofono.Modem` interface;
   delivered with `(name: str, value: variant)`. Online transition is
   `name == "Online"` and `bool(value) == True`.

5. **GLib mainloop context** — all D-Bus signal callbacks execute in the
   GLib mainloop; no additional threading needed.

6. **Retry ladder side-effects** — `_retry_index` must be reset on
   successful bind (already done in `_bind_modem()`).

7. **Python conventions** — `ruff` + `black`; type hints on the modified
   methods; `dbus` import deferred inside methods to preserve testability.

---

## Candidate Approaches (for Architect)

| # | Approach | Trade-offs |
|---|----------|------------|
| A1 | **Rank-then-defer:** Add adapter-preference to the sort key in `_discover_modem()`. If top candidate is Offline and on the preferred adapter, subscribe to its `PropertyChanged` and return without binding. Cancel subscription on bind or modem-removed. | Clean, single place of truth. FR2 and FR3 both handled in `_discover_modem()` and `_on_modem_added`. Requires tracking the pending-subscription state. |
| A2 | **Strict filter then watch:** If `adapter_hci` is set, discard any modem NOT on the preferred adapter from consideration entirely (unless none exist). Among preferred candidates, watch Online and bind when it arrives. Fall back to non-preferred only after a timeout (e.g., 15s after `_RETRY_STEPS` is exhausted). | More aggressive — never accidentally binds the wrong adapter early. Risk: if the preferred modem never comes Online (e.g., dongle disconnected), user waits the full timeout before fallback. |
| A3 | **Force-up then watch (A1 + FR6):** A1 plus a `SetProperty Powered=true` call on the preferred Offline modem to actively trigger SLC establishment, then watch for Online. | Fastest cold-start resolution. Adds oFono write coupling; if oFono rejects the call (e.g., modem already being powered up by BlueZ), the error must be suppressed gracefully. |

---

## Dependencies

| Dependency | Status | Notes |
|-----------|--------|-------|
| `self._adapter_hci` in `CallController` | Present | Already passed at construction from `__main__.py`; no change needed. |
| `org.ofono.Modem::PropertyChanged` signal | Available | Standard oFono interface; no new D-Bus object import needed. |
| `org.ofono.Modem::SetProperty Powered` | Available | Used in FR6 (optional). Same interface as PropertyChanged; no new object needed. |
| tincan-gnmdv (`verify_dongle_adapter` fix) | Separate | Must NOT be mixed into this bead — different root cause, different module, already has its own PRD. |
| tincan-j16uo (`--device` auto-discover) | Separate | MAC-fragment matching in `_is_hfp_iphone_modem()` is out of scope here; that bead owns the device selection logic. |
| oFono `hfp_hf_bluez5` plugin | Required | Must be running on the system bus. No change to the oFono dependency. |

---

## Open Questions

| # | Question | Needed from |
|---|----------|-------------|
| OQ1 | Should the fallback timeout (A2) be configurable, or is the existing `_RETRY_STEPS` ladder (≈30s total) sufficient? | Architect |
| OQ2 | Is FR6 (proactive `SetProperty Powered=true`) worth the extra oFono coupling, given that A1 already covers the cold-start case via `PropertyChanged`? | Architect / Jim |
| OQ3 | Should `_on_modem_removed` trigger re-bind to the preferred adapter if it is already Online at that moment, or always go through the retry ladder? | Architect |
| OQ4 | Is there a risk that oFono's `ModemAdded` fires before `PropertyChanged("Online")` settles, causing a brief double-bind? Need to confirm the oFono event ordering. | Architect |
