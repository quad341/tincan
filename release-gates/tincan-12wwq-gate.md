# Release Gate: tincan-12wwq — ruff lint fix + CI lint enforcement

**Bead:** tincan-12wwq (deploy bead)
**Feature:** Lint fix — ruff findings in tincand/tincan_gui/tests + CI lint blocking
**Source bead:** tincan-6erin (CLOSED)
**Review bead:** tincan-csxmo (CLOSED, PASS)
**Commit evaluated:** 9842776 (984277693780c870927944a3174ab862979aab9f) on origin/builder/tincan-6erin
**Gate run:** 2026-07-05
**Verdict:** ✅ PASS

---

## Gate Checklist

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | ✅ PASS | tincan-csxmo CLOSED, verdict PASS — independent 37-file hand-diff, security walk, no blockers |
| 2 | Acceptance criteria met | ✅ PASS | All four criteria from tincan-6erin re-verified directly (below) |
| 3 | Tests pass | ✅ PASS | 2416 passed, 1 skipped, 100.27s — re-run by deployer on branch merged with current origin/main tip |
| 4 | No HIGH findings open | ✅ PASS | 0 findings; reviewer's one note is explicitly informational/non-blocking, no code change required |
| 5 | Final branch clean | ✅ PASS | `git status` clean on evaluated branch |
| 6 | Branch diverges cleanly from main | ✅ PASS | `git merge-tree --write-tree origin/main origin/builder/tincan-6erin` exit 0; live test merge auto-merged cleanly |
| 7 | Single feature theme | ✅ PASS | One commit, one cohesive lint/CI-hygiene debt-paydown; not a bundle of independent features |

---

## Criterion 2 — Acceptance Criteria (re-verified independently)

- `ruff check tincand tincan_gui tests` → exit 0, "All checks passed!"
- `.github/workflows/ci.yml`: no `continue-on-error` anywhere in the file (grep confirmed); Lint (ruff) step at line 28-29 now blocks the Test step on failure.
- Full pytest suite passes (see Criterion 3).
- `tincan_gui/conversation_list.py`: exactly one `def set_compose_new_enabled` (line 547); accessibility calls restored inside it — `setAccessibleName("New conversation")` (line 552, enabled path) and `setAccessibleName(tooltip)` (line 559, disabled-with-explicit-tooltip path).

---

## Criterion 3 — Tests

Branch origin/builder/tincan-6erin was reviewed (tincan-csxmo) against origin/main @ c892a19. Since then origin/main advanced to 3faf6b4 (PR #176, "fix(calls): self-healing phone reconnect", touching `tincand/call_controller.py` + `tincand/dbus_service.py`). Re-ran the full gate independently on the branch merged with the current main tip to rule out interaction regressions:

```
ruff check tincand tincan_gui tests
All checks passed!

PYTHONPATH=. pytest tests/ -q
2416 passed, 1 skipped, 18 warnings in 100.27s (0:01:40)
```

Numbers match the reviewer's original run exactly, despite the intervening main history — no regressions introduced by the rebase gap.

---

## Criterion 6 — Merge Cleanliness

```
git merge-tree --write-tree origin/main origin/builder/tincan-6erin
2ea8b5df12959b33687cc915727cf61f781280f8   # exit 0 — no conflicts

git merge origin/main --no-edit   # live test on a scratch branch
Auto-merging tincand/dbus_service.py
Merge made by the 'ort' strategy.
```

No manual conflict resolution required; safe to open the PR from the branch as-is (no pre-emptive rebase performed — see guardrail against deployer-seat rebasing).
