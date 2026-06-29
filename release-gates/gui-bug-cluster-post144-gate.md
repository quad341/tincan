# Release Gate: post-PR-144 GUI bug cluster fix (phase 2)

**Bead:** tincan-mi3tu  
**Branch:** feat/gui-bug-cluster-post144  
**Gate commit:** 788ca1c  
**Date:** 2026-06-28  

> **Supersedes** the prior gate at `a75b50e` (bead tincan-6bi9z, 2026-06-27).
> Two additional commits (`a2a61a0`, `788ca1c`) were added after that gate; this document re-evaluates the full branch.

## Gate Checklist

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-f03kj (closed, reason: pass) reviewed all fixes at `a2a61a0`; tincan-2gj5m (closed, reason: pass) reviewed QTimer fix at `788ca1c` — full PASS verdict on current HEAD |
| 2 | Acceptance criteria met | **PASS** | All 7 new bug-cluster fixes verified by reviewer in tincan-f03kj/tincan-2gj5m; prior cluster (6 commits incl. prior gate) was gate-passed at a75b50e |
| 3 | Tests pass | **PASS** | 2116 passed, 1 skipped, 9 xfailed — `pytest tests/ -x -q` on `788ca1c` (36.42s) |
| 4 | No high-severity findings open | **PASS** | Only BLOCK from tincan-f03kj was missing QTimer import; fixed in `788ca1c` and verified PASS in tincan-2gj5m |
| 5 | Final branch is clean | **PASS** | `git status` shows only untracked worktree artifacts (.claude/, .codex/, .gc/, .gitkeep) |
| 6 | Branch diverges cleanly from main | **PASS** | `git merge-base --is-ancestor origin/main HEAD` → origin/main is ancestor; no conflicts |
| 7 | Single feature theme | **PASS** | All commits address post-PR-144 GUI correctness bugs (visual regressions, signal leaks, race conditions, missing decorators) — one coherent bug-fix theme |

**Overall: PASS**

---

## Acceptance Criteria Verification

### Original cluster (commits b2c7241 → a75b50e, gate tincan-6bi9z)

| Criterion | Status | Evidence |
|-----------|--------|----------|
| `_first_valid_icon` helper + BMP fallback (⚙/⚠/☆) for all 3 TitleBar buttons | PASS | Reviewer PASS at a75b50e; `tincan_gui/main.py` |
| `_configure_bt_combo_width(adapter_combo, device_combo)` — minWidth=360, minContentsLength=42 | PASS | Reviewer PASS at a75b50e; `tincan_gui/settings_dialog.py` |
| `adapter_combo.hide()` at init; `adapter_unavailable_frame.show()` at init | PASS | Reviewer PASS at a75b50e; `tincan_gui/main.py` |
| `set_compose_new_enabled(False)` in `ConversationListWidget.__init__` | PASS | Reviewer PASS at a75b50e; `tincan_gui/conversation_list.py` |
| `setTextFormat(PlainText)` on `AdapterMismatchBanner._label` | PASS | a75b50e; `tincan_gui/degradation_banners.py:461` |
| `setTextFormat(PlainText)` on `_adapter_mismatch_annotation` in settings_dialog | PASS | 279b672; `tincan_gui/settings_dialog.py:597` |

### New cluster (commits a2a61a0 + 788ca1c, review tincan-f03kj + tincan-2gj5m)

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Loader signal dedup: `disconnect()` stale `_loader_thread.loaded` before reassign (hasattr guard) | PASS | tincan-f03kj PASS; `tincan_gui/settings_dialog.py` |
| Call signal cleanup: `old_sig.remove()` before overwriting `_call_sigs[call_id]` | PASS | tincan-f03kj PASS; `tincan_gui/call_controller.py` |
| ANCSRepairBanner: 10s `QTimer` start/stop logic correct | PASS | tincan-f03kj PASS (conditional on import); 788ca1c fixes the import |
| Banner refresh on connect: `_refresh_adapter_unavailable_banner` + `_refresh_adapter_mismatch_banner` called | PASS | tincan-f03kj PASS; `tincan_gui/main.py` |
| `get_calls()` guard: `len(c) >= 4` per tuple | PASS | tincan-f03kj PASS; `tincan_gui/dbus_client.py` |
| `@Slot(str, 'QByteArray')` on `_on_contact_photo_received` | PASS | tincan-f03kj PASS; `tincan_gui/dbus_client.py` |
| Stale `xfail` removed from `_on_contact_photo_received` tests | PASS | tincan-f03kj PASS; `tests/tincan_gui/conftest.py` |
| `QTimer` added to `PySide6.QtCore` import in `degradation_banners.py` | PASS | tincan-2gj5m PASS; `tincan_gui/degradation_banners.py` |

---

## Commit Set

| SHA | Summary |
|-----|---------|
| b2c7241 | fix(gui): post-PR-144 bug cluster — orange rect, toolbar icons, compose button, combo width |
| f863fc6 | fix(tests): remove stale main._emoji_font_families patch from _fake_emoji_families fixture |
| 279b672 | fix(gui): BLOCK-1/2 — wrap 5 E501 lines, add setTextFormat on mismatch annotation |
| a75b50e | fix(gui): setTextFormat(PlainText) on AdapterMismatchBanner._label |
| b8afbaa | chore: release gate PASS for gui-bug-cluster-post144 (tincan-6bi9z) |
| a2a61a0 | fix: 7-bead bug cluster — signal leaks, race conditions, missing decorators |
| 788ca1c | fix(gui): add QTimer to degradation_banners.py QtCore import |

---

## Test Summary

```
2116 passed, 1 skipped, 9 xfailed, 1 warning in 36.42s
pytest tests/ -x -q on feat/gui-bug-cluster-post144 @ 788ca1c
```

---

## Notes

- `mcp` module not installed — `test_mcp_server.py` collection warning is pre-existing, unrelated to this branch.
- Pre-existing ruff I001/F401 in `tincan_gui/degradation_banners.py` from `origin/main` — not introduced by this diff.
- `tincan-h6y8v` (needs-tests) tracks follow-up coverage for `_configure_bt_combo_width` path.
