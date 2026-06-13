# Release Gate: Iris spike empty-STT guard fix (tincan-cyqnm)

**Bead:** tincan-cyqnm  
**Fix bead:** tincan-bbpih.1  
**Branch:** fix/tincan-bbpih.1-empty-stt-guard → feature/tincan-efedo  
**Merge commit:** 9dc0e0bef225d63f1aca4d16175b0cf93862b1d6  
**PR:** https://github.com/quad341/tincan/pull/124 (MERGED)  
**Gate evaluated at:** origin/feature/tincan-efedo @ 9dc0e0b  
**Date:** 2026-06-13

---

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-vnlny closed PASS by tincan/reviewer (2026-06-13): "17/17 spike tests pass including previously-failing test_hello_makes_llm_call, ruff clean, no regressions, no security concerns" |
| 2 | Acceptance criteria met | **PASS** | `test_hello_makes_llm_call` PASSES — 'hello' (5 chars, 1 word) now correctly goes to LLM; empty string and 2-char words still filtered; all 17 EmptySTTGuard boundary tests green |
| 3 | Tests pass | **PASS** | 17/17 spike tests pass; full suite 1901 passed, 1 skipped, 6 xfailed — zero regressions |
| 4 | No high-severity findings | **PASS** | Reviewer: "pure string manipulation, no injection risk, no external I/O in changed lines" |
| 5 | Final branch clean | **PASS** | Only untracked agent/infra files (.claude/, .gc/, etc.); no staged or tracked-modified files |
| 6 | Branch diverges cleanly from base | **PASS** | PR #124 fast-forward merged; feature/tincan-efedo is ahead of main by 5 commits, no conflicts |
| 7 | Single feature theme | **PASS** | One-line bug fix in `spikes/iris_spike.py` — word count → char count guard; single subsystem, single file |

## Verdict: PASS

## Fix summary

`_iris_loop` was guarding against empty STT with `len(words) <= 2` (word count),
which incorrectly treated "hello" (1 word) as noise and skipped the LLM call.
Spec requires a **non-whitespace character count ≤ 2** so that single-letter
stutters and punctuation are filtered while real one-word utterances pass through.
Fix: `len(transcript.strip().replace(' ', '')) <= 2`.

## Notes

PR #124 was merged by the operator (Jim) directly. Gate evaluation is retroactive
confirmation of the merge. No new PR or merge-request action required.
