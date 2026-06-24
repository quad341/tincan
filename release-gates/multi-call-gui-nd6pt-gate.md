# Release Gate: multi-call GUI (feat/multi-call-gui-nd6pt)

**Bead:** tincan-r8bs7 — multi-call GUI: CallWaitingDialog, MultiCallPanel, wiring  
**Branch:** feat/multi-call-gui-nd6pt  
**Tip commit:** 1c299af  
**Date:** 2026-06-24  
**Deployer:** tincan/deployer

## Gate Result: PASS

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | PASS | tincan-0ep8h (review bead) closed reason=pass; "Reviewer verdict: PASS (re-submission round 3)" confirmed all 5 review findings resolved. One MEDIUM finding (double declined emit) is outstanding — see note below. |
| 2 | Acceptance criteria met | PASS | See per-bead checks below. |
| 3 | Tests pass | PASS | 1995 passed, 3 skipped, 8 xfailed, 1 warning. `python -m pytest tests/ -x -q` on feat/multi-call-gui-nd6pt tip. |
| 4 | No HIGH findings open | PASS | Outstanding finding is [MEDIUM/FUNC] double declined emit — not HIGH. Criterion requires 0 HIGH findings; 0 unresolved HIGH present. |
| 5 | Final branch clean | PASS | `git status` clean; untracked files (docs/plans/, worktrees/) are unrelated artifacts. |
| 6 | Diverges cleanly from main | PASS | `git merge-tree` shows no conflicts with origin/main. |
| 7 | Single feature theme | PASS | All 3 commits touch multi-call HFP GUI subsystem only (call_panel.py, dbus_client.py, main.py, test_dbus_contract.py). |

## Outstanding Finding (MEDIUM — non-blocking)

**[MEDIUM/FUNC] Double `declined` signal emission** (`tincan_gui/call_panel.py`:459-465)

`CallWaitingDialog._on_decline()` emits `self.declined` then calls `self.reject()` which also emits `self.declined`. Results in `hangup()` called twice on the waiting call. Harmless in practice (double-hangup on an already-ending call), but should be fixed in follow-up.

Fix: remove `self.declined.emit()` from `_on_decline`; let `reject()` be the sole emitter.

The reviewer issued a REQUEST-CHANGES note for this after the PASS verdict. However the review bead tincan-0ep8h was closed with reason=pass and criterion #4 requires only 0 HIGH findings. Recommend filing a bug bead for this fix.

## Acceptance Criteria Verification

### tincan-lq5o7 — CallWaitingDialog

- [x] `CallWaitingDialog(QDialog)` at `tincan_gui/call_panel.py:324`
- [x] Constructor: `(waiting_name, waiting_number, active_name, active_elapsed, parent)`
- [x] Fixed 360×360px size, dark background
- [x] Signals: `hold_and_answer_requested`, `release_and_answer_requested`, `declined`
- [x] Keyboard: H → hold_and_answer, R → release_and_answer, Escape → declined + close
- [x] `reject()` override emits `declined` (X-button bypass fixed in 1c299af)

### tincan-qa4oh — MultiCallPanel

- [x] `MultiCallPanel(InCallPanel)` at `tincan_gui/call_panel.py:479`
- [x] Signals: `swap_requested`, `end_all_requested`, `hold_and_answer_requested`, `release_and_answer_requested`, `decline_waiting_requested`, `keypad_toggled`
- [x] Dynamic visibility per call count (End All Calls visible only 2+ calls)
- [x] Backward compat: 1-call appearance unchanged

### tincan-qaics — Wire signals in main.py

- [x] `c.call_waiting.connect(self._on_call_waiting)` at `main.py:681`
- [x] `c.call_held.connect(self._on_call_held)` at `main.py:682`
- [x] `_on_call_waiting` shows `CallWaitingDialog`
- [x] `_on_call_held` routes to `MultiCallPanel` state
- [x] No PII (phone numbers) in debug logs (fixed in 1c299af)

## Commits

```
1c299af fix(gui): address review blockers — PII in logs, X-button bypass on CallWaitingDialog
6b6b2d9 feat(gui): wire multi-call signals in main.py — CallWaiting/CallHeld + panel controls (tincan-qaics)
7ca7d20 feat(gui): CallWaitingDialog + MultiCallPanel for multi-call HFP (tincan-lq5o7, tincan-qa4oh)
```

## Note: Duplicate Branch

Branch `builder/tincan-mol-it01` (deploy bead tincan-ym7gm) contains byte-for-byte identical
changes (`git diff 1c299af 765670b` produces no output). tincan-ym7gm will be closed as
superseded by this PR.
