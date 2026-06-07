# PRD: Fix Right-Click Copy in Message Bubbles

**Bead:** tincan-4ozsq  
**Type:** Bug Fix  
**Priority:** P2  
**Date:** 2026-06-07  

---

## Problem Statement

**What:** Selecting text in a message bubble and choosing "Copy" from the right-click context menu places nothing on the clipboard. The action silently fails.

**Who:** Any Tincan desktop user who tries to copy text from a received or sent message.

**Impact:** Core text-selection usability is broken. The right-click menu shows "Copy" enabled when text is selected, creating a clear user expectation that is not met. This erodes trust in the GUI.

**Root cause (confirmed):** `tincan_gui/thread_view.py:616` in `contextMenuEvent` calls `self._body_label.copy()`. `_body_label` is a `QLabel` instance (assigned at line 455, constructed at line 434). `QLabel` does not have a `.copy()` method — it raises `AttributeError`. The correct pattern is `QApplication.clipboard().setText(label.selectedText())`.

---

## Goals

- **G1:** "Copy" on selected text puts *exactly the selected text* on the system clipboard.
- **G2:** "Copy" on partially-selected text never silently falls back to the full message body — the selection boundary must be respected.
- **G3:** No regression to the other three context-menu actions (Copy Message, Copy Link, Select All), which already work correctly.

## Non-Goals

- No change to context-menu appearance, menu item labels, or keyboard shortcuts.
- No change to daemon/IPC layer — this is GUI-only.
- No change to `QLabel` text rendering, link-click behavior, or selection highlighting.

---

## User Stories

1. **As a user**, I select part of a received message and right-click → Copy; the selected text is now in my clipboard and I can paste it elsewhere.
2. **As a user**, I select all text in a bubble via "Select All" then right-click → Copy; the full message body is on my clipboard.
3. **As a user**, I right-click a bubble without selecting text; Copy is disabled (existing behavior — must remain unchanged).

---

## Functional Requirements

| ID | Requirement | Acceptance Criteria |
|----|-------------|---------------------|
| FR-1 | Replace the broken `.copy()` call with a clipboard write using the label's selected text. | `QApplication.clipboard().setText(self._body_label.selectedText())` (or equivalent) is called when "Copy" is chosen. |
| FR-2 | If `selectedText()` returns an empty string (e.g. race between `hasSelectedText` check and action), the clipboard must not be cleared. | Guard: only write to clipboard when `selectedText()` is non-empty. `copy_act.setEnabled(self._body_label.hasSelectedText())` already gates the menu item; the handler should still be defensive. |
| FR-3 | No `AttributeError` is raised on "Copy". | Manual test: select text → right-click → Copy → paste elsewhere confirms text. No exception in `tincan-gui` log. |
| FR-4 | "Copy Message", "Copy Link", and "Select All" behavior is unchanged. | Each of those three branches must be exercised and verified in the same manual test session. |

---

## Non-Functional Requirements

| ID | Requirement | Metric |
|----|-------------|--------|
| NFR-1 | Fix is contained to `tincan_gui/thread_view.py`. | Diff touches only this file, only the `contextMenuEvent` handler body. |
| NFR-2 | No new imports required beyond what's already at the top of `thread_view.py`. | `QApplication` is already imported; verify before adding any import. |

---

## Technical Constraints

- GUI layer: PySide6 (`QLabel`, `QApplication.clipboard()`) — see `PROJECT_MANIFEST.md` Tech Stack.
- `QLabel` text interaction is controlled via `textInteractionFlags`; the label must have `Qt.TextSelectableByMouse` set for `selectedText()` to work. Verify this is already set at construction (line ~434).
- The fix must not break the daemon/client API boundary — this is a pure GUI fix with no IPC change.

---

## Dependencies

- None external. This depends only on PySide6, which is already a project dependency.

---

## Open Questions

- **OQ-1:** Does `_body_label` have `Qt.TextSelectableByMouse` set? If not, `selectedText()` will always return `""` and the fix will seem to work but copy nothing. The architect should confirm this is set (or add the flag as part of the fix).
- **OQ-2:** Should "Copy" be renamed "Copy Selection" to be explicit? Deferred to designer — out of scope for this bug fix PRD.

---

## Architecture Scope

This bug requires **no architecture decision**. The fix is a one-line change in `tincan_gui/thread_view.py`. The architect's role here is to:

1. Confirm OQ-1 (TextSelectableByMouse flag) by inspecting the widget construction.
2. Confirm `QApplication` is already imported in `thread_view.py` (no new dependency needed).
3. Sign off that no other widget in the codebase shares this same `.copy()` antipattern.

No design (UI/UX) work is required — the context menu structure is unchanged.
