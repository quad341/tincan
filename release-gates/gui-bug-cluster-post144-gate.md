# Release Gate: post-PR-144 GUI bug cluster fix

**Bead:** tincan-6bi9z  
**Branch:** feat/gui-bug-cluster-post144  
**Gate commit:** a75b50e  
**Date:** 2026-06-27  

## Gate Checklist

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | Reviewer PASS verdict at a75b50e in bead tincan-1f2u9 (3 iterations; final verdict 2026-06-27) |
| 2 | Acceptance criteria met | **PASS** | FR-C1/C2/C3/D all verified by reviewer at a75b50e (see below) |
| 3 | Tests pass | **PASS** | 2114 passed, 2 skipped, 10 xfailed — `pytest tests/ -x -q` on feat/gui-bug-cluster-post144 |
| 4 | No high-severity findings open | **PASS** | All BLOCK-1 and BLOCK-2 findings resolved; W3 (format-string minor) is non-blocking carry-forward |
| 5 | Final branch is clean | **PASS** | `git status` shows no staged/modified tracked files; only untracked worktree artifacts |
| 6 | Branch diverges cleanly from main | **PASS** | `git merge-base --is-ancestor origin/main feat/gui-bug-cluster-post144` → origin/main IS ancestor; no conflicts |
| 7 | Single feature theme | **PASS** | All 4 commits address post-PR-144 GUI followup bugs (setTextFormat security hardening, E501 lint, test fixture cleanup, core GUI fixes) — one coherent theme |

**Overall: PASS**

---

## Acceptance Criteria Verification

| Criterion | Status | Evidence |
|-----------|--------|----------|
| FR-C1: `_configure_bt_combo_width(adapter_combo, device_combo)` — minWidth=360, minContentsLength=42 | PASS | Verified by reviewer at a75b50e; `tincan_gui/settings_dialog.py` |
| FR-C2: `_first_valid_icon` helper + BMP fallback (⚙/⚠/☆) for all 3 TitleBar buttons | PASS | Verified by reviewer at a75b50e; `tincan_gui/main.py` |
| FR-C3: `adapter_combo.hide()` at init; `adapter_unavailable_frame.show()` at init; all banners hidden in no-adapters path | PASS | Verified by reviewer at a75b50e; `tincan_gui/main.py` |
| FR-D: `set_compose_new_enabled(False)` in `ConversationListWidget.__init__`; wired in `_on_daemon_connected/disconnected/_sync_daemon_state` | PASS | Verified by reviewer at a75b50e; `tincan_gui/conversation_list.py` |
| setTextFormat(PlainText) on AdapterMismatchBanner._label (security: prevents Qt HTML auto-detect on raw D-Bus strings) | PASS | a75b50e: `tincan_gui/degradation_banners.py:461` |
| setTextFormat(PlainText) on `_adapter_mismatch_annotation` in settings_dialog | PASS | 279b672: `tincan_gui/settings_dialog.py:597` |
| E501 lint lines in main.py, settings_dialog.py, test_main.py | PASS | 279b672: ruff exits 0 on all modified files |

---

## Commit Set

| SHA | Summary |
|-----|---------|
| b2c7241 | fix(gui): post-PR-144 bug cluster — orange rect, toolbar icons, compose button, combo width |
| f863fc6 | fix(tests): remove stale main._emoji_font_families patch from _fake_emoji_families fixture |
| 279b672 | fix(gui): BLOCK-1/2 — wrap 5 E501 lines, add setTextFormat on mismatch annotation |
| a75b50e | fix(gui): setTextFormat(PlainText) on AdapterMismatchBanner._label |

---

## Lint Notes

ruff I001/F401 in `tincan_gui/degradation_banners.py` are **pre-existing from main** (confirmed: same errors appear on origin/main at `feat/adapter-mismatch-banner-5y8km.2`). Not introduced by this diff.

---

## Follow-up

- tincan-h6y8v filed (needs-tests, validator): coverage for untested FR-C1 path.
