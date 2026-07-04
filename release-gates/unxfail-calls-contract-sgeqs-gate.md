# Release Gate: un-xfail 9 stale im.tincan.Calls contract tests

**Bead:** tincan-sgeqs (deploy) · source: tincan-73eki (build) · review: tincan-snlvq
**Branch:** `fix/tincan-73eki-unxfail-calls-contract`
**Gate commit (pre-gate tip):** aba051a7a530632ab149fce0510c7d08028974a8
**Date:** 2026-07-03

## Gate Checklist

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-snlvq reviewer verdict PASS (tincan/reviewer, 2026-07-03); independent scope/claim/test verification documented in review notes |
| 2 | Acceptance criteria met | **PASS** | tincan-73eki acceptance: "no xfails remain (unless genuinely pending, using strict xfail)" + "full suite green" — both verified directly, see below |
| 3 | Tests pass | **PASS** | Re-ran myself on `aba051a`: `tests/tincand/test_dbus_contract.py` 77 passed, 1 skipped, 0 xfailed; full suite `tests/` 2376 passed, 1 skipped, 0 failed, 0 xfailed (102s) |
| 4 | No high-severity review findings open | **PASS** | Review notes: "No blockers." One P4 non-blocking incidental finding filed separately as tincan-ym09d (unrelated file, not a blocker) |
| 5 | Final branch is clean | **PASS** | `git status` clean at `aba051a` (only pre-existing worktree scaffolding `.gc/`, `.gitkeep`, not part of this diff) |
| 6 | Branch diverges cleanly from main | **PASS** | `git merge-base --is-ancestor origin/main HEAD` true — `origin/main` (399b500) is a direct ancestor; branch is exactly 1 commit ahead (clean fast-forward, zero conflict risk) |
| 7 | Single feature theme | **PASS** | Single file (`tests/tincand/test_dbus_contract.py`), single logical change: remove a stale pending-iface entry + convert the guard to a strict, self-healing xfail. Test-infrastructure only, no app-logic surface |

**Verdict: PASS**

## Independent Verification Detail

- Scope: `git diff origin/main --stat` on `aba051a` → `tests/tincand/test_dbus_contract.py | 32 +++++++++++++------------` (16 insertions, 16 deletions), matches the reviewer's and builder's claimed scope exactly.
- Core claim: `grep` of `tincand/dbus_service.py:803-838` confirms all 9 `im.tincan.Calls` signals (IncomingCall, CallConnected, CallEnded, AudioError, AudioRestored, CallWaiting, CallHeld, CallActive, CallRemoved) are unconditionally exported.
- Test run (targeted): `PYTHONPATH=. pytest tests/tincand/test_dbus_contract.py -q` → `77 passed, 1 skipped, 1 warning`.
- Test run (full suite): `PYTHONPATH=. pytest tests/ -q` → `2376 passed, 1 skipped, 1 warning in 102.06s`. Matches builder's reported 2376/1/0 exactly (this environment has the `mcp` package installed, so unlike the reviewer's sandbox, `test_mcp_server.py` collected and ran here too — no gap).
- Lint: `ruff check .` → 77 errors both on `aba051a` and on `origin/main` (identical count; the diff introduces zero new lint issues). `black` is not installed in this environment (pre-existing gap, not introduced by this change; ruff is the enforced linter for this repo per prior deploys).
- Divergence: `origin/main` is a direct git ancestor of `aba051a` (1 commit ahead) — no merge-tree check needed, structurally cannot conflict.

## Duplicate bead note

`tincan-2wo73` is a second `needs-deploy` bead auto-created for this exact same commit/branch/review (identical `aba051a`, identical `fix/tincan-73eki-unxfail-calls-contract`, same source review `tincan-snlvq`) — a duplicate dispatch, not a distinct change. This gate and its PR are the deploy of record; `tincan-2wo73` is being closed as a duplicate referencing this bead/PR to prevent a second PR being opened for the same commit.

## Commit History

| SHA | Message |
|-----|---------|
| aba051a | fix(tests): un-xfail 9 stale im.tincan.Calls contract tests, make pending-iface guard strict (tincan-73eki) |
