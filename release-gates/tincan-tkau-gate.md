# Release Gate: tincan-tkau — ANCSBackend lifecycle state machine

**Bead:** tincan-tkau  
**Feature:** ANCSBackend lifecycle state machine — CONNECTING→ACTIVE→HEALING→FALLBACK (tincan-5mze.1)  
**Review bead:** tincan-03p4 (CLOSED, PASS)  
**Commit evaluated:** dbb68bf (feat(ancs): implement ANCSBackend lifecycle state machine)  
**Main HEAD at gate time:** dbb68bf (this commit IS the tip of main)  
**Gate run:** 2026-06-02  
**Verdict:** ✅ PASS

---

## Gate Checklist

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | ✅ PASS | tincan-03p4 CLOSED with close reason: pass — "claude-reviewer verdict: PASS"; 71/71 ANCSBackend tests; no blockers |
| 2 | Acceptance criteria met | ✅ PASS | All 6 spec criteria verified in code — see detail below |
| 3 | Tests pass + lint clean | ✅ PASS | 469/469 non-live tests pass; 71/71 ANCSBackend tests pass; ruff check: All checks passed; ruff format issue pre-existing (present in HEAD~1, not introduced by dbb68bf) |
| 4 | No HIGH findings open | ✅ PASS | F1 (Low: unstored 500ms timer ID), F2 (Informational: ancs_needs_repair not cleared on reconnect); zero HIGH findings |
| 5 | Final branch is clean | ⚠️ CONDITIONAL PASS | 4 pre-existing modified tracked files on main worktree (docs/TESTING.md, tests/tincand/test_dbus_client_live.py, tincand/__main__.py, tincand/backends/mock.py); none in feature path (tincand/backends/ancs.py) |
| 6 | Branch diverges cleanly from main | N/A | Local-only repo; commit is on main |
| 7 | Single feature theme | ✅ PASS | Single commit (dbb68bf) implementing ANCSBackend lifecycle state machine in tincand/backends/ancs.py |

---

## Criterion 2 — Acceptance criteria

| AC | Status | Evidence |
|----|--------|---------|
| Double-subscribe guard in _on_device_connected | ✅ PASS | `ancs.py:329-330` — `if self._notif_src_path is not None: return` |
| 500 ms Notifying poll after StartNotify | ✅ PASS | `ancs.py:466` — `GLib.timeout_add(500, self._check_notifying_after_subscribe)` |
| 30 s health check while ACTIVE (SOURCE_CONTINUE/REMOVE pattern) | ✅ PASS | `ancs.py:525` — `self._health_check_id = GLib.timeout_add(30_000, self._health_check)`; returns `GLib.SOURCE_CONTINUE` on pass, `GLib.SOURCE_REMOVE` on fail |
| HEALING entry: set_capability(ancs, False) + cancel health check + 5 s × 3 timer | ✅ PASS | `ancs.py:545-553` — `_enter_healing` cancels health-check ID, calls `set_capability("ancs", False)`, resets `_heal_attempts=0`, arms `GLib.timeout_add(5_000, self._attempt_le_rearm)` |
| 3-attempt counter + FALLBACK after 3 | ✅ PASS | `ancs.py:564,569-571` — `_heal_attempts += 1`; `if self._heal_attempts >= 3: self._enter_fallback()` |
| FALLBACK: set_capability(ancs_needs_repair, True) | ✅ PASS | `ancs.py:578` — `self._service.set_capability("ancs_needs_repair", True)` |
| Timer hygiene in stop() | ✅ PASS | `ancs.py:279-286` — both `_health_check_id` and `_heal_timer_id` cancelled and nulled |
| Timer hygiene in _on_device_disconnected() | ✅ PASS | `ancs.py:472-477` — both IDs cancelled and nulled; `_notif_src_path`/`_data_src_path` nulled at 499-500 |

---

## Criterion 3 — Tests

```
PYTHONPATH=/home/jaword/james-claude/.local/lib/python3.14/site-packages \
  python3 -m pytest tests/ --ignore=tests/tincand/test_dbus_client_live.py -q

469 passed, 1 warning in 3.24s
```

ANCSBackend unit tests (focused run):
```
71 passed, 1 warning in 0.18s
```

Lint:
```
ruff check tincand/backends/ancs.py → All checks passed!
```

Format note: `ruff format --check` would add blank lines before class definitions and split a trailing comma — same formatting drift is present in HEAD~1, not introduced by dbb68bf. Pre-existing condition; not a blocker.

---

## Criterion 4 — Review findings

| Finding | Severity | Disposition |
|---------|----------|-------------|
| F1: Unstored 500ms timer ID (ancs.py:466) | Low | Non-blocking; edge case only on rapid disconnect+reconnect within 500ms; follow-up suggested in review |
| F2: ancs_needs_repair not cleared on reconnect | Informational | Intentional — wizard is the clearing authority; out of scope |

No HIGH or MEDIUM findings.
