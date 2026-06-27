# Release Gate: adapter_warning + device_discovered in GetStatus() (tincan-5y8km.1)

**Bead:** tincan-zylxy (deploy) → tincan-5y8km.1 (build) → tincan-axhtf (review)
**Branch:** feat/adapter-warning-5y8km.1
**Commit:** 49dba44
**Date:** 2026-06-27
**Deployer:** deployer-gm-wisp-4wppd64

---

## Gate Checklist

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-axhtf: PASS verdict from reviewer-gm-wisp-6qenkfq — all 6 AC met |
| 2 | Acceptance criteria met | **PASS** | See AC table below |
| 3 | Tests pass | **PASS** | 2104 passed, 2 skipped, 10 xfailed — matches builder report |
| 4 | No high-severity findings open | **PASS** | One low-severity note: `hasattr` guard on `set_adapter_warning` is dead code (harmless) |
| 5 | Final branch is clean | **PASS** | Committed state (49dba44) is up to date with origin; git status clean on committed HEAD |
| 6 | Branch diverges cleanly from main | **PASS** | 1 commit ahead of origin/main, no conflicts |
| 7 | Single feature theme | **PASS** | Focused: adds `adapter_warning` + `device_discovered` to `TincanService.GetStatus()` and wires `CallController` to set/clear the warning |

**Overall: PASS**

---

## Acceptance Criteria Verification

| AC | Criterion | Status |
|----|-----------|--------|
| 1 | `TincanService.__init__` gains `self._adapter_warning = ""` and `set_adapter_warning(text: str)` method | ✓ `dbus_service.py:113-115`, `:281-290` |
| 2 | `GetStatus()` returns `adapter_warning` (str) and `device_discovered` (bool) | ✓ `dbus_service.py:193-200` |
| 3 | `CallController._bind_modem()` and `_on_modem_online()` call `set_adapter_warning()` when `verify_dongle_adapter()` returns False | ✓ `call_controller.py:258-279` |
| 4 | Warning cleared (`set_adapter_warning("")`) when adapter is correct | ✓ `call_controller.py:272` |
| 5 | Warning text format: names current adapter (hci + human name), why wrong (no SCO), correct adapter (alias + hci), action | ✓ confirmed by reviewer |
| 6 | `GetStatus()` returns `device_discovered: bool`, defaults to False | ✓ `dbus_service.py:113,200` |

---

## Test Run

```
2104 passed, 2 skipped, 10 xfailed, 1 warning in 41.43s
```

Run on committed state 49dba44 (local WIP stashed before run).

---

## Diff Surface

```
tincand/call_controller.py | 20 +++++++++++++++++++-
tincand/dbus_service.py    | 28 +++++++++++++++++++++++++++-
2 files changed, 46 insertions(+), 2 deletions(-)
```

Two files, one feature theme. `tincan_gui/dbus_client.py` not in this commit — GUI banner is in tincan-5y8km.2 (separate bead, already closed).

---

## Notes

- Follow-up needs-tests bead tincan-b0r2n filed (GetStatus defaults, set/clear cycle, _bind_modem paths).
- `device_discovered` stays False until tincan-ddnwh.1 (device auto-discovery) lands.
