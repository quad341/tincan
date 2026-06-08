# Release Gate: tincan-bgj3k

**Bead:** tincan-bgj3k — GUI batch 1 — ubsu5 cherry-pick + validator TDD tests  
**Branch:** fix/gui-bugs-batch1  
**Gate evaluated at:** 3a0d683 (branch tip)  
**Reviewed commit:** 2ea3b34 (review bead: tincan-8dlc1)  
**Date:** 2026-06-08

## Result: PASS ✅

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | ✅ PASS | tincan-8dlc1 closed with reason "pass"; reviewer tincan/reviewer verdict: **PASS** on commits 8edb1fe + 2ea3b34. Additional commit 3a0d683 (tincan-80wbb, tests-only) acknowledged in review notes. |
| 2 | Acceptance criteria met | ✅ PASS | §12 outbound-body-upgrade criteria verified by TestOutboundBodyUpgrade (3 tests) and TestOutboundSortKeyGuard (4 tests). Upgrade logic reviewed: longer-wins comparison, `_outbound_by_dk` index, in-place list replacement all correct. |
| 3 | Tests pass | ✅ PASS | `pytest tests/ -q --ignore=tests/tincand/test_mcp_server.py` → **1676 passed, 6 skipped, 6 xfailed, 0 failures** (35.47s) |
| 4 | No high-severity findings open | ✅ PASS | One LOW finding: E501 in test docstring (102 chars > 99 limit), non-blocking. Zero HIGH or MEDIUM findings. |
| 5 | Final branch is clean | ✅ PASS | `git status` clean; no uncommitted changes |
| 6 | Branch diverges cleanly from main | ✅ PASS | `git merge-base --is-ancestor origin/main HEAD` confirmed; 8 commits ahead, no merge conflicts |
| 7 | Single feature theme | ✅ PASS | All commits are GUI-layer correctness fixes (isk9x batch2 fixes, ubsu5 sent-body cache fix, mark-read UI test coverage). One subsystem, one branch, coherent batch. |

## Scope

**New commits in bgj3k scope (since tincan-isk9x gate at 513ed4c):**
- `8edb1fe` — tests(tincan-ubsu5): TDD tests for outbound body upgrade (TestOutboundBodyUpgrade ×3, TestOutboundSortKeyGuard ×4)
- `2ea3b34` — fix(gui): apply ubsu5 sent-body-prefer-cache fix (tincan-ubsu5, tincan-mk28j)
- `3a0d683` — test(gui): cover _on_notification_mark_read optimistic UI update (tincan-80wbb) — tests-only, reviewed in notes

**Previous gate on this branch:** release-gates/tincan-isk9x-gate.md (513ed4c)

## PR

**Existing PR #99:** https://github.com/quad341/tincan/pull/99  
(PR opened by deployer for tincan-isk9x; bgj3k commits extend the same branch — PR auto-updated)

**Note:** PR #100 (fix/sent-body-prefer-cache-ubsu5) contains the same ubsu5 fix on a standalone branch and is now superseded by PR #99. Mayor to close PR #100 after #99 merges.
