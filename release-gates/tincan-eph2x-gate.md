# Release Gate: deduplicate outbound echoes (tincan-eph2x)

**Bead:** tincan-y92t3 (deploy) → tincan-eph2x (source fix)
**Branch:** fix/tincan-eph2x
**Commit:** 574c0b7 (cherry-picked from 6295399 on fix/tincan-zlg3k)
**Date:** 2026-06-07

## Gate Criteria

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | Reviewer mail from tincan/reviewer: "Review PASS: deduplicate outbound echoes (tincan-eph2x)". Bead notes: "Reviewed + PASSED by reviewer (tincan/reviewer). Evidence: 4 regression tests PASS, §8 TestNoDuplicateAfterReload PASS, full GUI suite 858/858 PASS, lint clean, no security concerns." |
| 2 | Acceptance criteria met | **PASS** | All done-when criteria satisfied (see below) |
| 3 | Tests pass | **PASS** | 858/858 tests pass: `QT_QPA_PLATFORM=offscreen pytest tests/tincan_gui -q` |
| 4 | No high-severity review findings open | **PASS** | One LOW finding: body-only cache dedup over-applies to re-sends (non-blocking, follow-up bead recommended). No HIGH or MEDIUM findings. |
| 5 | Final branch is clean | **PASS** | `git status` clean (only untracked gc worktree artifacts: .claude/, .codex/, .gc/, .gitkeep) |
| 6 | Branch diverges cleanly from main | **PASS** | Cherry-pick 6295399 → 574c0b7 applied without conflict. Branch is 1 commit ahead of origin/main. |
| 7 | Single feature theme | **PASS** | Commit touches only `tincan_gui/main.py`, `tincan_gui/message_cache.py`, `tests/tincan_gui/test_repro_lcnyu.py` — all GUI dedup logic for the same fix. |

**Overall: PASS**

## Acceptance Criteria Detail (tincan-eph2x done-when)

- [x] `tests/tincan_gui/test_repro_lcnyu.py` — all 4 tests pass (divergent dup, matching control, accumulation, intentional-resend preserved): **858 total / 0 failures**
- [x] Existing §8 `TestNoDuplicateAfterReload` still passes: **confirmed (0 failures)**
- [x] Full GUI suite green (`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/tincan_gui -q`): **858 passed, 1 warning in 5.33s**
- [x] `ruff check tincan_gui` — 3 pre-existing errors in `degradation_banners.py`, `settings_dialog.py`, `thread_view.py`; identical on origin/main; **none introduced by this commit**

## Commit Summary

Files changed by 574c0b7:
- `tests/tincan_gui/test_repro_lcnyu.py` — new file: 4 regression tests for divergent-timestamp dedup
- `tincan_gui/main.py` — `_within_window` + `_collapse_outbound_echoes` helpers; applied on `_load_thread_messages` and `_on_conversation_selected` display paths; outbound echo persist guard in `_on_message_received`
- `tincan_gui/message_cache.py` — body-only dedup for outbound writes in `add_message`
