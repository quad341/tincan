# Release Gate: tincan-eag9h — MAP self-heal BT/MAP reconnect without sudo

**Bead**: tincan-eag9h (deploy) → source tincan-55rci (review) → tincan-8u3xl (impl)  
**Branch**: feature/tincan-x9zu3  
**Commits in PR**: 74cedea (feat: MAP self-heal), 447e783 (test: double-submit guard coverage)  
**Gate run**: 2026-06-05  
**Result**: ❌ FAIL — lint errors in new code (criterion 3)

---

## Criteria

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | ✅ PASS | tincan-55rci closed with `Review verdict: PASS` by tincan/all.reviewer; commit 74cedea on feature/tincan-x9zu3 |
| 2 | Acceptance criteria met | ✅ PASS | All 4 exit_contract items verified: _bt_connect before OBEX ✓, backoff 10s→300s capped ✓, success resets counter ✓, BT failure doesn't abort OBEX ✓ |
| 3 | Tests pass | ✅ PASS | 1011/1011 pass (`python -m pytest tests/ -v`); 71/71 test_backends.py; 18/18 new MAP tests; 6/6 GUI guard tests |
| 4 | No high-severity findings | ✅ PASS | Review noted one minor nit (double assign `_reconnect_source_id = None` then reassigned); explicitly marked non-blocking |
| 5 | Final branch is clean | ✅ PASS | `git status` clean; only untracked infrastructure files not in repo |
| 6 | Branch diverges cleanly from main | ✅ PASS | `git merge --no-commit --no-ff origin/main` → "Automatic merge went well"; no conflicts |
| 7 | Single feature theme | ✅ PASS (with note) | Two commits: 74cedea (MAP daemon reconnect) + 447e783 (GUI send-guard test coverage). 447e783 is test-only; the `_pending_sends` double-submit guard it tests is already in origin/main (`tincan_gui/main.py:878`). Not an independent new feature — completing test coverage for shipped code. |

**Release criteria from PROJECT_MANIFEST.md:**

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| RC-1 | Phase definition-of-done met | ✅ N/A | Reconnect improvement; phase-1 DoD (hold SMS conversation) not blocked |
| RC-2 | All automated tests pass | ✅ PASS | 1011/1011 |
| RC-3 | Lint/format clean (ruff, black) | ❌ **FAIL** | See details below |
| RC-4 | No hardcoded iOS-version assumptions | ✅ PASS | No iOS version strings in diff; device matched by Bluetooth Address equality |
| RC-5 | LIMITATIONS.md updated if needed | ✅ PASS | Reconnect improvement doesn't change capability limits; no LIMITATIONS.md update needed |
| RC-6 | Onboarding still surfaces reconnect/Show Notifications | ✅ PASS | No onboarding code changed |

---

## ❌ Lint FAIL (RC-3)

`python -m ruff check tincand/backends/bluez_map.py tests/tincand/test_backends.py tests/tincan_gui/test_double_submit_guard.py` produced 3 errors, **2 of which are NEW** (introduced by commits in this PR):

### New errors (introduced by this PR — builder must fix)

**`tests/tincand/test_backends.py:766` — E501 (from 74cedea)**
```
patch("tincand.backends.bluez_map.dbus.Interface", side_effect=lambda o, i: mock_obj_mgr):
```
Line is 103 chars; limit is 99. Split the line continuation.

**`tests/tincan_gui/test_double_submit_guard.py:19` — I001 (from 447e783)**
```
from __future__ import annotations
[blank line]
from unittest.mock import patch
[blank line]
import pytest
from PySide6.QtCore import QCoreApplication
...
```
Import block is un-sorted; `from __future__` must be in its own block. Run `ruff --fix` or manually reorder.

### Pre-existing error (NOT a regression, not blocking this PR specifically)

**`tincand/backends/bluez_map.py:371` — E501 (pre-existing, not in this PR's diff)**
```
body = _parse_bmsg_body(raw_bmsg) or str(props.get("Subject", "")).strip() or "New message"
```
107 chars. Pre-dates this branch (not in 74cedea diff). Noted for completeness; not a regression from this PR.

---

## Disposition

Gate **FAIL** on RC-3 (lint). Routing back to builder.

Builder action required:
1. Fix `tests/tincand/test_backends.py:766` — split the long mock-patch line
2. Fix `tests/tincan_gui/test_double_submit_guard.py:19` — sort imports (run `ruff --fix`)
3. Optionally fix `tincand/backends/bluez_map.py:371` (pre-existing; not required for this gate)
4. Re-push `feature/tincan-x9zu3`; re-trigger deploy

All other gate criteria (review PASS, tests, no HIGH findings, clean merge) are satisfied.
