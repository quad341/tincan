# Release Gate: multi-call-dbus-api-o9klv

**Bead:** tincan-mfwne (deploy bead) / tincan-o9klv (source bead)
**Branch:** feat/multi-call-dbus-api-o9klv
**Commit:** 9842950
**Date:** 2026-06-24

## Criteria

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-do9dc closed with reason "pass"; notes contain two independent "Reviewer verdict: PASS" from tincan/reviewer |
| 2 | Acceptance criteria met | **PASS** | Callback arity fixed: `on_call_active(call_id, cs.number)`, `on_call_held(call_id, cs.number)`, `on_call_waiting(call_id, number, caller_name)` — all 3 callers now match dbus_service.py signatures; `CallWaiting` signal param renamed `direction→name`; phone numbers removed from `CallActive`/`CallHeld`/`CallWaiting` INFO logs; `GetCalls`/`SwapCalls`/`HoldAndAnswer`/`ReleaseAndAnswer` D-Bus methods present |
| 3 | Tests pass | **PASS** | `pytest tests/ -x -q` → 2001 passed, 2 skipped, 10 xfailed, 0 failures (36.08s) |
| 4 | No high-severity review findings open | **PASS** | Reviewer noted one LOW non-blocking finding: no new arity-assertion tests (a needs-tests bead should follow). No HIGH findings. |
| 5 | Final branch is clean | **PASS** | `git status` shows no staged or tracked-but-modified files; only untracked agent-workspace files |
| 6 | Branch diverges cleanly from main | **PASS** | `git merge-base origin/main HEAD` = `276c801ec309eb45504f11110a5d597699c63f96`, which is the current tip of `origin/main` (0 commits behind) — no merge conflicts possible |
| 7 | Single feature theme | **PASS** | All 5 commits are part of the HFP multi-call feature chain: `mac_fragment` guard (prerequisite safety fix) → multi-call lifecycle in `call_controller.py` → multi-call D-Bus API in `dbus_service.py` → callback arity fix. These are not independent: removing the mac_fragment guard or the lifecycle commits would break the D-Bus API. Commits 51a9bcf/a9a022a/987a2fe are also in open PR #138 (`fix/mac-fragment-guard-kf2h0`); mayor should coordinate merge order. |

## Gate verdict: PASS

## Notes

This branch (`feat/multi-call-dbus-api-o9klv`) is built on top of `fix/mac-fragment-guard-kf2h0`
(PR #138). Commits `51a9bcf`, `a9a022a`, and `987a2fe` appear in both branches. If PR #138
merges first, this PR will automatically narrow to show only the 2 new commits (`df243b2`,
`9842950`) against the new main tip. Merge order is at the mayor's discretion — both routes
(merge #138 first, or merge this PR directly) are safe; the arity fix in 9842950 is needed
before the multi-call signals work correctly at runtime.

**LOW finding (non-blocking):** No new arity-verification tests. A follow-up needs-tests bead
should add assertions that `on_call_active`/`on_call_held`/`on_call_waiting` are called with
the correct argument count.
