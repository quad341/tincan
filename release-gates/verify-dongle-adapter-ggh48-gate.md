# Release Gate: verify_dongle_adapter adapter-index check (tincan-ggh48)

**Bead:** tincan-ggh48  
**Feature branch:** `fix/verify-dongle-adapter-ggh48`  
**Gate commit:** 4acc985  
**Gate date:** 2026-06-26  
**Deployer:** tincan/deployer

## Verdict: PASS

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-hni2a notes: "REVIEW VERDICT: PASS" by tincan/reviewer (claude-sonnet-4-6). No blocking findings. |
| 2 | Acceptance criteria met | **PASS** | `_DONGLE_ADAPTER_FRAGMENT` removed; `verify_dongle_adapter` now checks `/{adapter_hci}/` path component. Empty `adapter_hci` returns True (graceful skip). Tests updated to cover corrected contract. |
| 3 | Tests pass | **PASS** | `python -m pytest` — 2102 passed, 2 skipped, 10 xfailed (39s). 13 call_audio tests all green. |
| 4 | No high-severity findings | **PASS** | Review noted one style nit (warning message redundancy) — explicitly marked non-blocking. No HIGH findings. |
| 5 | Final branch clean | **PASS** | `git status` shows no uncommitted tracked changes (untracked: .claude/, .codex/, .gemini/, docs/plans/, worktrees/ — all pre-existing dev artifacts). |
| 6 | Branch diverges cleanly from main | **PASS** | `git merge-tree` shows 0 conflicts with `origin/main`. |
| 7 | Single feature theme | **PASS** | Single bug fix: one function in `tincand/call_audio.py` + corresponding test update. One logical change. |

## Change summary

**Files changed (2):**
- `tincand/call_audio.py` — removed `_DONGLE_ADAPTER_FRAGMENT` constant; rewrote `verify_dongle_adapter` to check `/{adapter_hci}/` path component instead of MAC substring; empty `adapter_hci` skips verification and returns True
- `tests/tincand/test_call_audio.py` — updated 5 test cases to cover new contract (adapter-index match, mismatch, empty adapter_hci, warning presence/absence)

## Root cause (from bead)

BlueZ HFP modem paths use adapter index (`hci1`), not adapter MAC (`a0_ad_9f_7a_15_8e`). The old substring match always failed, producing a spurious "not on RTL8761B dongle" warning even when the modem was correctly on the dongle adapter.
