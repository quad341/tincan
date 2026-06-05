# Release Gate: tincan-k942a (tincan-qfta7)

**Feature:** async MAP send off UI thread — fix 5s GUI freeze on enter-to-send  
**Bead:** tincan-qfta7 → source: tincan-52rxm  
**Branch:** feature/tincan-k942a  
**Commit:** 0c8402dae29ab545a45fce656797217b976a686d  
**Gate date:** 2026-06-05  
**Result:** FAIL

---

## Criteria

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | ✅ PASS | tincan-52rxm: "REVIEW VERDICT: PASS (all.reviewer, 2026-06-05)" |
| 2 | Acceptance criteria met | ✅ PASS | `_on_send` no longer calls blocking `send_message()`; uses `asyncCall+QDBusPendingCallWatcher`. Reviewer confirmed spec compliance. |
| 3 | Tests pass + lint | ❌ FAIL | See details below |
| 4 | No high-severity open findings | ✅ PASS | Review notes "Informational (non-blocking)" only — no blockers |
| 5 | Final branch is clean | ✅ PASS | `git status` clean, working tree empty |
| 6 | Branch diverges cleanly from main | ✅ PASS | 2 commits ahead of origin/main, no conflicts |
| 7 | Single feature theme | ✅ PASS | 3 files: `dbus_client.py` + `main.py` + new test file — strictly async send plumbing |

---

## Criterion 3 Detail

### Test run: `python -m pytest tests/ -q`

```
2 failed, 925 passed, 1 warning in 34.70s
FAILED tests/tincand/test_ancs_backend.py::TestActiveToHealing::test_health_check_fail_schedules_heal_timer
FAILED tests/tincand/test_ancs_backend.py::TestActiveToHealing::test_health_check_fail_clears_health_check_id
```

**ANCS failures: pre-existing.** These 2 tests pass when run in isolation (4/4 pass) — they fail due to test-ordering isolation from unrelated ANCS tests. Neither test touches any file changed by this commit. The commit only modifies `tincan_gui/` files; the failures are in `tests/tincand/`. Pre-existing on origin/main (confirmed). Not a regression from this commit.

### Ruff lint: `ruff check` on changed files

**NEW violations introduced by this commit in `tests/tincan_gui/test_send_async.py`:**

```
F401  line 15:38  `unittest.mock.call` imported but unused
E501  line 71     Line too long (100 > 99)
E501  line 102    Line too long (100 > 99)
E501  line 155    Line too long (102 > 99)
E501  line 183    Line too long (103 > 99)
E501  line 184    Line too long (104 > 99)
E501  line 198    Line too long (104 > 99)
```

**Pre-existing violations excluded** (confirmed on origin/main):  
`tincan_gui/main.py` — I001 (import sort), E501 lines 277 and 638. Not introduced by this commit.

**Summary:** 7 new ruff violations in the new test file. Gate FAIL on Criterion 3 (lint).

---

## Routing

Gate FAIL — technical implementation failure. Routed to builder (tincan/all.builder) for lint fix.

Required fixes in `tests/tincan_gui/test_send_async.py`:
1. Remove unused `call` import (line 15)
2. Shorten 6 lines exceeding 99 chars (lines 71, 102, 155, 183, 184, 198)
