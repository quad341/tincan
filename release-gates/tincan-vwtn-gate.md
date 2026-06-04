# Release Gate: tincan-vwtn — fix GUI send deadlock

**Bead:** tincan-vwtn (deploy bead)
**Feature:** fix(gui): replace deadlocking _SendWorker/QThread with inline Qt D-Bus send
**Source bead / review:** tincan-w8h8 (CLOSED, PASS)
**Spec bead:** tincan-gw29 (P0 bug)
**Commit evaluated:** 0cf9b94 (cherry-picked as ac3436d on tincan-vwtn off origin/main)
**Gate run:** 2026-06-04
**Verdict:** ✅ PASS

---

## Gate Checklist

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | ✅ PASS | tincan-w8h8 CLOSED with `REVIEW PASS — all.reviewer (2026-06-04)`; 0 HIGH findings |
| 2 | Acceptance criteria met | ✅ PASS | All deliverables from tincan-gw29 satisfied (see below) |
| 3 | Tests pass | ✅ PASS | 694/694 pass, 1 warning (full suite on tincan-vwtn branch off origin/main) |
| 4 | No HIGH findings open | ✅ PASS | 0 HIGH; 1 LOW/Coverage (untested error paths, acceptable), 1 INFO (D-Bus latency note) |
| 5 | Final branch clean | ✅ PASS | `git status` clean after gate commit |
| 6 | Branch diverges cleanly from main | ✅ PASS | Cherry-pick onto `origin/main` applied cleanly (auto-merge, no conflicts) |
| 7 | Single feature theme | ✅ PASS | Single P0 bug fix: remove QThread deadlock, inline main-thread send; 2 files, 1 subsystem |

---

## Criterion 2 — Acceptance Criteria

From tincan-gw29: GUI send delivers AND shows sent/failed status; remove `_SendWorker`/QThread deadlock; use `TincandClient.send_message()` on main thread; add failed bubble indicator; `QTimer.singleShot(0)` defers `_pending_sends` cleanup.

| AC | Status | Evidence |
|----|--------|---------|
| `_SendWorker`/QThread removed | ✅ PASS | No match for `_SendWorker` in `tincan_gui/main.py`; class deleted entirely |
| `TincandClient.send_message()` used inline | ✅ PASS | `main.py:534` — `message_id = self._dbus_client.send_message(phone, text)` |
| Error surfaced on empty reply | ✅ PASS | `main.py:541–542` — empty `message_id` triggers `self._thread_view.mark_last_send_failed()` |
| `MessageBubble.set_send_failed()` added | ✅ PASS | `thread_view.py:184` — `set_send_failed()` sets `⚠ Failed` label on outbound bubble |
| `ThreadView.mark_last_send_failed()` added | ✅ PASS | `thread_view.py:408` — calls `set_send_failed()` on `_last_outbound` |
| `QTimer.singleShot(0)` defers `_pending_sends` cleanup | ✅ PASS | `main.py:536` — `QTimer.singleShot(0, lambda: self._pending_sends.discard((phone, text)))` |

---

## Criterion 3 — Tests

```
python3 -m pytest tests/ --tb=short -q --ignore=tests/tincand/test_dbus_client_live.py

694 passed, 1 warning in 4.51s
```

Test count difference vs reviewer (749): origin/main has 694 tests; local dev main carries 55 additional tests added by subsequent commits not in this PR. All 694 tests on this branch pass.

**Ruff:** 3 pre-existing E501 violations on origin/main (main.py:58, bluez_map.py:537, pbap.py:160) — none introduced by 0cf9b94. The cherry-picked commit is ruff-clean.

---

## Criterion 4 — Review Findings

From tincan-w8h8 notes:

- **LOW/Coverage**: `set_send_failed()`, `mark_last_send_failed()`, `QTimer.singleShot(0)` echo-suppression path — no automated tests. GUI behavior requiring Qt event loop + D-Bus mock; genuinely hard to test deterministically. Acceptable per coverage rules; needs-tests follow-up filed.
- **INFO**: `send_message()` blocks main thread for D-Bus round-trip (<200ms). No action needed; noted for future if latency degrades.

0 HIGH findings → PASS.
