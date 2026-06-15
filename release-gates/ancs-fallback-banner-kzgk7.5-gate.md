# Release Gate: ANCS FALLBACK banner with Try-to-Reconnect

**Bead:** tincan-pxiev (deploy) / tincan-2fmgf (review) / tincan-kzgk7.5 (feature)  
**Feature:** feat(gui): ANCS FALLBACK banner with Try-to-Reconnect  
**Branch:** feat/ancs-fallback-banner-kzgk7.5  
**Commit:** f8e28b79a8aed134d82a3ede3f44f8d7e0d7420c  
**PR:** https://github.com/quad341/tincan/pull/128  
**Evaluated:** 2026-06-14

## Gate Results

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | ✅ PASS | tincan-2fmgf closed (close_reason: pass); reviewer verdict: all ACs met, 1920/1920 tests passed on reviewer's environment, 0 HIGH findings. |
| 2 | Acceptance criteria met | ✅ PASS | Amber palette (#fff3bf/#e67700) ✓; headline+body two-line layout, 64px min-height ✓; `set_reconnecting()` method (idle/busy button states) ✓; D-Bus heal stack `RequestANCSHeal→request_heal→_enter_healing` ✓; `showEvent` focuses button for keyboard/AT users ✓. |
| 3 | Tests pass | ✅ PASS | 1904 passed, 1 skipped, 6 xfailed (mcp module excluded — consistent with reviewer's 1920 with mcp installed). Zero regressions vs main. Run: `python -m pytest tests/ -q --ignore=tests/tincand/test_mcp_server.py` |
| 4 | No high-severity findings open | ✅ PASS | Reviewer found one INFO/LOW edge case (_on_daemon_disconnected doesn't call set_reconnecting(False) — very unlikely in practice) and one LOW lint nit (unused QPushButton import in new test file). 0 HIGH findings. |
| 5 | Final branch is clean | ✅ PASS | Branch up to date with origin/feat/ancs-fallback-banner-kzgk7.5; untracked files are tooling-only (.claude/, .codex/, .gc/, .gitkeep). |
| 6 | Branch diverges cleanly from main | ✅ PASS | 3 commits ahead of origin/main (8860622); cherry-picks cleanly — no merge conflicts. |
| 7 | Single feature theme | ✅ PASS | All 3 commits are the ANCS status/fallback UI subsystem: kzgk7.4 (status dot), kzgk7.5 (FALLBACK banner + heal stack), kzgk7.7 (widget tests for both). Tightly coupled: kzgk7.7 tests both kzgk7.4 and kzgk7.5; banner references the status dot context. One logical feature. |

## Commits on branch (ahead of main)

| SHA | Description |
|-----|-------------|
| 9331fd9 | feat(gui): ANCS status indicator dot in title bar (tincan-kzgk7.4) |
| 500571c | feat(gui): ANCS FALLBACK banner with Try-to-Reconnect (tincan-kzgk7.5) |
| f8e28b7 | test(gui): ANCSStatusDot + ANCSRepairBanner widget tests (tincan-kzgk7.7) |

## Changed files

- `tincan_gui/ancs_status_dot.py` — new: ANCSStatusDot widget (amber/green dot in title bar)
- `tincan_gui/degradation_banners.py` — modified: ANCSRepairBanner redesigned (amber palette, two-line layout, set_reconnecting(), showEvent focus)
- `tincan_gui/dbus_client.py` — modified: adds `request_ancs_heal()` D-Bus call
- `tincan_gui/main.py` — modified: wires reconnect_clicked → _on_ancs_reconnect_clicked; clears reconnecting state on repair
- `tincand/backends/ancs.py` — modified: adds RequestANCSHeal handler → _enter_healing
- `tincand/dbus_service.py` — modified: exposes RequestANCSHeal D-Bus method
- `tests/tincan_gui/test_ancs_repair_banner.py` — modified: updated for new 64px min-height, accessible name, new wiring
- `tests/tincan_gui/test_ancs_ui_kzgk7.py` — new: 381-line widget test suite for ANCSStatusDot + ANCSRepairBanner

## Overall: PASS

All 7 criteria passed. Approved for merge via PR #128.
