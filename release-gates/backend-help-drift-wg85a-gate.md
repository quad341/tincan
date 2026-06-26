# Release Gate: backend-help-drift-wg85a

**Bead:** tincan-wg85a — Fix --backend help text drift (from:tincan-fub33)  
**Branch:** fix/backend-help-drift-wg85a  
**Cherry-pick SHA:** 956e11dd603675bc6aa5a0c7fd2f131bbeba475a  
**Gate date:** 2026-06-26  

## Criteria

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | ✅ PASS | Reviewer PASS recorded in tincan-wg85a bead notes: "Reviewed + PASSED by tincan/reviewer" |
| 2 | Acceptance criteria met | ✅ PASS | `--help` output verified live (per reviewer): shows `{ancs,map,mock}` and `Choices: ancs, map, mock`. f-string `f"Choices: {', '.join(sorted(_BACKENDS))}."` computes help from `_BACKENDS` directly — drift impossible |
| 3 | Tests pass | ✅ PASS | `2104 passed, 2 skipped, 10 xfailed, 0 failures` on the assembled branch (run 2026-06-26) |
| 4 | No high-severity findings open | ✅ PASS | Review PASS, no HIGH findings mentioned |
| 5 | Final branch is clean | ✅ PASS | `git status` shows no uncommitted tracked changes; only untracked `.gc`-setup files not part of the PR |
| 6 | Branch diverges cleanly from main | ✅ PASS | Cherry-pick applied with no conflicts: `1 file changed, 1 insertion(+), 1 deletion(-)` |
| 7 | Single feature theme | ✅ PASS | One file (`tincand/__main__.py`), one change (CLI help text), one subsystem (entrypoint). No independent features bundled |

## Verdict: PASS

## Diff summary

```diff
-            "Choices: mock, ancs."
+            f"Choices: {', '.join(sorted(_BACKENDS))}."
```

One line in `tincand/__main__.py:34`. No config changes, no new endpoints, no migration required.
