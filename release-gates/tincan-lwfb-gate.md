# Release Gate: tincan-lwfb — MapBackend.poll_inbox folder-nav + Text-body fix

**Bead:** tincan-lwfb  
**Feature:** MapBackend.poll_inbox folder-nav + Text-body fix (tincan-4igy)  
**Review bead:** tincan-jih6 (CLOSED, PASS)  
**Commit evaluated:** fec136b (fix(map): folder-nav + Text-body in poll_inbox; fix GetMessage signature)  
**Branch:** fix/poll-inbox-folder-nav-text-body  
**Gate run:** 2026-06-03  
**Verdict:** ✅ PASS

---

## Gate Checklist

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | ✅ PASS | tincan-jih6 CLOSED, PASS — tincan/all.reviewer (2026-06-03T14:05Z); 0 HIGH findings; 1 LOW/RISK (broad exception swallow in SetFolder ascent — non-blocking, follow-up acceptable) |
| 2 | Acceptance criteria met | ✅ PASS | All 3 ACs verified in code — see detail below |
| 3 | Tests pass + lint clean | ✅ PASS | 523/526 pass; 3 pre-existing TestHealingToActive failures identical on main (TDD-red, committed fa56780, unrelated to this fix); ruff check bluez_map.py → All checks passed |
| 4 | No HIGH findings open | ✅ PASS | Zero HIGH findings in tincan-jih6; all findings LOW or INFO |
| 5 | Final branch is clean | ⚠️ CONDITIONAL PASS | 4 pre-existing modified tracked files (docs/TESTING.md, tests/tincand/test_dbus_client_live.py, tincand/__main__.py, tincand/backends/mock.py); none in feature path (tincand/backends/bluez_map.py) |
| 6 | Branch diverges cleanly from main | ✅ PASS | 1 commit ahead of main (merge-base 6ae1238); local-only repo; no merge conflict possible |
| 7 | Single feature theme | ✅ PASS | One commit (fec136b), one file (tincand/backends/bluez_map.py); fixes two tightly coupled poll_inbox bugs (folder-nav + body source) — single subsystem, single function entry point |

---

## Criterion 2 — Acceptance criteria

| AC | Status | Evidence |
|----|--------|---------|
| BUG 1 — SetFolder('telecom') + SetFolder('msg') before ListMessages('inbox', {}) | ✅ PASS | `bluez_map.py` lines 174–181: `for _ in range(2): SetFolder('')` (ascend), then `_retry(SetFolder, 'telecom')` + `_retry(SetFolder, 'msg')` before `ListMessages` |
| BUG 2 — body from Text/Subject props; no GetMessage transfer in poll path | ✅ PASS | `bluez_map.py` lines 186–191: `str(props.get('Text','')) or str(props.get('Subject','')) or 'New message'`; `_fetch_full_body` no longer called from `poll_inbox` |
| GetMessage signature fixed (3 args: handle, targetfile, filter) | ✅ PASS | `bluez_map.py` line 268: `GetMessage(msg_path, '', {'Attachment': dbus.Boolean(False)})` — empty targetfile added |

---

## Criterion 3 — Tests

```
Tests run at fec136b on fix/poll-inbox-folder-nav-text-body:
PYTHONPATH=/home/jaword/james-claude/.local/lib/python3.14/site-packages \
  python3 -m pytest tests/ --ignore=tests/tincand/test_dbus_client_live.py -q

3 failed, 523 passed, 1 warning in 3.61s
```

Failures: `TestHealingToActive::test_rearm_success_*` (3 tests) — confirmed pre-existing on `main` (same 3 failures identical on `6ae1238` main HEAD). These are intentionally-red TDD stubs from commit fa56780 (HEALING→ACTIVE rearm, SPIKE-TBD). Not introduced by fec136b.

Lint:
```
ruff check tincand/backends/bluez_map.py
→ All checks passed!
```

---

## Reviewer findings carried forward

| Finding | Severity | Disposition |
|---------|----------|-------------|
| SetFolder ascent catches all DBusException (too broad) — silent swallow on transient errors | LOW/RISK | Non-blocking; descend calls surface failures; follow-up narrowing recommended |
| test_rearm_success_calls_set_capability_ancs_true failure | INFO/PREEXISTING | Same on parent 6ae1238 — not introduced by this change |
| Coverage gap (no dedicated unit tests for folder-nav or body-fallback chain) | INFO | Covered by policy — tincan-4u26 (needs-tests) filed by builder, routed to validator |

---

Local-only repo — no PR possible. Merge authority: mayor.
