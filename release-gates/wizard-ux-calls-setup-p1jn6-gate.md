# Release Gate: wizard UX + calls setup foundation (tincan-p1jn6)

**Bead:** tincan-p1jn6  
**Branch:** builder/tincan-p1jn6  
**HEAD:** c7896b7 (cherry-picked from builder/tincan-vva7d @ 197d456)  
**Date:** 2026-06-29  
**Deployer:** deployer-gm-4xaua

## Gate Result: PASS

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | reviewer-gm-eyn1a reviewed tincan-x1px4, closed with reason=pass (2026-06-29) |
| 2 | Acceptance criteria met | **PASS** | All 4 ACs verified by code inspection (see below) |
| 3 | Tests pass | **PASS** | 2324 passed, 1 skipped, 9 xfailed, 0 failures in 68.48s |
| 4 | No high-severity findings open | **PASS** | 3 findings in review bead, all [Low] / non-blocking |
| 5 | Final branch clean | **PASS** | `git status` clean; 5 cherry-picked commits, no uncommitted changes |
| 6 | Branch diverges cleanly from main | **PASS** | Cherry-picks onto origin/main applied with no conflicts; auto-merges on ancs.py, dbus_client.py, dbus_service.py resolved cleanly |
| 7 | Single feature theme | **PASS** | wizard UX hardening (aom60.x) and calls preflight (lqj89.x) are tightly coupled: the detect-badge widget surfaces preflight results; neither ships usefully without the other |

## Acceptance Criteria

### aom60.1 — ANCS failure reason constants
- `FailureReason.ANCS_EXT_ADV_BUG` and `FailureReason.ANCS_EXPERIMENTAL_REQUIRED` added to `tincand/pairing.py`
- `PairingOrchestrator._on_adv_error` dispatches 0x0d→`ANCS_EXT_ADV_BUG`, NotSupported→`ANCS_EXPERIMENTAL_REQUIRED`, fallthrough→`ADVERTISING_FAILED`
- GUI files NOT touched ✓

### aom60.2 — _DetectBadge widget
- `_DetectBadge(QLabel)` in `tincan_gui/pairing_wizard.py` with 4 modes (AUTO/PENDING/IOS/DONE) ✓
- Correct colors, fixedHeight 22px, SizePolicy.Fixed; accessible names on AUTO and IOS modes ✓

### aom60.5 — OnboardingWizard deleted
- `tincan_gui/onboarding.py` deleted ✓
- `git grep 'OnboardingWizard'` returns empty ✓

### lqj89.1 — calls preflight D-Bus method
- `tincand/setup_preflight.py` created with `SetupPreflightChecker.check_calls()` ✓
- `Preflight(a{sv}→a{sv})` D-Bus method on IFACE_DAEMON in `tincand/dbus_service.py` ✓
- `TincandClient.preflight_calls(callback)` in `tincan_gui/dbus_client.py` uses asyncCallWithArgumentList (non-blocking) ✓

## Review Findings (non-blocking)

| Severity | Bead | Finding |
|----------|------|---------|
| Low | aom60.1 | Duplicate adv-error dispatch logic between `ANCSBackend._classify_adv_error` and `PairingOrchestrator._on_adv_error` — two maintenance sites |
| Low | lqj89.1 | `setup_preflight.py:36-48`: WirePlumber D-Bus check for `Active` property is dead code (WP doesn't expose it); falls through to correct file-existence fallback |
| Low | lqj89.1 | `setup_preflight.py:53`: `os.environ.get('ACTUAL_HOME', '/home/jaword')` hardcodes operator home as fallback — portability risk if ever packaged |

Test beads aom60.6 and lqj89.4 are filed and open (acceptable per reviewer criterion (b)).

## Commits

| SHA | Message |
|-----|---------|
| 8aea279 | feat(pairing): ANCS failure reason constants and error-code dispatch (tincan-aom60.1) |
| f168104 | chore(wizard): delete OnboardingWizard and remove all imports (tincan-aom60.5) |
| b8eb1b3 | feat(wizard): _DetectBadge widget — per-page detect_mode chip (tincan-aom60.2) |
| 431e2dd | feat(dbus): preflight_calls — wrap Preflight(calls_check=True) D-Bus call (tincan-lqj89.1) |
| c7896b7 | feat(dbus): add Preflight D-Bus method and preflight_calls GUI client (tincan-lqj89.1) |
