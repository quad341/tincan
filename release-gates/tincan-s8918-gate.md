# Release Gate: adapter-unavailable banner + adapter_path in GetStatus (tincan-s8918)

**Bead:** tincan-s8918  
**Feature bead:** tincan-crfu9 (adapter-unavailable banner + adapter_path in GetStatus)  
**Review bead:** tincan-kpfqb  
**Commit:** `6614427`  
**Branch:** `fix/call-setup-ready-z0qqo`  
**Date:** 2026-06-14

## Gate Criteria

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-kpfqb notes: "REVIEW VERDICT: PASS (deploy hold — 16 test failures remain for tincan-yn2x5)" |
| 2 | Acceptance criteria met | **PASS** | 7/7 ACs verified by reviewer; see below |
| 3 | Tests pass | **PASS** | CI green at branch tip `f20fbcb` (2 consecutive successes 2026-06-14T22:18Z, 22:27Z); original review at this commit: 1894 pass; branch tip adds more tests |
| 4 | No high-severity findings | **PASS** | Only LOW (lint I001 import ordering) and INFO findings; all CI non-blocking per `continue-on-error: true` |
| 5 | Final branch clean | **PASS** (with note) | `origin/fix/call-setup-ready-z0qqo` fully pushed and clean. Local working tree has unstaged `settings_dialog.py` modifications (builder in-progress work); these are NOT committed and NOT part of this deployment. |
| 6 | Branch diverges cleanly from main | **PASS** | `git merge-base --is-ancestor origin/main origin/fix/call-setup-ready-z0qqo` confirms linear ancestry, zero conflicts |
| 7 | Single feature theme | **PASS** | All branch commits relate to BT adapter detection, picker UI, and degraded-state banners — one coherent feature area |

## Acceptance Criteria Verification

**AC 1:** Full-width `QFrame` below title bar, above degradation banners: `AdapterUnavailableBanner(QFrame)` added to `root_layout` after `_title_bar`, before `_banner_a`. **✅**

**AC 2:** Shown when `adapter_path_requested != ''` and `adapter_path != adapter_path_requested`: `_refresh_adapter_unavailable_banner()` called from `_on_status_changed()`. **✅**

**AC 3:** Primary text (12pt #fbbf24): `_primary_label`, `QFont` 12pt, color `#fbbf24`, text `'⚠ Saved adapter {x} was unavailable — using {y} instead.'`. **✅**

**AC 4:** Action hint (11pt #78716c): `_hint_label`, `QFont` 11pt, color `#78716c`, text `'Change adapter in Settings → Bluetooth'`. **✅**

**AC 5:** Dismiss ✕ (top-right, #d97706, accessible name `'Dismiss adapter warning'`, session-only): `QToolButton`, accessible name set, `_adapter_unavailable_banner_dismissed` instance var (not `QSettings`). **✅**

**AC 6:** Colors bg `#422006` / border-bottom 1px `#d97706`. **✅**

**AC 7:** Accessibility — no focus steal on appear: `show()` called without `setFocus()`. **✅**

**GetStatus `adapter_path`:** Daemon-side addition correct. `set_adapter_path()` called before `set_adapter_path_requested()` in `main()`. **✅**

## Non-Blocking Findings

- **LOW:** `degradation_banners.py` I001 — import ordering (separate `from PySide6.QtCore import Qt` block); CI non-blocking.
- **INFO:** `GetStatus` docstring missing `adapter_path` field — minor doc gap.
- **INFO:** `get_status()` in `dbus_client.py` normalizes `adapter_path_requested` but not `adapter_path` — inconsistent setdefault; banner degrades gracefully.

## Hold Condition Resolution

Deploy hold placed by reviewer: "do not open PR until branch CI is green (16 test_adapter_picker.py failures)."

Resolution: `tincan-yn2x5` (BT adapter picker QComboBox) was built and closed. CI now green at branch tip `f20fbcb` with all adapter picker tests passing.

## Verdict: **PASS**
