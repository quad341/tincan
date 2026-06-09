# Release Gate: PBAP retry for iOS approval race

**Bead:** tincan-jb5jw (deploy) ← tincan-3b34a (review) — supersedes prior gates (tincan-8qd3b, tincan-wyqoc, tincan-tn0rq, tincan-31q7r, tincan-mwbov, tincan-b4kig)
**Branch:** fix/pbap-0-contacts-retry-uhwfo
**Tip commit:** dd840cf
**Date:** 2026-06-09
**Evaluator:** tincan/deployer

---

## Gate Results

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-3b34a: "REVIEW VERDICT: PASS" from tincan/reviewer (Claude Sonnet 4.6) on commit 91d020f; lint clean, no OWASP findings, retry logic bounds correct, contacts_empty guard correct, None-iface guard correct, 7 §7 unit tests cover all branches |
| 2 | Acceptance criteria met | **PASS** | Bug: 0 contacts on PBAP connect after iOS Sync Contacts re-approval. Fix: `_retry_pullall()` — 5 s countdown, max 3 retries, `contacts_empty=True` on exhaustion, `contacts_empty=False` cleared when retry window opens. 7 new §7 tests cover all retry paths |
| 3 | Tests pass | **PASS** | `pytest tests/ --ignore=tests/tincand/test_mcp_server.py`: **1673 passed, 6 skipped, 6 xfailed** (run on dd840cf; MCP import error is pre-existing, unrelated) |
| 4 | No high-severity review findings open | **PASS** | Reviewer: no HIGH/CRITICAL/OWASP findings. F1 tmp-file leak pre-existing non-blocking; F2 stale-timer edge case advisory; F3 informational — all LOW |
| 5 | Final branch is clean | **PASS** | `git status`: nothing to commit, working tree clean |
| 6 | Branch diverges cleanly from main | **PASS** | 10 commits ahead, 0 behind origin/main; no merge conflicts |
| 7 | Single feature theme | **PASS** | All commits touch one subsystem (PBAP backend + its tests): `tincand/backends/pbap.py`, `tests/tincand/test_pbap_select.py` |

**Overall: PASS — PR #103 open; route merge-request to mayor**

---

## Commits on branch (vs main)

```
dd840cf  chore: release gate PASS for pbap-0-contacts-retry-uhwfo (tincan-8qd3b, tip 91d020f)
91d020f  chore: release gate PASS for pbap-0-contacts-retry-uhwfo (tincan-wyqoc, tip f5e3095)
f5e3095  chore: release gate PASS for pbap-0-contacts-retry-uhwfo (tincan-tn0rq, tip 76ff7fc)
76ff7fc  chore: release gate PASS for pbap-0-contacts-retry-uhwfo (tincan-31q7r, tip a5c7554)
a5c7554  chore: release gate PASS for pbap-0-contacts-retry-uhwfo (mwbov, tip 03320cd)
03320cd  chore: release gate PASS for pbap-0-contacts-retry-uhwfo (b4kig, tip 8df50c3)
8df50c3  fix(pbap): clear stale contacts_empty flag during retry window
410b321  chore: release gate PASS for pbap-0-contacts-retry-uhwfo
e020376  test(pbap): add §7 retry countdown tests for iOS approval-race recovery
65d1c18  fix(pbap): retry PullAll on 0-contact result for iOS approval race (tincan-uhwfo)
```

## Files changed vs main

```
release-gates/pbap-0-contacts-retry-uhwfo-gate.md |  48 +++++++++++++
tests/tincand/test_pbap_select.py                  |  80 +++++++++++++++++++++--
tincand/backends/pbap.py                           |  56 ++++++++++++++++
3 files changed, 180 insertions(+), 4 deletions(-)
```
