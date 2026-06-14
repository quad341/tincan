# Release Gate — ancs-interfaces-added-3bpav

**Bead:** tincan-ctuyr (deploy bead) → source: tincan-y4kyu / tincan-3bpav  
**Branch:** feat/ancs-interfaces-added-3bpav  
**Commit:** 11ea52d8622bc34c5ba657663c9a24afc6935e06  
**PR:** #126  
**Date:** 2026-06-13  

## Gate Results

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | Reviewed + PASSED by tincan/reviewer — verdict in tincan-ctuyr notes |
| 2 | Acceptance criteria met | **PASS** | See breakdown below |
| 3 | Tests pass | **PASS** | 953 passed, 1 skipped, 6 xfailed — `pytest tests/tincand/` |
| 4 | No high-severity review findings | **PASS** | Reviewer: "No security issues" — zero HIGH findings |
| 5 | Final branch is clean | **PASS** | `git status` clean; at 11ea52d |
| 6 | Branch diverges cleanly from main | **PASS** | `merge-base --is-ancestor origin/main feat/ancs-interfaces-added-3bpav` ✓ |
| 7 | Single feature theme | **PASS** | One commit; one subsystem (`tincand/backends/ancs.py`) |

**Overall: PASS**

## Acceptance Criteria Verification

- [x] `_on_interfaces_added()` handler registered on BlueZ ObjectManager at `/` via `add_signal_receiver`
- [x] Guard: returns silently if `Device1` interface absent in `interfaces` dict
- [x] Guard: returns silently if `Connected ≠ True`
- [x] Uses `GLib.idle_add(_on_device_connected, ...)` per architectural guardrail (no direct call)
- [x] Double-subscribe protection via existing `_notif_src_path is not None` guard in `_on_device_connected`
- [x] `PropertiesChanged` receiver unchanged — normal reconnect path unaffected
- [x] Behavioral follow-on coverage filed as bead tincan-2s8fg for validator

## Code Change Summary

`tincand/backends/ancs.py` +15 lines:
- Signal receiver registration at `start()` for `InterfacesAdded` on `org.bluez ObjectManager`
- `_on_interfaces_added(object_path, interfaces)` handler with two early-return guards

## Note

Stray commit `ea24b32` (test(gui): ANCSStatusDot+ANCSRepairBanner widget tests, kzgk7.7) was present locally on this branch but NOT pushed to origin. Reset to origin tip before gating. SHA preserved as local orphan; mayor notified.
