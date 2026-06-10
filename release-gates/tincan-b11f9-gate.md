# Release Gate: HFP call UI answer/hangup/dial + call_setup_ready (tincan-b11f9)

**Branch:** feat/call-ui-jni3z  
**HEAD:** 11826c6f4633112fb9520f60747ff2df03826852  
**PR:** [see bead notes after creation]  
**Gate evaluated:** 2026-06-10  

## Gate Result: PASS

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-4nvok closed reason=pass (cycle-2 after tincan-8pgco needs-tests bead filed); reviewer (tincan/reviewer, Sonnet 4.6) |
| 2 | Acceptance criteria met | **PASS** | See acceptance check below |
| 3 | Tests pass | **PASS** | 1703 passed, 6 skipped, 6 xfailed (pytest --ignore test_mcp_server.py; same as main; test coverage for new code tracked in tincan-8pgco per review criterion (b)) |
| 4 | No high-severity findings open | **PASS** | Zero HIGH findings; HangUp→Hangup fix verified correct; advisory: test coverage criterion satisfied via tincan-8pgco needs-tests bead |
| 5 | Final branch is clean | **PASS** | `git status` clean; untracked .claude/.codex/.gc/.gemini are harness artifacts |
| 6 | Branch diverges cleanly from main | **PASS** | Single commit ahead of merge base 82d8b05; branch is 1 commit behind current main (78c8700) but diverges cleanly — no conflicts |
| 7 | Single feature theme | **PASS** | HFP call UI only: answer/hangup/dial D-Bus methods, call_setup_ready capability gating, CallSetupRequiredBanner, IncomingCallDialog.disable_answer(). Also includes refresh_contacts() from PR #107 (pending) — creates a merge-order dependency (see note below). |

## Acceptance Criteria (tincan-jni3z)

- `dbus_client.answer(call_id)`, `.hangup(call_id)`, `.dial(number)→str` → fire-and-forget D-Bus to `im.tincan.Calls` ✓
- `call_panel.IncomingCallDialog.disable_answer(reason)` → disables Answer btn, sets tooltip + accessible description ✓
- `degradation_banners.CallSetupRequiredBanner` → 32px amber banner, shown when `call_setup_ready=False` ✓
- `main.py` tracks `_call_setup_ready`; `_apply_capabilities` handles capability flag ✓
- Incoming call flow wired: `_on_answer_accepted` → `answer()` + enter in-call; `_on_call_decline` → `hangup()` ✓
- Bug fix: `_on_hang_up` was using wrong D-Bus method name `HangUp` (spec: `Hangup`) — corrected ✓

## Merge Note

This branch includes `refresh_contacts()` (from `fix/emoji-notif-center-ux`, PR #107). Merge PR #107 first — once on main the diff for this PR shows only call-UI changes, keeping review clean.

## Lint

`ruff check tincan_gui/ tincand/`: 3 errors — all pre-existing on main (degradation_banners.py:17, settings_dialog.py:445, thread_view.py:499). None introduced by this branch.
