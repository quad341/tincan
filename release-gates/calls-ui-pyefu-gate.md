# Release Gate: calls-ui-pyefu (tincan-ir3nt)

**Bead:** tincan-ir3nt  
**Source bead:** tincan-pyefu  
**Review bead:** tincan-wfw5t  
**Branch:** builder/tincan-pyefu @ 6945de9 (origin)  
**Gate evaluated:** 2026-06-29 (deployer tincan-ir3nt)

## Verdict: PASS

All 7 criteria pass. Validator tests cherry-picked from tincan-w79ze (48e8d3f) and included. Lint fix (isort) applied to test file. 1141 tests passed on assembled branch.

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-wfw5t closed (PASS). Two independent reviewer verdicts: tincan/reviewer + reviewer-gm-fbujk. AC1–AC8 all confirmed. |
| 2 | Acceptance criteria met | **PASS** | AC1–AC8 verified in tincan-wfw5t: DialpadDialog 360×560, TitleBar Dial teal/grey per call_setup_ready, ThreadHeader Call hidden on group, Call gated on ≥4 digits, dial()→_enter_call() with inline error, Return/Enter fires Call, Backspace works, OQ4 raw number passed to _enter_call(). |
| 3 | Tests pass | **PASS** | 1141 passed, 1 warning (pre-existing GLib deprecation unrelated to this feature). Includes 14 new behavioral tests from tincan-w79ze covering all 4 spec scenarios. Ruff lint clean on all changed files. |
| 4 | No high-severity review findings | **PASS** | No HIGH findings. Only LOW/non-blocking: N1 (defense-in-depth: _on_thread_call missing call_setup_ready guard, button disabled by _sync_call_state so unreachable by normal interaction), N2 (style: self.sender() called twice in _on_dialpad_call, low priority). |
| 5 | Final branch is clean | **PASS** | `git status` clean on 6945de9. No conflict markers. |
| 6 | Branch diverges cleanly from main | **PASS** | `git merge-tree --write-tree origin/main HEAD` exits 0 (SHA 9181a2d). |
| 7 | Single feature theme | **PASS** | Outbound call UI: DialpadDialog, TitleBar Dial button, ThreadHeader Call button, _sync_call_state — one coherent Calls UI feature. Files: tincan_gui/main.py, tincan_gui/thread_view.py, tests/tincan_gui/test_calls_ui_w79ze.py. |

## Branch diff summary (vs origin/main)

- `tincan_gui/main.py`: `DialpadDialog` class (360×560, 12-key grid, editable number field, backspace, Call/Cancel, inline error, Return-key wiring); TitleBar `_dial_btn` (teal/grey per `_call_setup_ready`); `_sync_call_state()`; `_open_dialpad()`; `_on_dialpad_call()`; `_on_thread_call()`; `DialpadDialog` wired into conversation selection, capability changes, connect/disconnect
- `tincan_gui/thread_view.py`: ThreadHeader `_call_btn` (hidden on group threads, visible on 1:1)
- `tests/tincan_gui/test_calls_ui_w79ze.py`: 14 behavioral pytest-qt tests covering all 4 design-spec scenarios (cherry-picked from tincan-w79ze @ 48e8d3f, lint fixed)
