# Release Gate: tincan-ps152 — MAP notification fix

**Bead:** tincan-g0ow1 (deploy) ← tincan-2ts7p (review) ← tincan-ps152 (feature)  
**Branch:** feature/tincan-ps152  
**Commit:** c86f4a7 (cherry-picked from 27acc24 on docs/bt-headset-relay-limitation)  
**Date:** 2026-06-06  
**Evaluator:** tincan/all.deployer

---

## Gate Checklist

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | ✅ PASS | tincan-2ts7p closed reason=pass; notes: "REVIEW VERDICT: PASS" — reviewer tincan/all.reviewer, all dimensions (Correctness/Style/Security/Tests) PASS |
| 2 | Acceptance criteria met | ✅ PASS | Criterion: "every incoming message notifies, respecting focus/visibility rules." Fix adds `is_new=True` for all `notify=True` inbound messages in `_emit_messages`. Double-gated on notify flag + direction=='inbound'. Outbound and baseline-poll (notify=False) messages cannot trigger false positives. |
| 3 | Tests pass | ✅ PASS | `QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q` → **1205 passed**, 0 failed, 1 unrelated PyGI deprecation warning, 30.32s |
| 4 | No high-severity review findings open | ✅ PASS | Review notes: Correctness PASS, Style PASS, Security PASS, Tests PASS. Zero HIGH findings. Test-gap bead tincan-vlxtb filed as follow-up (non-blocking). |
| 5 | Final branch is clean | ✅ PASS | `git status`: no uncommitted changes; untracked files are infra-only (.codex/, .gc/, .gitkeep) |
| 6 | Branch diverges cleanly from main | ✅ PASS | 1 commit ahead of origin/main; clean cherry-pick, no conflicts |
| 7 | Single feature theme | ✅ PASS | 1 file changed: `tincand/backends/bluez_map.py` (+3/-1). One theme: fix notification dropout for iOS-auto-read inbound messages |

## Project Release Criteria (PROJECT_MANIFEST.md)

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| RC-1 | Phase DoD met | ✅ PASS | Phase-1 DoD: "hold a real SMS conversation reliably." Notification dropout after first message was load-bearing for this; fix is directly on the critical path. |
| RC-2 | All automated tests pass | ✅ PASS | 1205 passed (see criterion 3 above) |
| RC-3 | Lint/format clean | ✅ PASS | `ruff check tincand/ tincan_gui/` → all checks passed. black not installed; ruff covers formatting rules. |
| RC-4 | No hardcoded iOS-version assumptions | ✅ PASS | Fix uses protocol semantics (`msg['read']`, `notify` flag, `direction`) — no version guards, no model checks |
| RC-5 | LIMITATIONS.md updated if needed | ✅ N/A | This fix closes a bug; it does not change what the platform can/cannot do. No LIMITATIONS.md update required. |
| RC-6 | Onboarding surfaces Show Notifications + reconnect | ✅ PASS | Onboarding code not touched by this change |

## Verdict: **PASS**

All 7 gate criteria and all 6 project release criteria pass. Proceeding to push and PR.
