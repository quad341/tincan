# Release Gate: tincan-wc8r

**Feature:** 4 QA bug fixes + ANCS healing (tincan-6ok1 / tincan-5mze / tincan-9388 / tincan-xbxe / tincan-v3oq)
**Deploy bead:** tincan-doqd (source review bead: tincan-wc8r)
**Commit:** f5fc878 on main
**Gate run:** 2026-06-03
**Result:** PASS

## Gate Checklist

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | PASS | tincan-wc8r closed with `Review verdict: PASS`; reviewer tincan/all.reviewer; 0 HIGH findings |
| 2 | Acceptance criteria met | PASS | See detail below |
| 3 | Tests pass | PASS | 700 pass, 1 warning in 27.65s (full suite on current main) |
| 4 | No HIGH findings open | PASS | 0 HIGH; one MEDIUM (ANCS health-check restart) filed as follow-up tincan-ixc1 — non-blocking |
| 5 | Final branch clean | PASS | `git status` shows only untracked infra files (.beads/, .gc/, etc.) |
| 6 | Branch diverges cleanly from main | N/A | Commit f5fc878 is already on main; no separate feature branch |
| 7 | Single feature theme | PASS | 5 related QA bug fixes in the message send/receive pipeline — tightly coupled, not independent features |

## Criterion 2 — Acceptance Criteria

### tincan-6ok1 (P1): phone-originated sent messages not mirrored

- ✅ `ContactStore.lookup_by_name()` reverse name→phone lookup present (`tincand/contact_store.py:62`)
- ✅ `TincanService._resolve_to_phone()` 3-step resolution (normalize → ContactStore → conv scan) present (`tincand/dbus_service.py`)
- ✅ `update_contact()` merges name-keyed convs into phone-keyed slot on PBAP sync
- ✅ GUI reloads conversation list on `CapabilityChanged('contacts', True)`

### tincan-5mze (§20): ANCS HEALING→ACTIVE rearm success detection

- ✅ `_attempt_le_rearm()` detects Notifying=True externally restored; transitions back to ACTIVE (`tincand/backends/ancs.py:592-611`)
- ✅ 3 TDD tests in `tests/tincand/` all pass (128 tests in modified test files pass)

### tincan-9388 (P1): 4s GUI freeze on Enter

- ✅ `_SendWorker(QObject)` class with `QThread` runs blocking SendMessage off the UI thread (`tincan_gui/main.py:125`)
- ✅ Optimistic outbound bubble rendered immediately; `_pending_sends` dedup prevents duplicate echo

### tincan-xbxe (P2): error bar visual glitch

- ✅ `setMinimumHeight(32)` used on `_error_bar` (replacing `setFixedHeight`) in `tincan_gui/compose_panel.py:92`
- ✅ `setWordWrap(True)` on error text label

### tincan-v3oq (P2): hardcoded real phone in tests (PII/security fix)

- ✅ Real phone number replaced with `TINCAN_TEST_NUMBER` env var (default `+15550101234` fictional NANP) in:
  - `tests/tincand/test_map_send.py:36`
  - `tests/tincand/test_pbap.py:40`
  - `tests/tincand/test_bluez_map.py` (references to +15550101234)

## Criterion 3 — Test Run

```
python -m pytest tests/ --tb=no -q
700 passed, 1 warning in 27.65s
```

## Criterion 3 — Lint

`ruff check` on files modified by f5fc878 (`tincan_gui/main.py` as of f5fc878, before subsequent 731bafd):
```
All checks passed!
```

Pre-existing ruff errors in unmodified files (test_backends.py, test_compose_panel.py, test_avatar.py, etc.)
are not introduced by f5fc878 — the long-line error in current `tincan_gui/main.py:58` was introduced
by the subsequent commit 731bafd (HiDPI icon work).

## Release Criteria (PROJECT_MANIFEST.md)

| # | Criterion | Result | Notes |
|---|-----------|--------|-------|
| 1 | Phase definition-of-done met | PASS | 5 P1/P2 send-flow bugs fixed |
| 2 | Automated tests pass | PASS | 700 pass |
| 3 | Lint/format clean | PASS | f5fc878 files clean; pre-existing errors in unmodified files |
| 4 | No hardcoded iOS-version/model assumptions | PASS | None introduced |
| 5 | LIMITATIONS.md updated if needed | N/A | Bug fix, no new limitations |
| 6 | Onboarding still surfaces requirements | N/A | No onboarding changes |
