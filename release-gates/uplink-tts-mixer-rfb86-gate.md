# Release Gate: uplink TTS mixer — null-sink (mic + iris_tts) → bluez_output

**Bead:** tincan-jxkn7 (deploy) · source: tincan-rfb86 (build) · review: tincan-hveiz  
**Branch:** `builder/tincan-rfb86`  
**Gate commit:** da425e8  
**Date:** 2026-06-28  

## Gate Checklist

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-hveiz reviewer verdict PASS @ da425e8 (2026-06-29T00:05Z); ruff blocker resolved; security OWASP PASS; spec compliance PASS |
| 2 | Acceptance criteria met | **PASS** | See per-criterion breakdown below |
| 3 | Tests pass | **PASS** | 41/41 unit tests pass (test_uplink_mixer.py + test_apply_barge_in_frame.py); full suite 2145 passed, 2 skipped, 10 xfailed, 0 failures |
| 4 | No high-severity findings open | **PASS** | 0 open HIGH findings; one coverage observation (timing-race guards not unit-tested) logged as informational, not a blocker |
| 5 | Final branch is clean | **PASS** | `git status` clean on builder/tincan-rfb86 @ da425e8; no uncommitted changes |
| 6 | Branch diverges cleanly from main | **PASS** | `git merge-tree --write-tree origin/main builder/tincan-rfb86` exit 0; no conflicts; main moved to 336c246 (bmstd) since branch base f1dd8ed; both call_audio.py edits integrate cleanly |
| 7 | Single feature theme | **PASS** | All 7 commits target the calls/audio subsystem (tincand/call_audio.py + tests); one coherent primitive: PipeWire null-sink uplink mixer for TTS |

**Verdict: PASS**

---

## Acceptance Criteria — Per-Criterion

From tincan-rfb86:

| Criterion | Status | Notes |
|-----------|--------|-------|
| Mixer: null-sink/loopback `(mic + iris_tts) → bluez_output` via `setup_uplink_mixer` | PASS | Implemented: `setup_uplink_mixer` loads a null-sink module, wires mic→sink and sink-monitor→bluez_output via `pw-link`; returns `UplinkMixerCtx` |
| Barge-in: operator mic wins, iris yields immediately | PASS | `BargeInController` (RMS threshold + hangover) + `apply_barge_in_frame` mutes/unmutes TTS pw-links on transition |
| TTS wiring deferred; `SPEAK_DURING_CALL` unchanged | PASS | `connect_tts_to_uplink` API present but not auto-invoked; `SPEAK_DURING_CALL` remains False in codebase |
| Graph-level only — no PipeWire re-patching | PASS | All wiring via `pw-link` / `pactl load-module module-null-sink`; no profile forcing, no PipeWire patch |
| Teardown on hangup | PASS | `teardown_uplink_mixer` disconnects all links and unloads the null-sink module |
| Hardware: far party hears iris on live SCO call | **PENDING (post-merge)** | Factory determination: live hardware smoke test is post-merge operator validation (BLOCKER-2). Not a gate blocker per reviewer verdict and deploy bead notes. |

---

## Test Run Summary

```
platform linux -- Python 3.14.0b3
collected 41 items (targeted) / 2157 items (full suite)

tests/tincand/test_uplink_mixer.py     27 passed
tests/tincand/test_apply_barge_in_frame.py  14 passed
Full suite: 2145 passed, 2 skipped, 10 xfailed, 0 failed (36.99s)
```

Ruff lint: `All checks passed!` on tincand/call_audio.py, test_uplink_mixer.py, test_apply_barge_in_frame.py

---

## Commit History

| SHA | Message |
|-----|---------|
| da425e8 | fix(tests): remove unused pytest import and sort imports in test_apply_barge_in_frame |
| dcd4787 | fix(calls): add PipeWire timing hint to setup_uplink_mixer null-sink port warnings |
| 0a8fdb1 | test(calls): apply_barge_in_frame actuator coverage (tincan-c8ttg) |
| 4592f7e | fix(calls): add apply_barge_in_frame — barge-in actuator for TTS pw-links |
| 6bd9b0e | style(tests): drop unused imports from test_uplink_mixer (ruff F401) |
| 781644a | feat(calls): uplink TTS mixer — null-sink: (mic + iris_tts) → bluez_output |
| 9264db1 | test(calls): red — uplink TTS mixer (tincan-rfb86) |
