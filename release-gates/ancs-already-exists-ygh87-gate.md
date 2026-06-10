# Release Gate: ANCS AlreadyExists fix (tincan-ygh87)

**Bead:** tincan-cdg30 (deploy) ← tincan-ne5g0 (review) ← tincan-ygh87 (bug)
**Branch:** `fix/ancs-already-exists-ygh87`
**Head commit:** `4889adcd86751b5e68bd6f35da2dcaf1f0c62bdf`
**PR:** https://github.com/quad341/tincan/pull/118
**Gate evaluated:** 2026-06-10

---

## Criteria

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | maintainer-pr-review verdict: `fix-merge` (Claude + Codex pass; Qwen unavailable). Maintainer added `test_already_exists_proceeds_to_discovery`, re-ran suite, posted PASS. Review comment: https://github.com/quad341/tincan/pull/118#issuecomment-4674625639 |
| 2 | Acceptance criteria met | **PASS** | `tincand/backends/ancs.py`: `Pair()` raising `AlreadyExists` now logs and falls through to GATT discovery instead of calling `set_capability("ancs", False)` and returning. Non-`AlreadyExists` errors still abort (unchanged behavior). `_check_notifying_after_subscribe` HEALING path handles the case where no LE ACL is live. |
| 3 | Tests pass | **PASS** | `pytest tests/ --ignore=tests/tincand/test_mcp_server.py`: **1690 passed, 6 skipped, 6 xfailed** (test_mcp_server.py excluded: `mcp` module not installed in gate env, pre-existing). ANCS suite: **141 passed**. |
| 4 | No high-severity review findings open | **PASS** | 0 open HIGH findings. The only finding (missing test coverage for the new AlreadyExists branch) was resolved in commit `4889adc` before gate evaluation. |
| 5 | Final branch is clean | **PASS** | `git status` on `fix/ancs-already-exists-ygh87` is clean; no uncommitted changes. |
| 6 | Branch diverges cleanly from main | **PASS** | `git merge --no-commit --no-ff origin/main` → "Already up to date." No conflicts. |
| 7 | Single feature theme | **PASS** | Files changed vs main: `tincand/backends/ancs.py`, `tests/tincand/test_ancs_backend.py`. Single subsystem (ANCS backend), single bug fix. |

---

## Verdict: PASS

All 7 criteria pass. PR #118 is open and ready for merge.
