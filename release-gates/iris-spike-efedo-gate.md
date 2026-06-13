# Release Gate: Iris voice agent spike (tincan-43oaj)

**Bead:** tincan-43oaj (deploy bead for tincan-efedo + tincan-bbpih.1 + tincan-9i2ux)
**Branch:** feature/tincan-efedo  
**Tip commit:** 16fde5b6635bd656c7e96a9aed4c3d775f2aa929  
**PR:** #123 https://github.com/quad341/tincan/pull/123  
**Gate evaluated:** 2026-06-13

---

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-y6y9l closed PASS by tincan/reviewer (2026-06-13): "17/17 unit tests pass. Security clean. Spec compliance verified." No HIGH findings (reviewer found LOW stale comment + INFO items only). |
| 2 | Acceptance criteria met | **PASS ⚠ LIVE-GATED** | All code-verifiable criteria pass (prereq ✓/✗ output with install commands, session summary, all design requirements from tincan-efedo). Hardware-gated criteria (live HFP call, disclosure timing, 2-way latency, Ctrl-C, DEGRADED mode) not verifiable in deployer seat — see LIVE TEST GATE below. |
| 3 | Tests pass | **PASS** | 17/17 spike tests pass locally; full suite 1884 passed, 1 skipped, 6 xfailed, 0 errors. CI GREEN at 2026-06-13T21:43:58Z (run 27479970446). |
| 4 | No high-severity findings | **PASS** | Reviewer found: [LOW] stale comment in test file (guard description outdated); [INFO] security clean; [INFO] t_tts_first_audio approximation documented. Zero HIGH or BLOCKER findings. |
| 5 | Final branch is clean | **PASS** | `git status` shows only untracked agent/infra dirs (.claude/, .codex/, .gc/, .gemini/). No staged or tracked-modified files. |
| 6 | Branch diverges cleanly from main | **PASS** | feature/tincan-efedo is 7 commits ahead, 0 behind origin/main (8860622). No merge conflicts. |
| 7 | Single feature theme | **PASS** | All 5 changed files relate to the Iris voice agent spike: `spikes/iris_spike.py`, `tests/spikes/__init__.py`, `tests/spikes/conftest.py`, `tests/spikes/test_iris_spike.py`, `release-gates/tincan-cyqnm-gate.md` (sub-bead gate included in PR). One subsystem, one logical feature. |

## Verdict: PASS

## ⚠ LIVE TEST GATE — merge authority must verify before merging

PR test plan items 3–7 require a live active HFP call and cannot be verified
in the deployer seat. The reviewer and builder both noted this explicitly.

**Mayor/mpr: confirm operator (Jim) ran the following before merging PR #123:**

- [ ] `ANTHROPIC_API_KEY=... python spikes/iris_spike.py --device-mac D0:6B:78:33:46:20` during active HFP call on Malala
- [ ] Far end hears disclosure (Iris introduction) within 2s of script start
- [ ] 2-way conversation: far end speaks → Iris replies ≤ 1500ms p90 (check EERL output)
- [ ] Ctrl-C exits cleanly without disrupting the call
- [ ] DEGRADED mode: "get Jim" or API failure → recovery line spoken, process stays alive

If any live test fails, reopen tincan-43oaj and route back to builder with findings.

## Minor notes (not blockers)

- **Ruff in test files**: 4 minor violations in `tests/spikes/` (I001 × 2, E501 × 1, F401 × 1). CI ruff is `continue-on-error: true`; not a gate blocker. Main spike file `spikes/iris_spike.py` is ruff-clean.
- **Stale comment**: `test_iris_spike.py:963-966` NOTE block says guard "will FAIL until corrected" but it was corrected in tincan-bbpih.1. LOW finding from reviewer; comment is misleading but test passes correctly.

## Changed files

| File | Change | Purpose |
|------|--------|---------|
| `spikes/iris_spike.py` | +1073 lines | Iris voice agent pipeline implementation |
| `tests/spikes/__init__.py` | +0 (new empty) | pytest package marker |
| `tests/spikes/conftest.py` | +5 lines | sys.path setup for spike import |
| `tests/spikes/test_iris_spike.py` | +1000 lines | 17 unit tests (5 groups) |
| `release-gates/tincan-cyqnm-gate.md` | +37 lines | Gate for empty-STT fix (tincan-bbpih.1, sub-bead) |
