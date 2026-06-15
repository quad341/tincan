# Release Gate: HFP call-audio auto-configure

**Bead:** tincan-y42ld (deploy) / tincan-1usl7 (review) / tincan-zmpml (feature)  
**Feature:** feat(calls): auto-configure HFP call-audio path on call active  
**Branch:** feat/hfp-auto-audio-zmpml  
**Commit:** 1483291e71925c26160e04a5e8c440608a0b5bd4  
**PR:** https://github.com/quad341/tincan/pull/121  
**Evaluated:** 2026-06-12

## Gate Results

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | ✅ PASS | tincan-1usl7 closed (close_reason: pass); final reviewer verdict after builder revision: all findings resolved. Original request-changes (B1 missing tests, N1/N2/N3 style) fully addressed at commit 1483291. |
| 2 | Acceptance criteria met | ✅ PASS | "place/answer a call → 2-way audio, zero manual pw-link/volume" — hardware smoke confirmed: Malala iPhone via RTL8761B (hci1), outbound call, 2-way audio observed, 2 SCO pw-link connections, oFono volume=100, zero manual steps. |
| 3 | Tests pass | ✅ PASS | 1899 passed, 1 skipped, 6 xfailed — includes 15 new tests in tests/tincand/test_call_audio.py (verify_dongle_adapter × 7, verify_usb_autosuspend_off × 8). Zero regressions vs main. |
| 4 | No high-severity findings open | ✅ PASS | B1 (missing behavioral test evidence) resolved with 15 unit tests + hardware smoke. N1/N2/N3 non-blockers addressed. 0 HIGH findings remain open. |
| 5 | Final branch is clean | ✅ PASS | 2 commits ahead of origin/main; untracked files are tooling-only (.claude/, .codex/, .gc/, .gitkeep) |
| 6 | Branch diverges cleanly from main | ✅ PASS | Adds tincand/call_audio.py, modifies tincand/call_controller.py, adds tests/tincand/test_call_audio.py; no conflicts with origin/main |
| 7 | Single feature theme | ✅ PASS | All 3 changed files are the HFP call-audio auto-configuration feature (new module, integration into call controller, unit tests). No independent themes. |

## New files
- `tincand/call_audio.py` — verify_dongle_adapter, verify_usb_autosuspend_off, set_ofono_call_volume, setup_sco_routing, teardown_sco_routing
- `tests/tincand/test_call_audio.py` — 15 unit tests, monkeypatched sysfs isolation

## Modified files
- `tincand/call_controller.py` — verifies adapter at modem bind; triggers audio setup on call active via GLib.timeout_add; tears down on hangup/removed

## Overall: PASS

All 7 criteria passed. Approved for merge via PR #121.
