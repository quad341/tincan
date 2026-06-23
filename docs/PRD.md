# PRD: Fix `verify_dongle_adapter` False-Positive Warning (tincan-gnmdv)

**Status:** Draft  
**Author:** tincan/planner  
**Date:** 2026-06-23  
**Source bead:** tincan-gnmdv  
**Type:** Bug fix  
**Priority:** P3

---

## Problem Statement

`call_audio.verify_dongle_adapter(modem_path)` always returns `False` and emits a
spurious "HFP SCO audio likely broken" WARNING on every HFP modem bind, even when
the iPhone is correctly connected through the RTL8761B dongle (hci1 = A0:AD:9F:7A:15:8E).

**Root cause:** The function checks whether the adapter MAC fragment
`a0_ad_9f_7a_15_8e` appears in the oFono modem path. But oFono HFP modem paths
have the form `/hfp/org/bluez/<hciN>/dev_<remote-device-MAC>` — they encode the
adapter *name* (e.g., `hci1`) and the *remote device* MAC, never the local adapter
MAC. The fragment can never match.

**Who is affected:** All tincan users with a multi-adapter setup (built-in MT7925 +
RTL8761B dongle). Verified on roglet (2026-06-23): the WARNING fires on every call
even when audio works correctly.

**Current impact:** Benign in the short term — `call_controller.py:136` calls
`verify_dongle_adapter()` but ignores its return value; `setup_sco_routing`
(`:273`) is not gated on it. The warning is alarming and will erode confidence in
log-based diagnostics.

**Future risk:** If `verify_dongle_adapter()` is ever used to gate SCO routing (a
natural next step), a persistent `False` return would silently disable audio on all
calls on the dongle — the correct adapter.

---

## Goals

| # | Goal | Measurable Outcome |
|---|------|--------------------|
| G1 | Eliminate false-positive WARNING when modem is on the configured adapter | Zero "HFP SCO audio likely broken" log entries during a call on the dongle |
| G2 | Preserve the genuine WARNING when modem is on an unexpected adapter | WARNING fires when iPhone modem path contains a different hciN than the configured adapter |
| G3 | Remove the hardcoded adapter MAC (`a0_ad_9f_7a_15_8e`) from `call_audio.py` | No hardware-specific MAC constant in `call_audio.py` |
| G4 | Adapter-index-agnostic — survives hardware reordering | Check works correctly if hci indices change (e.g., dongle becomes hci0 on a different machine) |

## Non-Goals

- Gating `setup_sco_routing` on `verify_dongle_adapter()`'s return value (separate decision, not this fix)
- Changing the return type or external semantics of `verify_dongle_adapter()`
- Removing `verify_dongle_adapter()` entirely — it is a useful diagnostic and may be used as a gate in future
- Adding any UI changes or user-visible behavior changes (purely internal)
- Changing USB autosuspend verification (a separate check in the same file)

---

## User Stories

| ID | Story |
|----|-------|
| US1 | As a developer reading tincan logs during a call, I want to see no false "HFP SCO audio likely broken" warnings so I can trust log entries about real problems. |
| US2 | As a user with only the built-in MT7925 adapter (no dongle), I want a real WARNING in the logs if the call is on an adapter known to have SCO issues, so I know why audio may fail. |

---

## Functional Requirements

### FR1 — Correct adapter identity check
`verify_dongle_adapter(modem_path)` must return `True` if and only if the
`hciN` segment embedded in `modem_path` matches the `hciN` of the daemon's
currently configured adapter path.

- oFono modem paths have the form `/hfp/org/bluez/hciN/dev_XX_XX_XX_XX_XX_XX`
- The configured adapter path has the form `/org/bluez/hciN`
- Matching these two `hciN` values (e.g., both `hci1`) is sufficient and correct

### FR2 — No hardcoded adapter MAC or index
`call_audio.py` must not contain a hardcoded adapter MAC address (`_DONGLE_ADAPTER_FRAGMENT`) or a hardcoded hci index. The reference adapter identity must come from the daemon's resolved adapter path (already determined at startup by `_resolve_adapter_path()` in `__main__.py`).

### FR3 — No extra D-Bus call on the hot path
The fix must not introduce a `GetManagedObjects()` or any other D-Bus round-trip
inside `verify_dongle_adapter()`. The adapter path is already known at startup;
the check should use that cached value.

