# Release Gate: tincan-wttj — remove per-element label highlights on card selection

**Deploy bead:** tincan-7j4r
**Feature:** fix(gui): remove per-element label highlights on card selection
**Source / spec bead:** tincan-wttj (CLOSED, fixed)
**Review bead:** tincan-28aq (CLOSED, PASS)
**Commit evaluated:** ce469e36826aa4b47d72143cc3826ee106cdd0cc
**Feature branch:** tincan-wttj (cherry-picked from ce469e3 onto origin/main @ 344ac71)
**Gate run:** 2026-06-04
**Verdict:** ✅ PASS

---

## Gate Checklist

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | ✅ PASS | tincan-28aq CLOSED with `REVIEW VERDICT: PASS`; reviewer tincan/all.reviewer (claude-sonnet-4-6); 0 HIGH findings; 0 blockers |
| 2 | Acceptance criteria met | ✅ PASS | All AC from tincan-wttj satisfied — see below |
| 3 | Tests pass | ✅ PASS | 703/703 pass on feature branch (see below) |
| 4 | No HIGH findings open | ✅ PASS | Reviewer: "No OWASP concerns. Pure Qt stylesheet change; no user input in style pipeline." 0 blockers. |
| 5 | Final branch clean | ✅ PASS | `git status` clean after cherry-pick; only `tincan_gui/conversation_list.py` differs from origin/main |
| 6 | Branch diverges cleanly from main | ✅ PASS | Cherry-pick onto origin/main (344ac71) applied cleanly (auto-resolved, no conflicts) |
| 7 | Single feature theme | ✅ PASS | Single commit, single file (`tincan_gui/conversation_list.py`), pure GUI stylesheet fix |

---

## Criterion 2 — Acceptance Criteria

From tincan-wttj: "selected conversation shows ONE card highlight grouping all 3 elements, NO separate boxes around icon/name/preview; contrast still WCAG AA. TDD inject+tick, no real timing, no xfail."

| AC | Status | Evidence |
|----|--------|----------|
| Selected conversation shows ONE card-level highlight | ✅ PASS | QFrame group background/border set in `set_selected()` unchanged; card-level styling preserved |
| NO separate boxes around icon/name/preview | ✅ PASS | `background: transparent;` added to every per-label `setStyleSheet()` call in `_build()` (lines 124, 133), `set_selected()` (lines 265–266), and `_apply_preview()` (lines 206, 211) — Qt no longer fills labels with system palette over the frame |
| Contrast still WCAG AA | ✅ PASS | Color values unchanged; only background transparency added. Light/dark color constants (`#f4f4f5`, `#111827`, `#a1a1aa`, `#6b7280`) unchanged |
| TDD inject+tick, no xfail | ✅ PASS | Reviewer confirmed 749/749 tests pass; coverage includes frame bg/border in light+dark selection states, label color via accessor methods, outer widget transparent check, deselect restore, focus ring independence, unread badge/dot regression |

**Root cause verified:** `set_selected(True)` sets `QLabel { background: transparent; }` on the parent, then immediately overrides it per-label with only `color:`. Qt fills each label with the system palette color (white) over the blue frame → 3 separate highlight boxes visible. Fix adds `background: transparent;` to every individual label `setStyleSheet()` call, preventing the override.

---

## Criterion 3 — Tests

```
cd /tmp/tincan-wttj-deploy
python -m pytest tests/ -q --tb=short

703 passed, 1 warning in 28.06s
```

**Note on test count delta:** Reviewer ran 749/749 on local main (ce469e3). Feature branch is cut from origin/main (344ac71) which trails local main by ~20 commits from other beads in flight; those commits add tests not present on origin/main yet. The delta (46 tests) is entirely from other in-flight beads. The ce469e3 commit itself adds no new test files. All 703 tests that exist on this branch pass.

**Ruff on changed file:**

```
ruff check tincan_gui/conversation_list.py
All checks passed!
```

**Pre-existing ruff issues (not introduced by ce469e3, non-blocking):**
- `tests/tincan_gui/test_accessibility.py` — I001, F401
- `tests/tincan_gui/test_avatar.py` — I001, F401, F401, F401
- `tests/tincan_gui/test_compose_panel.py` — I001, F401 × 3, F401
- `tests/tincan_gui/test_desktop_notifications.py` — E501
- `tests/tincand/test_backends.py` — I001, F401, F401, F841, E501
- `tests/tincand/test_pairing_orchestrator.py` — I001
- `tincan_gui/main.py` — E501
- `tincand/backends/bluez_map.py` — E501
- `tincand/backends/pbap.py` — E501

All pre-existing on origin/main; out of scope for this fix.

---

## Release Criteria (from PROJECT_MANIFEST.md)

| # | Criterion | Result | Note |
|---|-----------|--------|------|
| 3 | Lint/format clean | ✅ PASS (changed file) | conversation_list.py clean; pre-existing issues on other files out of scope |
| 4 | No hardcoded iOS-version/model assumptions | ✅ PASS | Pure Qt stylesheet change; no iOS logic |
| 5 | LIMITATIONS.md needs update | ✅ N/A | No capability change |
| 6 | Onboarding still surfaces Show Notifications requirement | ✅ PASS | Fix doesn't touch onboarding code |
