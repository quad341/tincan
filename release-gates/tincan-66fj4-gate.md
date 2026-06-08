# Release Gate: tincan-66fj4
**Feature:** hide-conversation UX fixes (tincan-g28vr, tincan-gvv9o)
**Branch:** `fix/hide-conv-ux-p3`
**Tip commit:** `1f58956`
**Date:** 2026-06-08

## Gate Checklist

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | Reviewer PASS in tincan-cnj73 notes: "REVIEW VERDICT: PASS" (tincan/reviewer, claude-sonnet-4-6) |
| 2 | Acceptance criteria met | **PASS** | See per-bead check below |
| 3 | Tests pass | **PASS** | 1686 passed, 6 skipped, 6 xfailed — `pytest tests/ -x -q` on `fix/hide-conv-ux-p3` |
| 4 | No high-severity findings open | **PASS** | One INFO finding (iteration from idx 0, acceptable semantics). No HIGH/CRITICAL findings. |
| 5 | Final branch clean | **PASS** | `git status` clean (only untracked agent dirs) |
| 6 | Branch diverges cleanly from main | **PASS** | 1 commit ahead of `origin/main` (da693df), no conflicts |
| 7 | Single feature theme | **PASS** | Both bugs affect `archive_conversation()` in `conversation_list.py` — tightly coupled hide-conversation UX; not independently shippable |

**Overall: PASS**

---

## Acceptance Criteria per Bead

### tincan-g28vr: auto-select next conversation after hide
- **AC**: After hiding the selected conversation, thread view must not retain the hidden conversation's messages; next visible conversation is auto-selected, or view clears if none remain.
- **Verified**: `archive_conversation()` now calls `set_selected(False)` on the hidden item, then iterates `_items` to find the first visible one and emits `conversation_selected(conv_id)`. If no visible conversation remains, emits `conversation_selected("")`. `_on_conversation_selected` guards `conv_id == ""` with an early-exit that clears `_current_phone` and reloads the thread view with an empty conversation. ✅

### tincan-gvv9o: fix horizontal alignment after hide
- **AC**: Hiding a conversation must not leave stale 2px selected-border on a hidden item causing layout misalignment.
- **Verified**: Before calling `self._archived.archive(conv_id)`, the code now calls `self._items[self._selected_index].set_selected(False)` and resets `self._selected_index = -1`. This ensures no item retains `_selected=True` state after hiding. ✅

---

## Test Evidence

```
pytest tests/ -x -q  (on fix/hide-conv-ux-p3 @ 1f58956)

1686 passed, 6 skipped, 6 xfailed in 33.75s
```

New tests (`§3 TestAutoSelectAfterHide`, 4 tests in `tests/tincan_gui/test_hide_conversation.py`):
- `test_hiding_selected_emits_next_conversation` — hides selected c1 of [c1,c2,c3]; verifies `conversation_selected` fires with a remaining conversation ✅
- `test_hiding_selected_deselects_it` — verifies `_selected=False` on the hidden item ✅
- `test_hiding_only_conversation_emits_empty` — solo conversation hidden; verifies `conversation_selected("")` emitted ✅
- `test_hiding_non_selected_leaves_selection_unchanged` — non-selected hide; verifies no `conversation_selected` signal fires ✅

Lint: `ruff check` — all checks passed.

---

## Reviewer INFO finding
- `conversation_list.py:641`: auto-select iterates from idx 0 (not from hidden item's position), giving "first remaining visible" semantics rather than "next after hidden". Acceptable per reviewer — no behavioral regression; reviewer marked non-blocking.
