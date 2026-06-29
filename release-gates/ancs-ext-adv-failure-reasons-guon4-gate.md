# Release Gate: ANCS ext-adv failure reasons (tincan-guon4)

**Deploy bead:** tincan-kq2hl  
**Feature bead:** tincan-guon4  
**Branch:** feature/ancs-ext-adv-failure-reasons-guon4  
**Commit:** f91f632 (cherry-picked from 097dfc2)  
**Date:** 2026-06-29

## Gate Checklist

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-tjhi1 closed with reason=pass; reviewer verdict PASS from tincan/reviewer (reviewer-gm-xc4e4) on 2026-06-29 for commit 097dfc2 |
| 2 | Acceptance criteria met | **PASS** | See AC verification below |
| 3 | Tests pass | **PASS** | 2308 passed, 1 skipped, 9 xfailed (mcp pre-existing env issue). `python -m pytest tests/ --ignore=tests/tincand/test_mcp_server.py` |
| 4 | No high-severity findings open | **PASS** | Review found 2 LOW findings only (UPPER_CASE constant naming per spec; no dedicated unit tests for new dispatch branches). No HIGH findings. |
| 5 | Final branch is clean | **PASS** | `git status` clean, working tree has no uncommitted changes |
| 6 | Branch diverges cleanly from main | **PASS** | Cherry-pick of 097dfc2 onto origin/main applied with zero conflicts. Branch is 1 commit ahead of origin/main. |
| 7 | Single feature theme | **PASS** | One subsystem (ANCS advertisement error dispatch in `tincand/backends/ancs.py` + `tincand/pairing.py`). No unrelated surfaces touched. |

**Overall: PASS**

## Acceptance Criteria Verification

**AC1:** `FailureReason.ANCS_EXT_ADV_BUG = 'ANCS_EXT_ADV_BUG'` and `ANCS_EXPERIMENTAL_REQUIRED = 'ANCS_EXPERIMENTAL_REQUIRED'` added to `tincand/pairing.py`  
→ **VERIFIED** — both constants present at `tincand/pairing.py:34-35`

**AC2:** `_on_adv_error` dispatch:
- `'Invalid Parameters'` or `'0x0d'` in exc_str → `ANCS_EXT_ADV_BUG`
- `'NotSupported'` in exc_str → `ANCS_EXPERIMENTAL_REQUIRED`
- else → `ADVERTISING_FAILED`

→ **VERIFIED** — exact dispatch logic in `tincand/backends/ancs.py:368-395`. Failure reason stored in `self._adv_failure_reason` for upstream wizard use (tincan-aom60).

**AC3:** Existing ANCS tests pass  
→ **VERIFIED** — 2308 passed total; ANCS tests run under `tests/tincand/test_ancs_*.py` and `test_pairing_orchestrator.py` all pass.

**AC4:** No UI changes  
→ **VERIFIED** — diff touches only `tincand/backends/ancs.py` and `tincand/pairing.py`. No `tincan_gui/` changes.

## Cherry-pick note

Commit `097dfc2` was authored atop `builder/tincan-nbjrp` (whose nbjrp work landed via PR #154 and pyefu Calls UI via PR #157). Cherry-picked cleanly onto `origin/main` as `f91f632` with zero conflicts.
