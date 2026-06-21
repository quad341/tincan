# Release Gate: call-controller-device-mac-i4sqk (tincan-trmu4)

**Branch:** `fix/call-controller-device-mac-i4sqk`  
**HEAD commit:** `3029df4`  
**Bead:** tincan-trmu4 (source: tincan-ogrfo)  
**Date:** 2026-06-19

## Gate Criteria

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-ogrfo: PASS verdict from tincan--reviewer (2026-06-19). PII remediated, style clean, spec verified. |
| 2 | Acceptance criteria met | **PASS** | `_IPHONE_MAC_FRAGMENT = "d0_6b_78_33_46_20"` removed from `call_controller.py`. `self._mac_fragment` now derived at runtime from `device_addr` param (`addr.lower().replace(':','_')`). `__main__.py` passes `args.device or TINCAN_DEVICE`. Test helper updated with `device_addr` param (default `"D0:6B:78:33:46:20"` for fixture compatibility). |
| 3 | Tests pass | **PASS** | 1989 passed, 1 skipped, 6 xfailed, 1 warning — 37.06s (full suite on builder worktree) |
| 4 | No HIGH findings open | **PASS** | 0 HIGH findings. 1 LOW finding (follow-up filed as tincan-kf2h0): `device_addr=""` → `_mac_fragment=""` → `_is_hfp_iphone_modem` matches any HFP modem path. Not reachable in practice (requires no `--device` and active oFono HFP modems). |
| 5 | Final branch is clean | **PASS** | No tracked changes uncommitted. Untracked: `.claude/`, `.codex/`, `.gc/`, `.gitkeep` (builder meta, not code). |
| 6 | Branch diverges cleanly from main | **PASS** | `git merge-base --is-ancestor origin/main 3029df4` → true. Single commit on top of d90e8ac (main). |
| 7 | Single feature theme | **PASS** | Single focused security fix: removes hardcoded personal MAC from source; one commit touching `call_controller.py`, `__main__.py`, test helper. |

## Overall: PASS
