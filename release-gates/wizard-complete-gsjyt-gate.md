# Release Gate: wizard complete — DetectBadge, AdapterCapabilityPage, CallsSetupPanel

**Bead:** tincan-gsjyt  
**Branch:** builder/tincan-wizard-complete  
**Tip commit:** 91a5f5985b6a7f974d84fb522a1f2028892f0d5e  
**Reviewed at:** 3f4746a70e833534868fad0c8752184ef490964b  
**Gate date:** 2026-06-29  

## Criteria

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-562ga closed with reason `pass`; verdict `pass` in notes; commit 3f4746a explicitly reviewed |
| 2 | Acceptance criteria met | **PASS** | Reviewer verified: `_ANCS_PARTIAL_REASONS` frozenset correct, `accept_partial(ancs=False)` → SuccessPage wiring correct, `SuccessPage.setup_calls_btn` → `CallsSetupPanel.exec()` correct, `main.py._open_calls_setup_panel` re-fetches capabilities on close, `preflight_calls` path wired end-to-end |
| 3 | Tests pass | **PASS** | 2353 passed, 1 skipped, 9 xfailed, 0 failures (67s); includes 88 new behavioral tests: `test_pairing_wizard_aom60.py` (37), `test_pairing_wizard_4ktha.py` (28), `test_calls_setup_panel_lqj89.py` (23), `test_calls_setup_panel_ud49h.py` |
| 4 | No high-severity review findings open | **PASS** | Reviewer noted 0 security issues; 1 low-priority style note (non-blocking cross-module import). Pre-existing `degradation_banners.py` ruff errors confirmed pre-exist on `origin/main`, not introduced by branch. |
| 5 | Final branch is clean | **PASS** | `git status` shows only untracked `.gc/` and worktree artifacts; no uncommitted code changes |
| 6 | Branch diverges cleanly from main | **PASS** | `git merge-tree origin/main builder/tincan-wizard-complete` → 0 conflicts |
| 7 | Single feature theme | **PASS** | All commits extend the pairing wizard UI (DetectBadge, AdapterCapabilityPage, accept_partial) and the tightly-coupled CallsSetupPanel dialog launched from SuccessPage. Cannot be shipped independently: CallsSetupPanel entry point lives in wizard SuccessPage. |

## Files changed vs main

```
tincan_gui/pairing_wizard.py        (+284/-229 lines) — wizard completion
tincan_gui/calls_setup_panel.py     (new)             — calls setup dialog
tincan_gui/main.py                  (+11/-1)           — entry point wiring
tincan_gui/degradation_banners.py   (+15/-?)           — CallSetupRequiredBanner
tincand/pairing.py                  (+4/-0)            — pairing state
tests/tincan_gui/test_pairing_wizard_aom60.py  (new, 37 tests)
tests/tincan_gui/test_pairing_wizard_4ktha.py  (pre-existing — noted in tests run)
tests/tincan_gui/test_calls_setup_panel_lqj89.py (new, 23 tests)
tests/tincan_gui/test_calls_setup_panel_ud49h.py (new)
release-gates/wizard-failure-reasons-4ktha-gate.md (prior deploy gate, no-conflict)
```

## Test run summary

```
2353 passed, 1 skipped, 9 xfailed, 1 warning in 67.13s (0:01:07)
```

## Lint

- `calls_setup_panel.py` — ruff clean ✓
- `main.py` — ruff clean ✓
- `pairing_wizard.py` — ruff clean ✓
- `tincand/pairing.py` — ruff clean ✓
- `degradation_banners.py` — 2 pre-existing errors (I001, F401) confirmed on `origin/main`; not introduced by this branch

## Verdict: PASS
