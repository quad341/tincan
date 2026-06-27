# Release Gate: adapter-mismatch-banner-5y8km.2 (tincan-w45et)

**Bead:** tincan-w45et  
**Branch:** feat/adapter-mismatch-banner-5y8km.2 @ 1e8d7fa  
**Gate evaluated:** 2026-06-27  

## Verdict: FAIL

**Failing criterion: #6 — Branch diverges cleanly from main**

PR #144 merged to `origin/main` on 2026-06-27 and included overlapping changes to
`tincan_gui/degradation_banners.py` and `tincan_gui/main.py` (same AdapterMismatchBanner
code this branch adds). `git merge-tree --write-tree origin/main HEAD` exits 1 with:

```
CONFLICT (content): Merge conflict in tincan_gui/settings_dialog.py
```

The conflict is in `tincan_gui/settings_dialog.py` — PR #144 added the BT device picker
(+109 lines to settings_dialog.py) while this branch also modifies settings_dialog.py
(AC6 annotation, +34 lines). The AC6 annotation and test suite are NOT yet on main and
are valuable — the branch must be rebased, not abandoned.

**Action required:** Builder should rebase `feat/adapter-mismatch-banner-5y8km.2` onto
`origin/main`, resolving the conflict in `settings_dialog.py` by keeping:
- main's BT device picker code (already there from PR #144)
- this branch's AC6 `_adapter_mismatch_annotation` + `_refresh_adapter_mismatch_annotation()`
Then re-route to deployer.

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-y8u5z: "## Reviewer Verdict: PASS" for 5c0d0f3. |
| 2 | Acceptance criteria met | **PASS** | All 7 ACs verified (see prior gate for detail); AC6 annotation present in settings_dialog.py. |
| 3 | Tests pass | **PASS** | 2110 passed, 2 skipped, 10 xfailed on branch checkout. |
| 4 | No high-severity review findings | **PASS** | No HIGH findings. Pre-existing E501 lint in settings_dialog.py (unchanged lines). |
| 5 | Final branch is clean | **PASS** | `git status` clean on branch (no uncommitted changes). |
| 6 | Branch diverges cleanly from main | **FAIL** | `git merge-tree --write-tree origin/main HEAD` → conflict in `tincan_gui/settings_dialog.py`. PR #144 merged overlapping settings_dialog.py changes. Rebase required. |
| 7 | Single feature theme | **PASS** | GUI-only: AdapterMismatchBanner (AC1–5) + AC6 adapter-status annotation. Cohesive. |

## Net-new vs origin/main (not yet on main)

- `tests/tincan_gui/test_adapter_mismatch_banner.py` — 253-line test file (fully new)
- `tincan_gui/settings_dialog.py` — AC6: `_adapter_mismatch_annotation` QLabel + `_refresh_adapter_mismatch_annotation()`
- Gate file and test commit (1e8d7fa) added after prior deployer session.

(Note: `degradation_banners.py` AdapterMismatchBanner + `main.py` wiring are already on
main via PR #144 squash.)

## Prior gate

Prior gate (tincan-u1akq) PASSED when main was at `f1dd8ed` (pre-PR-#144). PR #145
(feat/adapter-mismatch-banner-5y8km.2) was opened then closed when PR #144 merged first,
pre-empting the merge. This gate reflects the post-PR-#144 state.