### FR4 — No regression in the negative case
When the modem's hciN does NOT match the configured adapter's hciN, the WARNING
must still be emitted (same message content is acceptable). The return value must
remain `False`.

### FR5 — `_DONGLE_ADAPTER_FRAGMENT` and `_DONGLE_USB_*` constants removed or scoped
If the adapter MAC / USB vendor+product constants in `call_audio.py` become
unreferenced after the fix, they must be removed. If they are still used by
`verify_usb_autosuspend_off()` or other callers, they may remain but should be
renamed/documented to reflect their real scope.

---

## Non-Functional Requirements

| # | Requirement | Metric |
|---|-------------|--------|
| NF1 | Test coverage | Unit tests must cover: modem on configured adapter (→ True), modem on other adapter (→ False), modem path with unexpected format (→ False, no crash) |
| NF2 | No D-Bus dependency in unit tests | Tests must be runnable without a live BlueZ bus (the adapter path is injected, not queried) |
| NF3 | Log output | INFO log on True, WARNING log on False — preserve current logging intent |

---

## Technical Constraints

From `docs/PROJECT_MANIFEST.md`:

1. **`tincand` owns all Bluetooth machinery** — `call_audio.py` is part of `tincand`; it may use BlueZ D-Bus but should prefer already-resolved values over new queries.
2. **`adapter_check.py` provides `list_adapters()`** — already enumerates adapters with `path` and `address`; usable from within `tincand` if a D-Bus call is needed at init time (not on the hot path).
3. **`_resolve_adapter_path()` (`__main__.py`)** — resolves the configured adapter at daemon startup; result (`/org/bluez/hciN`) is already propagated to the `TincanService` (`service.set_adapter_path()`).
4. **`CallController`** — currently receives no adapter path at construction; it only receives `system_bus` and `service`. If the fix requires injecting adapter identity into `CallController`, that constructor signature will change.
5. **Conventions** — Python; `ruff` + `black`; type hints on public daemon APIs.

---

## Candidate Approaches (for Architect)

The architect should select one of these or propose an alternative:

| # | Approach | Trade-offs |
|---|----------|------------|
| A1 | **Inject hciN via `CallController` constructor** — parse `hciN` from the resolved adapter path at startup; pass it to `CallController.__init__`; update `verify_dongle_adapter(modem_path, expected_hci: str)` to compare hciN segments. | Clean, testable, no D-Bus on hot path. Requires constructor change. |
| A2 | **Module-level cache in `call_audio.py`** — add `set_expected_adapter(adapter_path: str)` to `call_audio.py`; call it from `main()` after `_resolve_adapter_path()`; `verify_dongle_adapter()` reads the module cache. | No constructor change. Slightly less explicit. Requires care in tests (cache reset). |
| A3 | **BlueZ lookup inside `verify_dongle_adapter()`** — parse hciN from modem path; query `org.bluez.Adapter1.Address` for `/org/bluez/<hciN>`; compare to known-good MAC. | No signature change, no constructor change. Adds a D-Bus call per bind — violates FR3. Not recommended. |

---

## Dependencies

| Dependency | Status | Notes |
|-----------|--------|-------|
| `adapter_check.py` (`list_adapters()`) | Available | Implemented in tincan-hchsf (closed). May be useful if A3 is chosen. |
| `_resolve_adapter_path()` in `__main__.py` | Available | Already used at startup; output flows to `TincanService.set_adapter_path()`. |
| `CallController.__init__` signature | Current | Approach A1 requires adding an `adapter_path` or `expected_hci` parameter. |
| oFono modem path format | Confirmed | `/hfp/org/bluez/hciN/dev_<remote-mac>` — verified 2026-06-23 on roglet. |

---

## Open Questions

| # | Question | Needed from |
|---|----------|-------------|
| OQ1 | Should `verify_dongle_adapter()` be promoted from a diagnostic to an actual gate on SCO routing, now that it can be correct? | Architect / Jim |
| OQ2 | Is `verify_usb_autosuspend_off()` in the same file using `_DONGLE_USB_VENDOR`/`_DONGLE_USB_PRODUCT` — should those constants be generalized to use the adapter selection config (i.e., look up USB IDs dynamically from `list_adapters()`)? | Architect |
| OQ3 | `TincanService` already holds `adapter_path` (set by `set_adapter_path()`). Should `CallController` receive it from `TincanService` at bind time rather than at construction? | Architect |
