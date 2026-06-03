# Release Gate: tincan-9o8p

**Feature:** wire MapBackend↔TincanService — poll loop + SendMessage + GetMessage
**Bead:** tincan-9o8p (source: tincan-hf3f)
**Branch:** fix/poll-inbox-folder-nav-text-body
**Head commit:** 8e63712
**Gate run:** 2026-06-03
**Result:** FAIL

## Gate Checklist

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | PASS | tincan-jgr3 closed with `Review verdict: PASS`; reviewer all.reviewer; 0 HIGH findings (3x LOW advisory) |
| 2 | Acceptance criteria met | PASS | register_backend() wires SendMessage/GetMessage; MapBackend 30s GLib poll timer; 'map' backend in __main__; MockBackend connect-order fixed |
| 3 | Tests pass | **FAIL** | 531 pass, 4 fail — 3 pre-existing TestHealingToActive failures (on main), 1 NEW failure introduced by 8e63712 |
| 4 | No HIGH findings open | PASS | 0 HIGH findings; 3 advisory LOW (error message hardcode, stale help text, coverage gap) |
| 5 | Final branch clean | PASS | `git status` shows only untracked infra files (.beads/, .gc/, docs/designs/, etc.) |
| 6 | Branch diverges cleanly from main | PASS | Local repo; no remote. 3 commits ahead of main (fec136b, 5318412, 8e63712); cherry-picks cleanly |
| 7 | Single feature theme | PASS | Commit 8e63712 is a single coherent feature: wiring MapBackend↔TincanService |

## Criterion 3 Detail — Test Failure

### Pre-existing failures (on main before this branch)

```
FAILED tests/tincand/test_ancs_backend.py::TestHealingToActive::test_rearm_success_calls_set_capability_ancs_true
FAILED tests/tincand/test_ancs_backend.py::TestHealingToActive::test_rearm_success_clears_heal_timer_id
FAILED tests/tincand/test_ancs_backend.py::TestHealingToActive::test_rearm_success_resets_ancs_needs_repair
```

Confirmed pre-existing on main (verified by running on main checkout: same 3 failures, 0 others).

### NEW failure introduced by 8e63712

```
FAILED tests/tincand/test_dbus_client_live.py::TestSignalReception::test_daemon_gui_receives_required_signals_and_updates_model
```

**Root cause:** `test_daemon_gui_receives_required_signals_and_updates_model` is a new test
introduced in `8e63712` (commit message: "Extend test_dbus_client_live.py: PySide6 availability
check + daemon+GUI signals test"). The test expects to receive the `connected` signal, but the
mock daemon emits `Connected` at startup (during `backend.connect()` in `main()`), which fires
~1.5 s into the daemon's lifecycle — before `MainWindow()` is created and the signal handler
is attached.

Failure output:
```
FAIL: missing signal(s): {'connected': False, 'message': True, 'capability': True, 'conversation': True}
```

`message`, `capability`, and `conversation` signals are received correctly; only `connected` is
missed because it already fired before the handler was registered.

**Fix needed:** The test must trigger a fresh `Connected` signal after attaching the handler.
Pattern: call `client.connect()` (or equivalent D-Bus method) after attaching, the same way
`test_connected_signal_received_within_5s` calls `Disconnect()` then `Connect()` to ensure a
fresh emission. Builder to fix in `tests/tincand/test_dbus_client_live.py`.

## Decision

Gate **FAIL** — Criterion 3. One new test introduced by the feature commit fails due to a
timing bug in the test itself. The feature code is correct; the test needs a one-line fix to
call `Connect()` after attaching the signal handler.

Route: back to builder (ready-to-build). No push, no PR opened.
