# Release Gate: tincan-eag9h — MAP self-heal BT/MAP reconnect without sudo

**Bead**: tincan-eag9h (deploy) → source tincan-55rci (review) → tincan-8u3xl (impl)  
**Branch**: feature/tincan-x9zu3  
**Commits in PR**: 74cedea (feat: MAP self-heal), 447e783 (test: double-submit guard coverage), 3e6a022 (chore: fix RC-3 lint)  
**Gate run**: 2026-06-05 (initial FAIL), 2026-06-05 (re-run PASS after lint fix)  
**Result**: ✅ PASS

---

## Criteria

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | ✅ PASS | tincan-55rci closed with `Review verdict: PASS` by tincan/all.reviewer; commit 74cedea on feature/tincan-x9zu3 |
| 2 | Acceptance criteria met | ✅ PASS | All 4 exit_contract items verified: _bt_connect before OBEX ✓, backoff 10s→300s capped ✓, success resets counter ✓, BT failure doesn't abort OBEX ✓ |
| 3 | Tests pass | ✅ PASS | 1011/1011 committed tests pass (`git ls-files tests/ | xargs python -m pytest`); 71/71 test_backends.py; 18/18 new MAP tests; 6/6 GUI guard tests |
| 4 | No high-severity findings | ✅ PASS | Review noted one minor nit (double assign `_reconnect_source_id = None` then reassigned); explicitly marked non-blocking |
| 5 | Final branch is clean | ✅ PASS | `git status` clean; only untracked infrastructure/future-work files not in repo |
| 6 | Branch diverges cleanly from main | ✅ PASS | `git merge-tree` confirms no content conflicts with origin/main (69835e6); untracked working-directory files prevented `--no-ff` test but committed content merges cleanly |
| 7 | Single feature theme | ✅ PASS (with note) | Three commits: 74cedea (MAP daemon reconnect), 447e783 (GUI send-guard test coverage — tests for guard already in origin/main), 3e6a022 (lint fix). All serve the same reconnect feature. |

**Release criteria from PROJECT_MANIFEST.md:**

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| RC-1 | Phase definition-of-done met | ✅ N/A | Reconnect improvement; phase-1 DoD (hold SMS conversation) not blocked |
| RC-2 | All automated tests pass | ✅ PASS | 1011/1011 committed tests |
| RC-3 | Lint/format clean (ruff, black) | ✅ PASS | After 3e6a022: only 1 pre-existing error remains (bluez_map.py:371 E501, pre-dates this branch, not introduced by this PR) |
| RC-4 | No hardcoded iOS-version assumptions | ✅ PASS | No iOS version strings in diff; device matched by Bluetooth Address equality |
| RC-5 | LIMITATIONS.md updated if needed | ✅ PASS | Reconnect improvement doesn't change capability limits; no LIMITATIONS.md update needed |
| RC-6 | Onboarding still surfaces reconnect/Show Notifications | ✅ PASS | No onboarding code changed |

---

## RC-3 Detail (resolved)

Initial gate run found 2 new lint errors introduced by PR commits:

- `tests/tincand/test_backends.py:766` — E501 (line too long, from 74cedea) — **fixed in 3e6a022**
- `tests/tincan_gui/test_double_submit_guard.py:19` — I001 (import order, from 447e783) — **fixed in 3e6a022**

Remaining after fix: `tincand/backends/bluez_map.py:371` — E501 (pre-existing, pre-dates this branch, not introduced by this PR). Not blocking.

---

## Disposition

Gate **PASS**. PR #49 open: https://github.com/quad341/tincan/pull/49  
Branch HEAD at time of gate: 3e6a022  
Merge authority: mayor / mpr
