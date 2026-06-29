# Release Gate: bug-hunt sweep — 5 correctness fixes

**Bead:** tincan-ulnx6 (deploy) / tincan-xh0fc (review) / tincan-0nuxm (source)
**Branch:** `fix/bug-hunt-sweep-0nuxm`
**Commit:** `afbd0e4`
**Date:** 2026-06-28

## Gate Results

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-xh0fc closed with reason=pass; reviewer-gm-wisp-z8oesf9 issued `VERDICT: PASS` |
| 2 | Acceptance criteria met | **PASS** | All 5 fixes verified by reviewer (see below) |
| 3 | Tests pass | **PASS** | 2114 passed, 2 skipped, 10 xfailed (--ignore=test_mcp_server.py) in 49.52s |
| 4 | No high-severity findings | **PASS** | Reviewer found 0 HIGH findings; 2 INFO-level pre-existing ruff issues, non-blocking |
| 5 | Final branch is clean | **PASS** | `git status` clean on `fix/bug-hunt-sweep-0nuxm` |
| 6 | Branch diverges cleanly from main | **PASS** | 1 commit ahead of `origin/main`; no merge conflicts |
| 7 | Single feature theme | **PASS** | All 5 fixes are GUI+daemon correctness in one coherent bug-hunt sweep |

**Overall: PASS**

## Fix Verification (per reviewer tincan-xh0fc)

1. **`tincand/__main__.py` — Adapter fallback** (`first_adapter` tracking): fallback order (powered > first-found > `/org/bluez/hci0`) is correct for single-adapter `hci0` systems. Default changed from `hci1` → `hci0`. ✓
2. **`tincan_gui/main.py:_exit_call`** — `_incall_dialog` close + null guard prevents stuck call UI on remote hangup. Correct Qt lifecycle pattern. ✓
3. **`tincan_gui/main.py:_on_daemon_disconnected`** — `_pending_sends.clear()` consistent with surrounding cache-clear block; fixes resend-after-reconnect. ✓
4. **`tincan_gui/main.py` — Duplicate `_on_file_bug`**: dead first definition removed; kept definition updated with Qt6 enum forms (`StandardButton.Ok`, `DialogCode.Accepted`). ✓
5. **`tincan_gui/degradation_banners.py:395`** — `setTextFormat(PlainText)` on `_primary_label`: correct XSS defense for Qt labels with untrusted adapter-path strings. ✓

## Test Summary

```
2114 passed, 2 skipped, 10 xfailed, 1 warning in 49.52s
```

Run: `pytest --ignore=tests/test_mcp_server.py -q` in `fix/bug-hunt-sweep-0nuxm` worktree.

(The `test_mcp_server.py` collection error is a pre-existing env issue — `mcp` package absent — not introduced by this branch.)
