# Release Gate: tincan-99b0 — device_name GUI wiring

**Bead:** tincan-99b0
**Feature:** Surface device_name in title bar instead of MAC address (tincan-m9u9 F1 fix)
**Review bead:** tincan-0mji (CLOSED, PASS)
**Commit evaluated:** 67a2391 (and subsequent fixes through 0db2c06 on main)
**Gate run (run-2):** 2026-06-03
**Verdict:** ✅ PASS

---

## Gate Checklist

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | ✅ PASS | tincan-0mji CLOSED, REVIEWER VERDICT: PASS |
| 2 | Acceptance criteria met | ✅ PASS | device_name wired in _sync_daemon_state + _on_daemon_connected, fallback to device_address |
| 3 | Tests pass | ✅ PASS | 523 pass, 3 fail (TestHealingToActive pre-existing) — see run-1 failure resolution below |
| 4 | No HIGH findings open | ✅ PASS | 0 HIGH findings. tincan-44wr (needs-tests, non-blocking) filed. |
| 5 | Final branch is clean | ✅ PASS | git status clean |
| 6 | Branch diverges cleanly | N/A | Local-only repo; commits are on main |
| 7 | Single feature theme | ✅ PASS | GUI-only change |

---

## Run-1 failure resolution

Run-1 failed on `TestStart::test_registers_application_exactly_once`.
That test was updated by the validator before run-2: it now asserts GattManager1 is NOT
called (correct for the SolicitUUIDs consumer architecture from eef1495). All 5 TestStart
tests pass in run-2.

The 3 TestHealingToActive failures are pre-existing (documented in tincan-dar4 baseline;
present on f4e7a85 before any of the commits in this deploy window).

**Command:** `python -m pytest tests/ --ignore=tests/tincand/test_dbus_client_live.py -q`
**Result:** 523 passed, 3 failed (TestHealingToActive pre-existing)

---

## Disposition

Gate PASS — all criteria met. All commits on main (local-only repo — no PR needed).
Mailing mayor for merge approval.
