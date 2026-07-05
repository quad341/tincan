# Release Gate: tincand SIGTERM/SIGINT attribution + shutdown-hang fix (tincan-97mlk.6)

**Bead:** tincan-f5pbw (deploy) — source tincan-97mlk.6.2 (re-review, PASS)
**Branch:** fix/tincan-97mlk.6-signal-attribution
**HEAD commit evaluated:** 561ab2e
**Origin/main base:** confirmed via `git log origin/main..HEAD` (exactly 3 commits ahead, 0 behind)
**Gate evaluated:** 2026-07-05

## Verdict: PASS

All 7 criteria pass. Evidence below was independently re-run by the deployer, not copied from bead notes.

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-97mlk.6.2 notes: "RE-REVIEW VERDICT: PASS (tincan/reviewer)" — both prior REQUEST-CHANGES findings independently re-verified by the reviewer, including a live `os.kill()` SIGTERM check outside the mocked test suite. |
| 2 | Acceptance criteria met | **PASS** | (1) `_block_shutdown_signals()` (`pthread_sigmask(SIG_BLOCK, ...)`) is the 2nd statement in `main()`, before any `threading.Thread`/GLib internals exist, so the blocked mask is inherited process-wide; `_signal_waiter` runs `sigwaitinfo()` in a dedicated daemon thread — the only way to get `si_pid`/`si_uid` in Python. (2) `_proc_cmdline(max_len=200)` and `_describe_signal_sender(max_depth=4, max_len=1000)` bound the attribution string to ~1KB, well under the 64KB pipe-buffer size that caused the original hang. (3) `packaging/` untouched — confirmed via diffstat (see below). (4) tincan-97mlk.6.1 tests merged in commit 169aab8, 17 dedicated tests present and passing. |
| 3 | Tests pass | **PASS** | `QT_QPA_PLATFORM=offscreen python3 -m pytest tests/ -q` → **2463 passed, 1 skipped, 0 failed** (69.5s). Targeted: `pytest tests/tincand/test_main_signal_attribution.py tests/tincand/test_main.py tests/tincand/test_main_args.py -q` → **60 passed**. |
| 4 | No high-severity review findings open | **PASS** | Zero HIGH findings. One LOW/non-blocking finding noted (`_proc_cmdline` doesn't strip control chars from attribution log; requires same-UID/CAP_KILL trust boundary already assumed, single-user desktop daemon) — explicitly marked non-gating by reviewer, deployer concurs it's not a real exposure. Unrelated pre-existing flake tincan-uj2jv (`test_dbus_client_live.py`) confirmed not reproduced by this diff. |
| 5 | Final branch is clean | **PASS** | `git status` on `fix/tincan-97mlk.6-signal-attribution`: no staged/unstaged changes (only untracked `.gc/`/`.gitkeep` rig scaffolding, same as every other worktree in this repo). |
| 6 | Branch diverges cleanly from main | **PASS** | `git log origin/main..HEAD` → exactly 2d8a094/169aab8/561ab2e (3 commits), `git log HEAD..origin/main` → empty (branch is origin/main plus these 3, not stale). `git merge-tree --write-tree origin/main fix/tincan-97mlk.6-signal-attribution` → exits 0, single tree hash, no conflict markers. |
| 7 | Single feature theme | **PASS** | All 4 touched files are the signal-attribution fix + its dedicated tests: `tincand/__main__.py`, `tests/tincand/test_main_signal_attribution.py`, `tests/tincand/test_main.py`, `tests/tincand/test_main_args.py`. No independent themes. |

## Additional verification

- Diffstat vs origin/main: `tincand/__main__.py` (+120/-4), `tests/tincand/test_main_signal_attribution.py` (+228 new file), `tests/tincand/test_main.py` (+2/-1), `tests/tincand/test_main_args.py` (+1/-3) — **4 files, +346/-8**, matches builder/reviewer claim exactly.
- `ruff check tincand/__main__.py tests/tincand/test_main_signal_attribution.py tests/tincand/test_main.py tests/tincand/test_main_args.py` → 3 findings (E501 `test_main.py:343`, I001 `test_main.py:366`, E402 `__main__.py:15`). Deployer independently diffed each against `git show origin/main:<path>`: all 3 pre-exist verbatim on origin/main (line-shifted only), none introduced by this diff.
- Read the full `tincand/__main__.py` diff directly: confirmed `loop.quit()` is in a `finally` block around the attribution WARNING log in `_signal_waiter` (so shutdown completes even if logging raises — the actual bug fix for the original hang), and `_proc_ppid` uses `read_text(errors="replace")` matching `_proc_cmdline`'s existing decode-tolerance pattern.
- `packaging/systemd/tincand.service`: confirmed untouched (not in the touched-file list above); the in-process `sigwaitinfo` approach is the intended replacement for the dead-end `ExecStopPost` attribution attempt, per bead spec.
