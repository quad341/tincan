# Plan: Wizard UX + Calls Setup Panel (tincan-aom60 + tincan-lqj89)

**PM:** tincan/pm  
**Date:** 2026-06-29  
**Design source:** tincan/designer (handoff 2026-06-29)  
**Parent beads:** tincan-aom60, tincan-lqj89

---

## Overview

Two design beads have been completed by the designer and decomposed into 10 implementation beads:

- **tincan-aom60** (6 beads) — PairingWizard UX overhaul: detection badges, adapter capability page, new failure reasons, partial success path, OnboardingWizard removal
- **tincan-lqj89** (4 beads) — CallsSetupPanel: new QDialog with 4-step calls prerequisites, D-Bus integration, entry point wiring

---

## tincan-aom60: Wizard UX

### Dependency Graph

```
aom60.1 (backend: ANCS failure reasons) ──────┐
aom60.2 (_DetectBadge widget) ────────────────┤──→ aom60.3 (_AdapterCapabilityPage)
                                              └──→ aom60.4 (failure page updates)
aom60.1 ──────────────────────────────────────┘
aom60.5 (delete OnboardingWizard) — independent
aom60.1,2,3,4,5 → aom60.6 (tests)
```

### Beads

| Bead | Title | Route | Ready? |
|------|-------|-------|--------|
| tincan-aom60.1 | feat(pairing): ANCS failure reason constants and error-code dispatch | builder | ✓ unblocked |
| tincan-aom60.2 | feat(wizard): _DetectBadge widget — per-page detect_mode chip | builder | ✓ unblocked |
| tincan-aom60.3 | feat(wizard): _AdapterCapabilityPage with _AdapterCard (step 1) | builder | blocked by .1, .2 |
| tincan-aom60.4 | feat(wizard): failure page updates — new reasons, partial success path, iOS copy | builder | blocked by .1 |
| tincan-aom60.5 | chore(wizard): delete OnboardingWizard and remove all imports | builder | ✓ unblocked |
| tincan-aom60.6 | test(wizard): pytest-qt behavioral acceptance | validator | blocked by .1–.5 |

### Key Design Decisions

- `_DetectBadge` is a shared widget used by both aom60 wizard pages AND lqj89 CallsSetupPanel
- Two new `FailureReason` constants map to specific BlueZ error codes (0x0d → EXT_ADV_BUG, NotSupported → EXPERIMENTAL_REQUIRED)
- Both ANCS failure reasons get a "Continue without notifications" secondary button — user is not blocked from using tincan
- `SuccessPage.set_partial(ancs=False)` shows ⚠ warning row instead of ✓ for notifications when ANCS failed but user chose to continue
- `OnboardingWizard` deletion is independent and can be parallelized with other aom60 work

---

## tincan-lqj89: Calls Setup Panel

### Dependency Graph

```
lqj89.1 (D-Bus preflight_calls) ──┐
aom60.2 (_DetectBadge) ───────────┤──→ lqj89.2 (CallsSetupPanel core) ──→ lqj89.3 (entry points)
lqj89.1,2,3 → lqj89.4 (tests)
```

### Beads

| Bead | Title | Route | Ready? |
|------|-------|-------|--------|
| tincan-lqj89.1 | feat(dbus): preflight_calls — wrap Preflight(calls_check=True) | builder | ✓ unblocked |
| tincan-lqj89.2 | feat(gui): CallsSetupPanel — 4-step calls prerequisites QDialog | builder | blocked by lqj89.1, aom60.2 |
| tincan-lqj89.3 | feat(gui): CallsSetupPanel entry points — SuccessPage + CallSetupRequiredBanner | builder | blocked by lqj89.2 |
| tincan-lqj89.4 | test(calls): pytest-qt behavioral acceptance | validator | blocked by lqj89.1–3 |

### Key Design Decisions

- `CallsSetupPanel` is a `QDialog` (not a wizard page) — opt-in, re-enterable, opens from both SuccessPage and CallSetupRequiredBanner
- Step visual order is **B, A, C, D** (WirePlumber before oFono) to mirror required setup sequence
- Step A shows an inline ordering warning when Step B (WirePlumber) is not yet configured
- `selinux_hfp_module` returns the string `"permissive"` (not bool) when SELinux is in Permissive mode — GUI shows neutral ℹ copy
- Step D is conditional on `adapter_vid_pid == "0b05:1bf6"` (RTL8761B); shows N/A for all other adapters

---

## Parallelizable work (immediately unblocked)

The following 4 beads have no blocking dependencies and can start in parallel:

1. `tincan-aom60.1` — ANCS failure reason constants (builder)
2. `tincan-aom60.2` — _DetectBadge widget (builder)  
3. `tincan-aom60.5` — Delete OnboardingWizard (builder)
4. `tincan-lqj89.1` — D-Bus preflight_calls (builder)

After aom60.2 lands: lqj89.2 unblocks alongside aom60.3 (both need _DetectBadge).
After aom60.1 lands: aom60.3 and aom60.4 unblock.
