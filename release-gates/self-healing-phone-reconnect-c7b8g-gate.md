# Release Gate: self-healing phone reconnect fix

**Bead:** tincan-6obam (deploy) / tincan-c7b8g (fix) / tincan-5wa67 (review)
**Branch:** rebase/tincan-c7b8g (rebased by builder after the prior FAIL; supersedes the stale `builder/tincan-c7b8g`)
**Fix commit:** ea12aada1d64446ff612d3ba1d6fb246e792e752
**Merge-base / parent:** c892a199c19a482895cbdb9e62d19bd0f63a9dd3 (= `origin/main` tip at gate time)
**Gate date:** 2026-07-05
**Prior cycle:** FAIL on criterion 6 (2026-07-04, three deployer sessions) — see git history of this file on `deploy/tincan-c7b8g` for the original evidence. Builder rebased onto current `origin/main` (`c892a19`, through `#172`/`#173`/`#174`) to resolve it; this gate re-verifies all 7 criteria from scratch on the new commit, not just criterion 6.

## Criteria

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-5wa67 closed reason `pass`; notes contain `REVIEWER VERDICT: PASS (tincan/reviewer, 2026-07-04)`. Review was against the pre-rebase commit (3e5ddb7); content is unchanged by the rebase (diffstat identical, see criterion 2), so the verdict still applies to `ea12aad`. |
| 2 | Acceptance criteria met | **PASS** | Diffed `ea12aad` directly against its parent `c892a19` and re-confirmed all 3 gaps from tincan-c7b8g: (1) `call_controller.py` `_schedule_retry()` falls back to `_RETRY_STEADY_STATE_S=30.0` indefinite polling once the 5-step fast backoff is exhausted, instead of idling permanently; (2) `dbus_service.py` adds `_bt_connect_device()`, called from `Connect()`, driving a real `org.bluez.Device1.Connect()` dispatched via `reply_handler`/`error_handler` (confirmed async, not blocking); (3) new `call_link_ready` capability wired True/False from `_bind_modem()`/`_on_modem_removed()`/`Disconnect()`, added to `_KNOWN_CAPABILITIES`, distinct from the SELinux-scoped `call_setup_ready` per tincan-r41sx. Diffstat unchanged from the original review: 81 insertions / 6 deletions across the same 2 files. |
| 3 | Tests pass | **PASS** | Independently re-ran on `ea12aad` in a clean detached-HEAD checkout: full suite `2416 passed, 1 skipped, 0 failed` in 56.08s (count is up from the previously-reported 2376 because `origin/main` gained tests via `#172`/`#174` in the interim — not a regression). `test_dbus_client_live.py` (live subprocess regression test for the sync-blocking-hang risk): `9 passed` in 26.69s, no hang — confirms the async `Device1.Connect()` dispatch still holds post-rebase. |
| 4 | No high-severity review findings open | **PASS** | Reviewer notes: "No blocking findings. PASS." No HIGH/CRITICAL items raised. One pre-existing `F401` (unused `os` import, `dbus_service.py:16`) reconfirmed via `git blame` (introduced in `bc70e5f`, 2026-06-05) and via `ruff check` on `origin/main` tip itself — predates this fix, not introduced by it, not gated in CI. |
| 5 | Final branch is clean | **PASS** | `git status` on the isolated `ea12aad` checkout shows no uncommitted changes (only pre-existing untracked worktree scaffolding `.gc/`, `.gitkeep`, unrelated to this bead). |
| 6 | Branch diverges cleanly from main | **PASS** (previously FAIL) | `git merge-base ea12aad origin/main` = `c892a199c19a482895cbdb9e62d19bd0f63a9dd3`, which is exactly `origin/main`'s current tip — `ea12aad`'s direct parent **is** `origin/main` HEAD. This is a linear fast-forward, not merely a conflict-free merge: zero divergence, zero risk of the `call_link_ready`/`call_audio_aec` collision recurring. Builder's rebase (continuing a prior in-progress rebase at `c06677a` through main's subsequent `#174`) resolved 3 conflicts total (`tincan_gui/degradation_banners.py`, `tincan_gui/settings_dialog.py`, `tincand/__main__.py`); `tincand/dbus_service.py` itself auto-merged cleanly with zero conflict markers, confirmed both `call_link_ready` and `call_audio_aec` present at all 3 original collision points (capability dict init, `Disconnect()` reset, `_KNOWN_CAPABILITIES` frozenset). |
| 7 | Single feature theme | **PASS** | Commit set touches exactly two files (`tincand/call_controller.py`, `tincand/dbus_service.py`), both in the `tincand` call/dbus subsystem, all three changes serve one theme (self-healing phone reconnect). Unchanged from the original review. |

## Files changed (this bead's commit)

```
tincand/call_controller.py  (+27/-4)  — indefinite steady-state modem retry re-arm
tincand/dbus_service.py     (+60/-2)  — real async BT Device1.Connect(); call_link_ready capability
```

## Test run summary

```
2416 passed, 1 skipped, 19 warnings in 56.08s   (full suite, isolated fix commit ea12aad)
9 passed, 1 warning in 26.69s                    (test_dbus_client_live.py, live regression)
```

## Lint

- `tincand/call_controller.py` — ruff clean
- `tincand/dbus_service.py` — one pre-existing `F401` (unused `os` import, line 16), predates this commit (`bc70e5f`, 2026-06-05), not gated in CI

## Verdict: PASS (all 7 criteria)

Proceeding to push + PR. Merge authority is mayor/mpr — this bead does not merge.
