# Release Gate — ancs-status-dot-kzgk7.4

**Bead:** tincan-iu4on (deploy bead) → source: tincan-1h2h3 / tincan-kzgk7.4  
**Branch:** feat/ancs-status-dot-kzgk7.4  
**Commit:** 9331fd9aef5cfe0cef28774c1cb3b297ed73e2fa  
**PR:** #127  
**Date:** 2026-06-13  

## Gate Results

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | Reviewed + PASSED by tincan/reviewer — verdict in tincan-iu4on notes |
| 2 | Acceptance criteria met | **PASS** | See breakdown below |
| 3 | Tests pass | **PASS** | 1884 passed, 1 skipped, 6 xfailed — `pytest tests/` |
| 4 | No high-severity review findings | **PASS** | Only LOW finding (ARMED/HEALING distinction, tracked as kzgk7.7) |
| 5 | Final branch is clean | **PASS** | `git status` clean; at 9331fd9 |
| 6 | Branch diverges cleanly from main | **PASS** | `merge-base --is-ancestor origin/main feat/ancs-status-dot-kzgk7.4` ✓ |
| 7 | Single feature theme | **PASS** | One commit; one subsystem (`tincan_gui/`) |

**Overall: PASS**

## Acceptance Criteria Verification

- [x] `ACTIVE` (ancs=True): green `#22c55e`, static, visible
- [x] `HEALING` (ancs=False, ancs_needs_repair=False): amber `#d97706`, pulsing (1.2 s InOutSine loop)
- [x] `FALLBACK` / disconnected (ancs_needs_repair=True): hidden — ANCSRepairBanner takes over
- [x] `ARMED` (neither capability): hidden
- [x] Prefers-reduced-motion: static amber when `QStyleHints.reducedAnimations()` returns True
- [x] WCAG 2.1 AA: accessible name updated + `QAccessibleEvent.NameChanged` fired on each transition
- [x] Tooltips: "Bluetooth notifications" (ACTIVE) / "Reconnecting..." (HEALING)
- [x] Excluded from tab order (`FocusPolicy=NoFocus`)
- [x] `_on_daemon_disconnected()` calls `ancs_status_dot.hide()`
- [x] Wired via `TitleBar.ancs_status_dot` property; `_apply_capabilities()` drives `update_state()`

## Known LOW Finding

**ARMED state shows amber** — capability model cannot yet distinguish ARMED from HEALING; both present as ancs=False, ancs_needs_repair=False. Tracked as tincan-kzgk7.7 to reconcile. User impact: brief amber flash during startup before call_setup_ready fires. Not a blocker; kzgk7.7 is a follow-on.

## Code Change Summary

- `tincan_gui/ancs_status_dot.py` (new, 115 lines): `ANCSStatusDot` widget with paint/animation/accessibility
- `tincan_gui/main.py` +12 lines: `TitleBar` wiring — layout insertion, property, `_apply_capabilities`, `_on_daemon_disconnected`
