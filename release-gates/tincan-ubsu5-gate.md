# Release Gate: tincan-ubsu5

**Feature:** fix(gui): prefer cached full body over truncated MAP echo for sent messages  
**Branch:** `fix/sent-body-prefer-cache-ubsu5`  
**Commit:** `c6152e2165530a9de63f1a420ddb0985a35e6eb0`  
**Deploy bead:** tincan-fmlwi  
**Source bead:** tincan-ubsu5  
**Review bead:** tincan-bud9o  
**Date:** 2026-06-08  

## Gate Result: PASS

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-bud9o — `VERDICT: PASS` by tincan/reviewer (claude). Single-pass (gemini second-pass disabled). |
| 2 | Acceptance criteria met | **PASS** | AC1: `add_message()` guard skips shorter body at same sort_key ✓; AC2: `_outbound_by_dk` upgrade restores full URL/body after daemon restart ✓; AC3: 1666 tests pass ✓ |
| 3 | Tests pass | **PASS** | `python -m pytest tests/ -q --ignore=tests/tincand/test_mcp_server.py` → **1666 passed, 6 skipped, 6 xfailed** (35.83s) |
| 4 | No high-severity review findings open | **PASS** | Review findings: 3 × INFO only. No HIGH or CRITICAL findings. |
| 5 | Final branch is clean | **PASS** | `git status` shows only untracked system directories (.beads, .claude, .codex, .gc, .gemini); no uncommitted tracked changes. |
| 6 | Branch diverges cleanly from main | **PASS** | `git merge --no-commit --no-ff origin/main` → "Already up to date." No conflicts. |
| 7 | Single feature theme | **PASS** | Two files changed: `tincan_gui/main.py` (+17 lines) and `tincan_gui/message_cache.py` (+10 lines). Both in the GUI message display/cache subsystem. One bug: sent-body truncation after daemon restart. |

## Changed Files

| File | +/- | Summary |
|------|-----|---------|
| `tincan_gui/message_cache.py` | +10 | `add_message()`: skip incoming body if existing entry at same sort_key is longer |
| `tincan_gui/main.py` | +17 | `_load_thread_messages()`: build `_outbound_by_dk` index before cache pass; upgrade daemon entry when cached body is longer; same upgrade for `_sent_cache` pass |

## Review Findings (INFO — non-blocking)

- **INFO** `tincan_gui/main.py:810-832` — `_outbound_by_dk` upgrade logic is safe; longer body wins in all ordering scenarios (including MAP echo before full body).
- **INFO** `tincan_gui/message_cache.py:70-78` — sort_key guard uses strict `>`; equal-length different-content bodies both stored but `MAX_MESSAGES` bounds accumulation.
- **INFO** coverage — `tincan-th1sf` filed (validator in progress); satisfies coverage rule condition (b).

## Follow-up

- `tincan-th1sf` (needs-tests): validator adding `TestOutboundSortKeyGuard` unit tests + behavioral integration test §12. Non-blocking per coverage rule condition (b).
