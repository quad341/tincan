# Release Gate: hfp-adapter-modem-3vc85 (tincan-pqjct)

**Deploy bead:** tincan-pqjct  
**Feature branch:** feat/hfp-adapter-aware-modem-selection-3vc85  
**Gate commit:** baf552b  
**Evaluated:** 2026-06-24 by tincan/deployer

---

## Gate Results

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-h4ena CLOSED with pass verdict for baf552b; all blockers resolved |
| 2 | Acceptance criteria met | **PASS** | See table below |
| 3 | Tests pass | **PASS** | 1982 passed, 1 skipped, 6 xfailed (mcp module absent — expected) |
| 4 | No high-severity review findings open | **PASS** | Review notes: no security concerns, no OWASP findings; all findings LOW or BLOCKER (resolved) |
| 5 | Final branch is clean | **PASS** | `git status` in builder worktree: only untracked agent files (.claude/, .codex/, .gc/) — no uncommitted code changes |
| 6 | Branch diverges cleanly from main | **PASS** | `git merge-tree` shows no conflicts; PR #136 (fix/hcin-adapter-hzcfj.1) is open but diverges independently — no overlap conflicts with this branch |
| 7 | Single feature theme | **PASS** | All 4 commits on this branch (9b38c6e FR1-FR5, c1f1f21 FR6, 4014afa VCM fixes, baf552b tests+guard) are cohesive parts of adapter-aware HFP modem selection. Removing any one leaves the others incomplete. |

---

## Acceptance Criteria (bead tincan-pqjct)

| Item | Criterion | Result |
|------|-----------|--------|
| §7 TestCancelVcmSubscriptions | 4 behavioral tests for rebind and modem-removed paths | **PASS** — 4 tests: rebind removes prior matches, rebind adds new, modem-removed cancels, modem-removed ignores non-bound |
| R1 log fix | is_preferred computed before rebind log guard; no double-log | **PASS** — commit moves `is_preferred` assignment before the guard and logs only when `not is_preferred` |
| 5tojh mac guard | `_is_hfp_iphone_modem` returns False for empty `_mac_fragment` | **PASS** — early return on empty fragment prevents vacuous `startswith("")` match |
| 5tojh routing guard | `setup_sco_routing` defensive guard + WARNING log | **PASS** — empty mac guard added with WARNING log in call_audio.py |
| test_false_when_mac_fragment_empty | Regression test for kf2h0 vacuous-match bug | **PASS** — test present in test_call_controller.py |

---

## Project Manifest Release Criteria

| Criterion | Result | Notes |
|-----------|--------|-------|
| Automated tests pass | **PASS** | 1982/1989 collected pass (1 error: mcp absent, expected; 6 xfail) |
| Lint/format clean (ruff) | **PASS** | `ruff check tincand/call_audio.py tincand/call_controller.py tests/tincand/test_call_controller.py` — All checks passed. 54 pre-existing errors in unrelated files (predate this PR). |
| No hardcoded iOS-version assumptions | **PASS** | MAC fragment detection is runtime behavior; no iOS version strings introduced |
| LIMITATIONS.md updated if needed | **N/A** | This PR does not change what the platform can/cannot do; LIMITATIONS.md remains accurate |
| Onboarding unaffected | **PASS** | No changes to onboarding flows |

---

## Branch Commits

| SHA | Message |
|-----|---------|
| 9b38c6e | fix(calls): adapter-aware HFP modem selection with deferred Online bind (tincan-3vc85) |
| c1f1f21 | fix(calls): proactive SetProperty Powered=true on preferred Offline modem (tincan-odlh9) |
| 4014afa | fix(calls): VCM signal leak, re-bind log, log polish (tincan-8o1pj, tincan-5jeeu, tincan-eld4u) |
| baf552b | test(calls): VCM subscription cleanup tests + empty mac guard (tincan-czxfo, tincan-5tojh) |

---

## Overall: PASS
