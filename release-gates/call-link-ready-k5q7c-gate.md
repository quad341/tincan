# Release Gate: call_link_ready wired into dial/call button state (reconciled)

**Deploy bead:** tincan-k5q7c
**Source beads:** tincan-bhij3 (design) → tincan-uuia9 (impl) → tincan-wcqn2 (orig review) → tincan-k5q7c (deploy, first pass FAILed) → this reconciliation → tincan-wcjy5 (re-review)
**Branch:** `builder/tincan-k5q7c-call-link-ready`
**Reviewed/tip commit:** `be2ffba` (parent `fec9dae`, parent `origin/main` tip `7f34ad6`)
**Base:** origin/main @ `7f34ad6`
**Merge-base:** `7f34ad6` (== origin/main tip — branch is a clean 2-commit fast-forward extension, 0 behind)
**Gate date:** 2026-07-13
**Prior attempt:** [`release-gates/call-link-ready-uuia9-gate.md`](call-link-ready-uuia9-gate.md) — FAILed on criteria 6/7 (stale merge-base, 27 commits behind origin/main, real conflicts in 7 files). This gate re-evaluates the reconciled branch built fresh off current `origin/main`.

## Gate Result: PASS

All 7 criteria pass. The reconciliation the prior FAIL recommended was carried out exactly as specified: the reviewed tip was cherry-picked onto a fresh branch off current `origin/main`, hand-reconciled against main's current group-conversation code shape, the stale ANCS commit was left behind entirely, and a coverage gap caught in re-review was fixed before this gate ran.

---

## Criteria

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-wcjy5 CLOSED, close reason "pass". Verdict trail: first pass REQUEST-CHANGES (one blocking item — coverage gap), builder fix applied, re-review verdict **PASS** with "No further blockers." |
| 2 | Acceptance criteria met | **PASS** | All 7 original ACs (tincan-uuia9) + 6 reconciliation ACs (tincan-wcjy5) independently spot-checked against `be2ffba` by direct grep/read, not just trusting the review: `_call_link_ready` default-False init (main.py:688), read from caps in `_apply_capabilities` before `_sync_call_state()` (main.py:1071), 3-way gate branches in both dial button and `ThreadHeader.set_call_button` (main.py:980,1003), disconnect reset (main.py:1343), `setAccessibleDescription` pairing on both widgets (main.py + thread_view.py:504), no new banner (`git diff` shows zero new banner logic, only a pre-existing context line and a comment). |
| 3 | Tests pass | **PASS** | Full suite independently re-run at `be2ffba` (own checkout, not trusting reported numbers): **2478 passed, 1 skipped, 0 failed**, exact match to both builder's and reviewer's independently-reported numbers. The 1 skip (`test_dbus_contract.py:261`, unknown D-Bus arg count) is pre-existing/unrelated — touches zero files in this diff. New test file re-run standalone: **15/15 passed**. |
| 4 | No high-severity findings open | **PASS** | The sole BLOCKING item from the first review pass (missing regression coverage for the new gating logic) was resolved by cherry-picking `tests/tincan_gui/test_call_link_ready.py` (commit `be2ffba`) and confirmed fixed in re-review. 0 HIGH/blocking findings remain open. |
| 5 | Final branch is clean | **PASS** | `git status` at `be2ffba`: working tree clean (only pre-existing untracked rig scaffolding `.gc/`, `.gitkeep`, unrelated to this repo's tracked content). |
| 6 | Branch diverges cleanly from main | **PASS** | `git merge-base builder/tincan-k5q7c-call-link-ready origin/main` == `origin/main` tip exactly (`7f34ad6`) — the branch is 0 commits behind, 2 ahead (a clean fast-forward extension, not a merge). `git merge-tree origin/main builder/tincan-k5q7c-call-link-ready` exits 0 with no conflict markers. This is the criterion that FAILed the prior attempt; the reconciliation fixes it structurally, not just re-tests it. |
| 7 | Single feature theme | **PASS** | `git diff --stat origin/main..HEAD`: 4 files, +231/-7 — `tincan_gui/main.py`, `tincan_gui/thread_view.py`, `tests/tincan_gui/test_calls_ui_w79ze.py` (1-line precondition update), `tests/tincan_gui/test_call_link_ready.py` (197-line new test file). All four are the single calls-UI gating feature; no unrelated commits are carried (the branch's merge-base equals `origin/main` tip, so the stale ANCS commit `097dfc2` and other prior-branch noise are structurally absent — confirmed by `git log origin/main..HEAD` showing exactly `fec9dae` + `be2ffba`). |

---

## Criterion 6 Detail — Resolution of the Prior FAIL

The prior gate FAILed because the original branch's merge-base was 27 commits behind `origin/main` and carried 9 unrelated commits, 2 of which collided directly with content `origin/main` had independently gained in the interim (a duplicate ANCS `FailureReason` addition with different string values, and `main.py`/`thread_view.py` group-conversation plumbing that the stale branch's differently-shaped version collided with inside the same functions).

The reconciliation did exactly what the prior gate recommended: cherry-picked only the reviewed tip (`d7b2fe6c`) onto a fresh branch cut from current `origin/main`, hand-resolved the `call_link_ready` insertion against main's current `_sync_call_state`/`_apply_capabilities` shape, left `_current_is_group`/`set_group_mode` untouched, and excluded the stale ANCS commit entirely. Independently confirmed here via `git merge-tree` (clean, exit 0) and via `git log origin/main..HEAD` (exactly 2 commits, both germane to this feature).

## Test Coverage Note

The re-review caught a real gap that the original review missed: at initial reconciliation (`fec9dae`), the dedicated regression tests for this exact gating logic (`tests/tincan_gui/test_call_link_ready.py`, originally authored under tincan-piiml) had not been carried forward from the superseded branch. Since tincan-piiml showed as closed in `bd`, this would have shipped as a silent coverage gap with no tracking mechanism left to catch it. The reviewer caught it, required the cherry-pick before approving, and the fix was verified content-identical to the original (only a docstring rewrap for line length) both by the reviewer and independently here.

---

## Project Manifest Release Criteria

| # | Criterion | Result | Notes |
|---|-----------|--------|-------|
| 1 | Phase definition-of-done | N/A | Incremental UX gating fix, not the Phase 1 E2E milestone |
| 2 | All tests pass | PASS | 2478 passed, 1 skipped (pre-existing/unrelated), 0 failed — independently re-run at `be2ffba` |
| 3 | Lint/format clean | PASS | `ruff check` on all 4 changed files: clean. Repo-wide `ruff check .`: 4 pre-existing findings, all in `docs/mgmt_ext_adv.py`, confirmed untouched by this branch (`git diff origin/main -- docs/mgmt_ext_adv.py` is empty) |
| 4 | No hardcoded iOS/iPhone-model assumptions | PASS | None in the diff — pure GUI state-gating logic on an existing daemon-exposed capability flag |
| 5 | LIMITATIONS.md updated | N/A | No platform-capability change, only GUI gating on an existing daemon-exposed flag |
| 6 | Onboarding requirements surfaced | PASS | Onboarding paths untouched by the diff |
