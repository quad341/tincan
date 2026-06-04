# Release Gate: tincan-zyje — MAP GetMessage failed-handle backoff cache (tincan-ixqg)

Evaluated: 2026-06-04
Commit: d2cdad202cfc5e9bae406106387d4c105ae7c3c4 (on main)
Deploy bead: tincan-zyje
Source bead: tincan-ixqg

---

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-s6x0: "REVIEWER VERDICT: PASS" + "Verdict: PASS — fix is minimal, surgical, and fully tested." 0 blockers. |
| 2 | Acceptance criteria met | **PASS** | AC: "fails at most once per handle; steady-state log quiet." `_failed_handles` set added; warns once on first `DBusException`, skips silently thereafter. `_failed_handles.clear()` in `connect()` for session-reconnect clean slate. |
| 3 | Tests pass | **PASS** | `python -m pytest tests/ -q`: 749/749 passed on d2cdad2. |
| 4 | No high-severity findings open | **PASS** | 0 blockers; 1 informational (non-blocking): `disconnect()` does not clear `_failed_handles`, harmless due to `_msg_access is None` guard at reconnect. |
| 5 | Final branch clean | **PASS** | `git status` on main: no uncommitted changes. |
| 6 | Branch diverges cleanly from main | **PASS** | Commit is on main HEAD. No divergence. |
| 7 | Single feature theme | **PASS** | Surgical: 2 files (`tincand/backends/bluez_map.py` +5 lines; `tests/tincand/test_bluez_map.py` +96 lines). One subsystem, one fix. |

**Overall: PASS**

## Changed files

- `tincand/backends/bluez_map.py`: +`_failed_handles: set[str]` in `__init__`, clear in `connect()`, early-return in `_fetch_full_body` if path already failed, add to set on `DBusException`.
- `tests/tincand/test_bluez_map.py`: 8 new §13 `TestMapBackendFailedHandleBackoff` tests covering inject+tick, no real timing.

## Ruff

`ruff check tincand/ tincan_gui/` — All checks passed.
