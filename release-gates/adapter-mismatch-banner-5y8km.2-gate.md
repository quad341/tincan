# Release Gate: adapter-mismatch-banner-5y8km.2 (tincan-u1akq)

**Bead:** tincan-u1akq  
**Source bead:** tincan-y8u5z  
**Branch:** feat/adapter-mismatch-banner-5y8km.2 @ 5c0d0f3  
**Gate evaluated:** 2026-06-27  

## Verdict: PASS

All 7 criteria met against current `origin/main`. PR opened; merge-request routed to mayor.

⚠ **MERGE ORDERING NOTE:** `feat/resilient-tincand-bringup-dufe8` (PR #144) also adds `AdapterMismatchBanner` to `degradation_banners.py` and banner wiring to `main.py`. If PR #144 merges before this PR, this branch will have conflicts in those two files and must be rebased by the builder before merge. Mayor should decide merge order or consolidation strategy. The AC6 annotation in `settings_dialog.py` is UNIQUE to this branch.

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-y8u5z: "## Reviewer Verdict: PASS" for 5c0d0f3 on feat/adapter-mismatch-banner-5y8km.2. AC6 implementation verified; needs-tests bead tincan-5m88a filed per validator-dod.md option (b). |
| 2 | Acceptance criteria met | **PASS** | All 7 ACs verified in code. See AC detail below. |
| 3 | Tests pass | **PASS** | 2104 passed, 2 skipped, 10 xfailed (`pytest tests/tincand/ tests/tincan_gui/`) |
| 4 | No high-severity review findings | **PASS** | Reviewer findings: [INFO-1] hasattr guard in _refresh_adapter_mismatch_annotation — defensive, low risk; [INFO-2] pre-existing E501 in settings_dialog.py:235, :241 — on main, not introduced by this PR. No HIGH findings. |
| 5 | Final branch is clean | **PASS** | `git status` clean — only untracked agent artifacts (.claude/, .codex/, .gemini/, etc.). No staged or unstaged changes. |
| 6 | Branch diverges cleanly from main | **PASS** | `git merge-base origin/main HEAD` = f1dd8ed (current main). No conflicts with current origin/main. 3 files changed, 114 insertions. |
| 7 | Single feature theme | **PASS** | GUI-only branch: AdapterMismatchBanner class (AC1-5) + Adapter status row ⚠ annotation (AC6). One coherent user-facing feature. |

## Acceptance Criteria

- **AC1** PASS: `AdapterMismatchBanner` shown when `GetStatus().adapter_warning` is non-empty (`main.py:741`).
- **AC2** PASS: Non-dismissible `QFrame` — no close button, `setVisible` controlled only by daemon state.
- **AC3** PASS: `update_warning(text)` calls `_label.setText(text)` (verbatim text, not reformatted).
- **AC4** PASS: `degradation_banners.py:443` `background: #fff3bf; border-bottom: 2px solid #f59f00;`; icon+label `color: #7c4f00`.
- **AC5** PASS: `main.py:741-746` — `update_warning("")` hides + stops 5s timer; non-empty text shows + starts timer.
- **AC6** PASS: `settings_dialog.py:549` `_adapter_mismatch_annotation` QLabel with `color: #f59f00`, `accessibleName("wrong adapter detected")`, hidden by default. `_refresh_adapter_mismatch_annotation()` shows `⚠ (wanted: hciX)` via regex; hides on empty warning. `get_status()` called at dialog open to seed state.
- **AC7** PASS: `main.py:685` `setInterval(5000)` (5s ≤ spec's ≤5s). Timer starts when warning set, stops when clear.

## Commits

- 3157c43 feat(gui): AdapterMismatchBanner — persistent amber warning for wrong BT adapter (tincan-5y8km.2)
- 5c0d0f3 feat(gui): AC6 — adapter-mismatch ⚠ annotation on Adapter status row (tincan-5y8km.2)

## Files changed vs origin/main

- `tincan_gui/degradation_banners.py` (+50): `AdapterMismatchBanner` class + accessibility factory
- `tincan_gui/main.py` (+30): banner widget init, 5s timer, `_refresh_adapter_mismatch_banner()`, `_poll_adapter_mismatch()`
- `tincan_gui/settings_dialog.py` (+34): AC6 `_adapter_mismatch_annotation` QLabel + `_refresh_adapter_mismatch_annotation()`
