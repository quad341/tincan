# Release Gate: MAP reconnect storm fix (tincan-bleim)

**Bead:** tincan-bn3tx (deploy) ← tincan-bleim (feature)
**Branch:** `fix/map-reconnect-storm-bleim`
**Head commit:** `d5b899cda9cba948acb883ff6052c1a3474de60c`
**PR:** quad341/tincan#117
**Date:** 2026-06-10
**Verdict:** ❌ FAIL

---

## Gate Criteria

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | ✅ PASS | tincan-5iyun closed with pass verdict; full ensemble: Qwen ok · Claude ok · Codex ok; synthesis: auto-merge |
| 2 | Acceptance criteria met | ✅ PASS | `_update_inbox_unsupported` flag: set on first UnknownObject/UnknownMethod/UnknownInterface from UpdateInbox, skipped silently on subsequent polls, reset in `connect()`. Dead-session detection preserved via SetFolder/ListMessages propagating UnknownObject to `_poll_tick`. 13 behavioral tests confirm all paths. |
| 3 | Tests pass | ❌ FAIL | `ruff check tincand/backends/bluez_map.py tests/tincand/test_backends.py` → 1 E501 error (see below). pytest: 1702 passed, 6 skipped, 6 xfailed — no regressions. |
| 4 | No HIGH findings open | ✅ PASS | Ensemble review found no HIGH severity findings. |
| 5 | Final branch clean | ✅ PASS | `git status` — no uncommitted tracked changes. |
| 6 | Branch diverges cleanly from main | ✅ PASS | 3 commits ahead of `origin/main`, no conflicts. |
| 7 | Single feature theme | ✅ PASS | Single bead, single subsystem (MAP backend `_update_inbox_unsupported` latch). |

---

## Failure Detail — Criterion 3

`ruff check tincand/backends/bluez_map.py tests/tincand/test_backends.py`:

```
E501 Line too long (100 > 99)
    --> tests/tincand/test_backends.py:1016:100
     |
1015 | class TestMapBackendUpdateInboxUnsupportedFlag:
1016 |     """poll_inbox: UpdateInbox unsupported flag — set on error, skip after set, reset on connect."""
     |                                                                                                    ^
Found 1 error.
```

The docstring on `TestMapBackendUpdateInboxUnsupportedFlag` (introduced by this PR) is 100 characters; the project ruff limit is 99. Not pre-existing — `origin/main:tests/tincand/test_backends.py` passes `ruff check` clean.

**Required fix:** shorten the class docstring by one character, e.g.:

```python
    """UpdateInbox unsupported flag: set on error, skip after set, reset on connect."""
```

After the fix, re-run `ruff check tincand/ tests/` to confirm clean.

---

## Notes

- pytest 1702 passed (excluding `tests/tincand/test_mcp_server.py` which fails to import due to missing `mcp` dependency — this is pre-existing and unrelated to this PR).
- All other gate criteria pass; this is a one-line lint fix away from a full PASS.
