# Release Gate: get_adapters() + adapter_path_requested in dbus_client (tincan-6m971)

**Bead:** tincan-6m971  
**Feature bead:** tincan-0fq30 (get_adapters() and adapter_path_requested in dbus_client)  
**Review bead:** tincan-09xw7  
**Commit:** `7d3af42`  
**Branch:** `fix/call-setup-ready-z0qqo`  
**Date:** 2026-06-14

## Gate Criteria

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-09xw7 notes: "REVIEW VERDICT: PASS (partial feature — deploy hold pending GUI beads)" |
| 2 | Acceptance criteria met | **PASS** | 3/3 ACs verified by reviewer; see below |
| 3 | Tests pass | **PASS** | CI green at branch tip `f20fbcb` (2 consecutive successes 2026-06-14T22:18Z, 22:27Z); 1906 tests pass at branch tip |
| 4 | No high-severity findings | **PASS** | No HIGH findings in tincan-09xw7 review; lint issues all CI non-blocking |
| 5 | Final branch clean | **PASS** (with note) | `origin/fix/call-setup-ready-z0qqo` fully pushed and clean. Local working tree has unstaged `settings_dialog.py` modifications (builder in-progress work); these are NOT committed and NOT part of this deployment. |
| 6 | Branch diverges cleanly from main | **PASS** | `git merge-base --is-ancestor origin/main origin/fix/call-setup-ready-z0qqo` confirms linear ancestry, zero conflicts |
| 7 | Single feature theme | **PASS** | All branch commits relate to BT adapter detection, picker UI, and degraded-state banners — one coherent feature area |

## Acceptance Criteria Verification

**AC 1:** `get_adapters()` calls `GetAdapters()` via `_dbus_call` + Qt fallback pattern consistent with `list_conversations()`. Returns `[]` when bus disconnected or all D-Bus paths fail. Uses existing `_demarshal_list_of_maps` helper. **✅**

**AC 2:** `get_status()` `adapter_path_requested` field: `setdefault('adapter_path_requested', '')` applied in all three return paths (dbus-python, Qt `QDBusMessage`, Qt `_wrap_reply`). Field always present even when daemon is older version. **✅**

**AC 3:** No `SystemBus`: grep confirms zero `dbus.SystemBus()` calls in `tincan_gui/dbus_client.py`. Only mention is in docstring warning. **✅**

## Hold Condition Resolution

Deploy hold placed by reviewer: "do not open PR until CI is clean (23 test_adapter_picker.py failures)."

Resolution: `tincan-yn2x5` (BT adapter picker) was built and closed. CI now green at branch tip `f20fbcb` with all adapter picker tests passing.

## Verdict: **PASS**
