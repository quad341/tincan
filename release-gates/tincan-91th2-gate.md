# Release Gate: tincan-91th2 — fix NewConversationDialog eventFilter crash

**Bead**: tincan-8ee6x (deploy) → tincan-20z1o (review) → tincan-91th2 (impl)  
**Branch**: feature/tincan-91th2  
**Commits in PR #42**: 8bf82d5 (eventFilter guard), c251370 (notifications observability — tincan-ikpf9, out-of-scope)  
**Gate run**: 2026-06-05  
**Result**: ⚠️ RETROACTIVE — PR #42 merged at 20:28:03Z before formal deployer gate ran

> **Note**: The operator merged this branch directly (PR body: "Generated with Claude Code"), bypassing the deployer pipeline. This gate is a post-merge audit. RC-3 would have caused a FAIL and lint-fix cycle before deploy.

---

## Criteria

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | ✅ PASS | tincan-20z1o closed `Review verdict: PASS` by tincan/all.reviewer; commit 8bf82d5 on feature/tincan-91th2 |
| 2 | Acceptance criteria met | ✅ PASS | Root cause confirmed (installEventFilter before _autocomplete init); both eventFilter calls deferred to after _autocomplete created; _autocomplete.installEventFilter(self) added for Up/Return handling; 4 regression tests cover the crash path |
| 3 | Tests pass | ✅ PASS | 1036/1036 pass per reviewer + builder notes; no failures reported |
| 4 | No high-severity review findings | ✅ PASS | Reviewer found no HIGH findings; style only (minimal reorder, no new logic) |
| 5 | Final branch clean | ✅ PASS | PR #42 merged without conflicts; branch fully incorporated into main |
| 6 | Branch diverges cleanly from main | ✅ PASS | Merged successfully; no conflict markers |
| 7 | Single feature theme | ⚠️ DEVIATION | PR included c251370 (tincan-ikpf9 notifications/observability) alongside 8bf82d5 (tincan-91th2 eventFilter). These address different subsystems. tincan-ikpf9 was simultaneously shipped via its own PR #41 (same change), resulting in the notifications fix appearing twice in main (as squash-merged content in both e8d9d1f and 2bc1e5b). Work is already on main; flag for PM awareness. |

## Release Criteria from PROJECT_MANIFEST.md

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| RC-1 | Phase definition-of-done met | ✅ N/A | Bug fix; phase-1 DoD (hold SMS conversation) not blocked |
| RC-2 | All automated tests pass | ✅ PASS | 1036/1036 |
| RC-3 | Lint/format clean (ruff, black) | ❌ FAIL (retroactive) | Two issues in new tests introduced by 8bf82d5 (see below) |
| RC-4 | No hardcoded iOS-version assumptions | ✅ PASS | Diff touches tincan_gui/main.py eventFilter ordering and test file only; no iOS version strings |
| RC-5 | LIMITATIONS.md updated if needed | ✅ PASS | No capability changes; LIMITATIONS.md not required |
| RC-6 | Onboarding still surfaces reconnect/Show Notifications | ✅ PASS | No onboarding code changed |

---

## ❌ RC-3 Lint Issues (retroactive — work already merged)

`ruff check tests/tincan_gui/test_new_conversation.py` (at origin/main):

**`tests/tincan_gui/test_new_conversation.py:127` — F841 (new, introduced by 8bf82d5)**
```python
contacts = [{"name": "Alice", "phone": "+14155550001"}]
```
Assigned but never used in `test_load_thread_called_for_single_phone`. Remove the assignment.

**`tests/tincan_gui/test_new_conversation.py:201` — I001 (new, introduced by 8bf82d5)**
```python
from PySide6.QtCore import QEvent
from PySide6.QtGui import QKeyEvent
from PySide6.QtCore import Qt as _Qt   # duplicate module, unsorted
```
Inline imports in `test_key_down_does_not_crash` have duplicate `PySide6.QtCore` entries and are unsorted. Move to top-of-file imports or sort/deduplicate.

**`tincan_gui/main.py:2` — I001 (pre-existing, not a regression)**
Import block unsorted; present before this PR's diff. Not blocking for this PR specifically.

---

## Disposition

**Retroactive gate.** The two RC-3 lint errors are in new test code and would have triggered a FAIL → builder-fix cycle before deploy. Follow-up cleanup bead filed (see below).

**Criterion 7 deviation** (scope contamination): c251370 was committed to feature/tincan-91th2 by the builder but belongs to tincan-ikpf9. That work shipped in the same PR, resulting in the tincan-ikpf9 fix landing twice on main. Low functional impact (second application of same change is a no-op if the file state matches); no correctness risk. PM flagged.

**Actions taken:**
- Gate file committed to feature/tincan-x9zu3 (deployer branch) for audit record
- Deploy bead tincan-8ee6x closed with PR #42 reference
- Mayor notified of retroactive gate status and lint follow-up
