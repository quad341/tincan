# Release Gate: HFP call UI wiring + tests (tincan-lx80j)

**Branch:** feat/call-ui-jni3z-land  
**HEAD:** 6953605a923d380f1ec180b3be33a69118ffc790  
**PR:** https://github.com/quad341/tincan/pull/113  
**Gate evaluated:** 2026-06-10  

## Gate Result: PASS

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-0z8d7 closed reason=pass; reviewer (tincan/reviewer, Sonnet 4.6) verdict: "Review Verdict: PASS" on commit 6953605a923d380f1ec180b3be33a69118ffc790 |
| 2 | Acceptance criteria met | **PASS** | See per-bead check below |
| 3 | Tests pass | **PASS** | 1710 passed, 6 skipped, 6 xfailed (pytest --ignore test_mcp_server.py; 23/23 target tests in test_call_ui_jni3z.py) |
| 4 | No high-severity findings open | **PASS** | 3 ADVISORY findings only (UX copy inconsistency, SCO spike still open, integration smoke hardware-gated). Zero HIGH. |
| 5 | Final branch is clean | **PASS** | `git status` clean; untracked .claude/.codex/.gc/.gemini are harness artifacts |
| 6 | Branch diverges cleanly from main | **PASS** | `git merge --no-commit --no-ff origin/main` = "Automatic merge went well"; no conflicts |
| 7 | Single feature theme | **PASS** | HFP call UI wiring — answer/hangup/dial D-Bus client methods + call_setup_ready capability handling, all in tincan_gui package |

## Per-Bead Acceptance Check

### tincan-jni3z — HFP answer/hangup/dial methods + call_setup_ready capability
- `dbus_client.py`: `answer()`, `hangup()`, `dial()` on `TincandClient` using `im.tincan.Calls`; str() coercion, empty-string fallback
- `call_panel.py`: `IncomingCallDialog.disable_answer(reason)` — disables button, tooltip, accessibleDescription
- `degradation_banners.py`: `CallSetupRequiredBanner` — 32px amber, accessible role StaticText
- `main.py`: `_call_setup_ready` defaults True; `_banner_call_setup` hidden by default; `_apply_capabilities` handles `call_setup_ready`; `_on_call_incoming` disables Answer when not ready; `_on_answer_accepted` calls `dbus.answer()` + `_enter_call()`; `_on_call_decline` calls `dbus.hangup()` + clears `_incall_dialog`; `_on_hang_up` uses public `hangup()` (fixes latent HangUp→Hangup method name bug)
- Code: commit 08d1ed4
- **PASS**

### tincan-8pgco — 23 tests for HFP call UI wiring
- `tests/tincan_gui/test_call_ui_jni3z.py`: §1 `disable_answer` (3 tests), §2 `_apply_capabilities call_setup_ready` (3), §3 `_on_answer_accepted` (2), §4 `_on_call_decline` (2), §5 `_on_hang_up` (1), §6 `TincandClient.answer/hangup/dial` (12)
- All 23 pass: `pytest tests/tincan_gui/test_call_ui_jni3z.py` → `23 passed in 0.31s`
- Code: commit 6953605
- **PASS**

## Lint

`ruff check tincan_gui/ tincand/`: 3 errors — all pre-existing on main (`degradation_banners.py:17`, `settings_dialog.py:445`, `thread_view.py:499`). None introduced by this branch.

## Advisories (non-blocking)

- Minor UX copy inconsistency: banner uses em-dash, dialog tooltip uses period (from review bead)
- tincan-xy2sb SCO audio spike still OPEN; `call_setup_ready=False` gating provides runtime protection
- Integration/smoke (validator-dod.md criterion 3) hardware-gated; accepted under reviewer coverage option (a)
