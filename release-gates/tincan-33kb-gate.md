# Release Gate: tincan-33kb — BackendManager for concurrent MAP+ANCS

**Bead:** tincan-33kb (deploy bead)
**Feature:** feat(daemon): BackendManager for concurrent MAP+ANCS in one process
**Source bead / review:** tincan-dtvm (CLOSED, PASS)
**Spec bead:** tincan-9k36
**Commit evaluated:** ce9f2b2 (cherry-picked as 72d3dc5 on tincan-33kb off origin/main)
**Gate run:** 2026-06-04
**Verdict:** ✅ PASS

---

## Gate Checklist

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | ✅ PASS | tincan-dtvm CLOSED with reviewer PASS; confirmed in ss-11495 |
| 2 | Acceptance criteria met | ✅ PASS | BackendManager delegates messaging to primary; secondaries share TincanService; connect/disconnect order correct; `--with-ancs` flag added (see below) |
| 3 | Tests pass | ✅ PASS | 740/740 pass, 1 warning on tincan-33kb branch |
| 4 | No HIGH findings open | ✅ PASS | 0 HIGH; needs-tests bead tincan-voor filed for lifecycle coverage (non-blocking) |
| 5 | Final branch clean | ✅ PASS | `git status` clean |
| 6 | Branch diverges cleanly from main | ✅ PASS | Cherry-pick onto origin/main applied cleanly (new files, no conflicts) |
| 7 | Single feature theme | ✅ PASS | New BackendManager abstraction + CLI flag; 2 files (new module + __main__.py) in one subsystem |

---

## Criterion 2 — Acceptance Criteria

From tincan-9k36: BackendManager(primary, secondaries) — delegates poll_inbox/send_message/get_message to primary; starts/stops secondaries alongside primary; secondaries use set_capability() on shared TincanService directly. Disconnect order: secondaries reversed then primary. CLI: `--with-ancs` flag wraps MapBackend + ANCSBackend when `--backend map`.

| AC | Status | Evidence |
|----|--------|---------|
| BackendManager delegates to primary | ✅ PASS | `backend_manager.py` — `poll_inbox`, `send_message`, `get_message` proxy to `self._primary` |
| Secondaries start/stop with primary | ✅ PASS | `start()` starts primary then each secondary; `stop()` stops secondaries (reversed) then primary |
| Secondary failures isolated | ✅ PASS | Reviewer confirmed: "Secondary failures isolated" in PASS verdict |
| `--with-ancs` CLI flag | ✅ PASS | `__main__.py` — `--with-ancs` arg wraps MapBackend + ANCSBackend in BackendManager when `--backend map` |

---

## Criterion 3 — Tests

```
python3 -m pytest tests/ --tb=short -q --ignore=tests/tincand/test_dbus_client_live.py

740 passed, 1 warning in 3.94s
```

Ruff: all checks passed.
