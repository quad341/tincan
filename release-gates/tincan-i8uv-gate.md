# Release Gate: tincan-i8uv — ANCSRepairBanner + FALLBACK notification + tray glyph

**Bead:** tincan-i8uv  
**Feature:** ANCSRepairBanner + FALLBACK notification + tray glyph (tincan-5mze.2/5mze.5)  
**Review bead:** tincan-4b6v (CLOSED, PASS)  
**Commit evaluated:** c0b9d6d (feat(ui): ANCSRepairBanner + FALLBACK notification + tray glyph)  
**Gate point:** c0b9d6d — gated here; fa56780 is on top on main (adds intentionally-red TDD §20 tests for HEALING→ACTIVE rearm, SPIKE-TBD, per fa56780 commit message)  
**Gate run:** 2026-06-03  
**Verdict:** ✅ PASS

---

## Gate Checklist

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | ✅ PASS | tincan-4b6v CLOSED, PASS — all functional requirements met; 0 HIGH findings; 1 LOW/STYLE (missing ⚠ symbol in banner text — cosmetic, non-blocking) |
| 2 | Acceptance criteria met | ✅ PASS | All 10 spec ACs verified in code — see detail below |
| 3 | Tests pass + lint clean | ✅ PASS | 469/469 non-live tests pass at c0b9d6d; ruff check: All checks passed (5 changed files) |
| 4 | No HIGH findings open | ✅ PASS | Zero HIGH findings in tincan-4b6v; all findings LOW or INFO |
| 5 | Final branch is clean | ⚠️ CONDITIONAL PASS | 4 pre-existing modified tracked files (docs/TESTING.md, tests/tincand/test_dbus_client_live.py, tincand/__main__.py, tincand/backends/mock.py); none in feature path |
| 6 | Branch diverges cleanly from main | N/A | Local-only repo; commit is on main |
| 7 | Single feature theme | ✅ PASS | Single commit (c0b9d6d) implements ANCSRepairBanner, FALLBACK notification, and tray glyph — all part of one user-facing ANCS degradation surface (tincan-5mze.2/5mze.5) |

---

## Criterion 2 — Acceptance criteria

| AC | Status | Evidence |
|----|--------|---------|
| `ancs_needs_repair` in `_KNOWN_CAPABILITIES` and `_capabilities` init | ✅ PASS | `dbus_service.py:142` — `frozenset({…, "ancs_needs_repair"})`; `dbus_service.py:69` — `"ancs_needs_repair": False` in init dict; `dbus_service.py:105` — same in Disconnect() reset |
| `ANCSRepairBanner(QWidget)` — h=56, #fff7ed bg, #f97316 border | ✅ PASS | `degradation_banners.py:115` — `setFixedHeight(56)`; `degradation_banners.py:117` — `background-color: #fff7ed; border: 1px solid #f97316` |
| Reconnect button with `reconnect_clicked` Signal | ✅ PASS | `degradation_banners.py:105` — `reconnect_clicked = Signal()`; `degradation_banners.py:141` — `reconnect_btn.clicked.connect(self.reconnect_clicked)` |
| `AlertMessage` accessible role via factory | ✅ PASS | `degradation_banners.py:204,206` — `if isinstance(obj, ANCSRepairBanner): return QAccessibleWidget(obj, QAccessible.Role.AlertMessage)` |
| No dismiss — banner persists until `ancs_needs_repair` clears | ✅ PASS | `degradation_banners.py:102-145` — no dismiss button or close mechanism; `main.py:246-258` — only hides when `needs_repair=False` |
| Banner inserted between StateB and StateC in `_build()` | ✅ PASS | `main.py:153-154` — `self._banner_ancs_repair = ANCSRepairBanner()` inserted between State B and C |
| `reconnect_clicked` → `_open_pairing_wizard` in `_wire()` | ✅ PASS | `main.py:206` — `self._banner_ancs_repair.reconnect_clicked.connect(self._open_pairing_wizard)` |
| Mutual exclusivity: StateC hidden when `ancs_needs_repair=True` | ✅ PASS | `main.py:267` — `show_c = not ancs_ok and not ancs_needs_repair` |
| FALLBACK notification: rate-limited, timeout=0, Reconnect+Dismiss actions | ✅ PASS | `main.py:252-253` — `_repair_notified` flag; `notifications.py:109` — `dbus.Int32(0)` timeout; `notifications.py:103-106` — actions array with Reconnect.../Dismiss |
| Tray `!` glyph + tooltip override on `set_repair_needed(True)` | ✅ PASS | `tray.py:39-55` — `_make_icon` draws `!` glyph when `repair_needed=True`; `tray.py:171-172` — icon and tooltip updated in `_update()` |

---

## Criterion 3 — Tests

```
Tests run at c0b9d6d (gate point):
PYTHONPATH=/home/jaword/james-claude/.local/lib/python3.14/site-packages \
  python3 -m pytest tests/ --ignore=tests/tincand/test_dbus_client_live.py -q

469 passed, 1 warning in 4.24s
```

GUI tests (focused, 270 tests at gate point): all pass.
dbus_service tests (28 tests): all pass.

Note on main HEAD (fa56780): 3 additional failures in `TestHealingToActive` —
intentionally-red TDD tests for the HEALING→ACTIVE rearm success path (§20),
explicitly marked TDD red in the fa56780 commit message. Not regressions from
c0b9d6d; these tests did not exist at the gate point.

Lint:
```
ruff check tincan_gui/degradation_banners.py tincan_gui/main.py \
           tincan_gui/notifications.py tincan_gui/tray.py tincand/dbus_service.py
→ All checks passed!
```

---

## Reviewer findings carried forward

| Finding | Severity | Disposition |
|---------|----------|-------------|
| Banner text missing ⚠ symbol (spec: `⚠ iPhone notifications unavailable — …`) | LOW/STYLE | Not blocking; cosmetic deviation; follow-up bead recommended by reviewer |
| `notifications.py:94` — redundant fallback `SessionBus()` retry | INFO | Benign; exception-guarded; no functional impact |
| Coverage gap (no new unit tests for banner visibility/rate-limiting/tray) | INFO | Covered by policy — tincan-5mze.4 needs-tests bead filed |

---

Local-only repo — no PR possible. Merge authority: mayor.
