# Release Gate: tincan-pj9f4 — MainWindow call panel state machine (tincan-fx79v.2)

Evaluated: 2026-06-07
Commit: 2111828 (rebased tip of gc-builder-7bc6d8919b27, post-branch-surgery)
Deploy bead: tincan-pj9f4
Source bead: tincan-fx79v.2

---

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-23jgd closed with `close_reason: pass`. Reviewer mail: "Review PASS: MainWindow call panel (tincan-fx79v.2) — deploy bead tincan-pj9f4 ready." Original blocker (avatar.py:120 E501) fixed in 2111828; encapsulation concerns (LOW) resolved by exposing `InCallPanel.elapsed` property and `set_keypad_checked()`. |
| 2 | Acceptance criteria met | **PASS** | All 4 ACs from tincan-fx79v.2 verified: (a) `compose_stack` is `QStackedWidget`, page 0=ComposePanel, page 1+=InCallPanel (main.py:553-557, 1289-1312); (b) all state transitions present (`setCurrentIndex` for compose/incall/audio-err/dtmf pages); (c) `dlg.raise_()` + `dlg.activateWindow()` at main.py:1281-1282; (d) all 12 behavioral tests pass with no real D-Bus (pure mock stubs). Encapsulation: `InCallPanel.elapsed` (call_panel.py:218), `set_keypad_checked()` (call_panel.py:221); main.py uses only public API. |
| 3 | Tests pass | **PASS** | `python -m pytest tests/ -q`: **1615 passed, 6 skipped, 6 xfailed, 0 failures** (44.89s). 12 call_panel behavioral tests all pass. 6 xfails are expected: `im.tincan.Calls` signals pending daemon implementation (tincan-xohrx). |
| 4 | No high-severity findings open | **PASS** | Reviewer found 1 BLOCKER (lint, fixed in 2111828) + 1 LOW (encapsulation, fixed). 0 open HIGH/BLOCKER findings. |
| 5 | Final branch clean | **PASS** | `git status` clean — no uncommitted changes. Untracked: `.claude/`, `.codex/`, `.gc/`, `.gitkeep` (deployer worktree infrastructure, not part of the PR). |
| 6 | Branch diverges cleanly from main | **PASS** | `git merge-base` = `04f0020` (current `origin/main` tip). 5 commits above main, no merge conflicts. |
| 7 | Single feature theme | **PASS** | All 5 commits are the call panel feature: widget definitions (tincan-fx79v), behavioral tests (tincan-fx79v.4), HFP daemon signals (tincan-fx79v.3), MainWindow wiring (tincan-fx79v.2), lint fix (2111828). Tightly coupled — widgets, wiring, and daemon client cannot ship separately without broken imports or invisible UI. |

**Overall: PASS**

## Changed files

- `tincan_gui/avatar.py`: lint fix — break `__init__` signature to fix E501 (reviewer blocker).
- `tincan_gui/call_panel.py`: new file — `IncomingCallDialog`, `InCallPanel`, `DTMFKeypad`, `AudioErrorPanel` widgets. Exposes `elapsed` property and `set_keypad_checked()` for clean `MainWindow` integration.
- `tincan_gui/dbus_client.py`: new HFP call signals (`IncomingCall`, `CallConnected`, `CallEnded`, `AudioError`, `AudioRestored`) and `send_dtmf()` method.
- `tincan_gui/main.py`: `QStackedWidget` call panel state machine — `compose_stack` page-swap on call events, `IncomingCallDialog` float, keypad/DTMF page.
- `tests/tincan_gui/test_call_panel.py`: 12 behavioral acceptance tests (mock-only, no real D-Bus).
- `tests/tincand/test_dbus_contract.py`: contract table updated with HFP call signals; xfail guard for pending daemon interfaces.

## Ruff

`ruff check tincand/ tincan_gui/` — 3 errors found, all pre-existing on `origin/main`:
- `tincan_gui/degradation_banners.py:17` F401 (pre-existing)
- `tincan_gui/settings_dialog.py:447` E501 (pre-existing)
- `tincan_gui/thread_view.py:440` E501 (pre-existing)

New files introduced by this branch (`call_panel.py`, `main.py` changes, `dbus_client.py` changes, `avatar.py` fix): `ruff check tincan_gui/call_panel.py tincan_gui/avatar.py tincan_gui/main.py tincan_gui/dbus_client.py` — **All checks passed.**

## Commit log (above main)

```
2111828 fix(lint): address reviewer blockers for tincan-fx79v.2 call panel
660a3b8 feat(gui): MainWindow QStackedWidget call panel state machine (tincan-fx79v.2)
03944f2 feat(gui): HFP call signals + send_dtmf in TincandClient (tincan-fx79v.3)
b96c0cf test(call_panel): behavioral acceptance tests for IncomingCallDialog, InCallPanel, DTMFKeypad, AudioErrorPanel (tincan-fx79v.4)
283bbf1 feat(gui): call_panel.py — IncomingCallDialog, InCallPanel, DTMFKeypad, AudioErrorPanel (tincan-fx79v)
```
