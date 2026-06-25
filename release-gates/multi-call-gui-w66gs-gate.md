# Release Gate: multi-call-gui-w66gs

**Bead:** tincan-w66gs (deploy bead) / tincan-d7pih (review bead)
**Source beads:** tincan-w59ao (InCallPanel multi-call), tincan-o7yjg (IncomingCallDialog call-waiting)
**Branch:** fix/mac-fragment-guard-kf2h0
**Tip commit:** 6960383
**Date:** 2026-06-24

## Commits ahead of main

| SHA | Description |
|-----|-------------|
| 51a9bcf | fix(calls): guard empty mac_fragment in _is_hfp_iphone_modem + setup_sco_routing (tincan-kf2h0) |
| a9a022a | chore: release gate PASS for mac-fragment-guard-kf2h0 (tincan-8rsrv) |
| 987a2fe | fix(calls): CallController multi-call lifecycle — per-call teardown, audio scoping, held/waiting |
| df243b2 | feat(calls): dbus_service.py multi-call API — 4 new signals + GetCalls/SwapCalls/HoldAndAnswer/ReleaseAndAnswer |
| 61afa76 | feat(gui): InCallPanel multi-call extension — _CallRow, _MultiCallControls, idempotent state API |
| d4e9da4 | feat(gui): IncomingCallDialog Call Waiting mode + main.py multi-call wiring |
| 6960383 | fix(gui): address reviewer blockers — arity fix, PII, E402/I001, caller_name, _incall_dialog cleanup |

Note: commits 51a9bcf–a9a022a are the mac-fragment-guard fix (previously gate-passed as
tincan-8rsrv but not yet merged to main); commits 987a2fe–6960383 are the multi-call feature.
Both are calls-subsystem work sharing `tincand/call_controller.py`.

## Criteria

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-d7pih closed with reason "pass"; notes contain "## Reviewer verdict: PASS". First-pass reviewer confirmed all blockers resolved. |
| 2 | Acceptance criteria met | **PASS** | InCallPanel: _CallRow, _MultiCallControls, add_call/update_call_state/remove_call, H/R keyboard shortcuts, idempotent add_call — all present in call_panel.py. IncomingCallDialog: call-waiting mode with Hold&Answer/Release&Answer, active timer, caller_name from signal. TincandClient: get_calls/swap_calls/hold_and_answer/release_and_answer wired. Arity fix (9842950 cherry-pick) applied: on_call_waiting(call_id, number, name), on_call_active(call_id, number), on_call_held(call_id, number) all correct. PII remediation: CallActive/CallHeld/CallWaiting log only call_id. |
| 3 | Tests pass | **PASS** | `python -m pytest --tb=short -q` → 2005 passed, 2 skipped, 10 xfailed, 1 warning (40.25s). MCP collection error pre-existing; unrelated to branch. |
| 4 | No high-severity review findings open | **PASS** | tincan-d7pih: 0 HIGH, 0 BLOCKER findings remain. Two LOW non-blockers logged for follow-up: (1) X-button bypass on IncomingCallDialog (no reject() override); (2) direction param dead in add_call signature. |
| 5 | Final branch is clean | **PASS** | `git status` shows no staged or tracked-but-modified files; only untracked internal docs (docs/plans/multi-call-feature.md, worktrees/). |
| 6 | Branch diverges cleanly from main | **PASS** | `git merge-tree` reports no conflicts. Branch is 7 commits ahead of origin/main (276c801); no overlapping changes with main since #133 merge. |
| 7 | Single feature theme | **PASS** | All commits are in the calls subsystem. mac-fragment-guard fix and multi-call feature both touch `tincand/call_controller.py` and are not independently deployable without rebasing. Reviewer reviewed the full branch state at 6960383 and issued PASS. Deploy bead tincan-w66gs explicitly specifies this commit. |

## Lint / format

`ruff check` on branch-changed files (call_panel.py, dbus_client.py, main.py, call_audio.py,
call_controller.py, dbus_service.py, test_call_controller.py, test_dbus_contract.py):

- Two E501 (line-too-long) violations found: test_dbus_contract.py:80 and main.py:939.
  Both are pre-existing on origin/main (confirmed via `git show origin/main:<file>`), not
  introduced by this branch.
- E402/I001 violations that were introduced by this branch: FIXED (confirmed by reviewer
  in tincan-d7pih notes).
- `black` not installed in this environment; ruff clean on branch-changed files.

## Gate verdict: PASS

## Non-blocking follow-up items

- tincan: override `IncomingCallDialog.reject()` to emit `declined` before `super().reject()`
  to close X-button bypass (LOW, noted by reviewer)
- tincan: drop or wire `direction` param in `add_call` (LOW, noted by reviewer)
