# Release Gate: proactive BT connect + oFono reconnect (tincan-vva7d)

**Bead:** tincan-vva7d (source) / tincan-wg724 (deploy)  
**Review bead:** tincan-otbzm (PASS)  
**Branch:** builder/tincan-vva7d @ a5734b0  
**Gate evaluated:** 2026-06-28 (deployer)

## Verdict: PASS

All 7 criteria pass.

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-otbzm closed with RE-REVIEW VERDICT: PASS (2026-06-28). Initial REQUEST-CHANGES (stale branch + L2 _calls access) resolved by builder; re-reviewed and confirmed PASS at a5734b0. |
| 2 | Acceptance criteria met | **PASS** | (1) `_bt_connect()` called proactively in `connect()` before CreateSession — brings up BT Classic ACL link without manual phone action. (2) `_arm_device_watcher()` subscribes to oFono ModemAdded — triggers `backend.connect(mac)` when HFP modem appears, covering the phone-offline-at-startup case. (3) No daemon restart needed: watcher runs in GLib main loop, bounded by `_MAX_AUTO_RECONNECTS=5`. |
| 3 | Tests pass | **PASS** | 2114 passed, 2 skipped, 10 xfailed (deployer run on builder/tincan-vva7d @ a5734b0). Zero regressions vs origin/main. Lint: E402 in `__main__.py` is pre-existing on origin/main (line 14 `from gi.repository import GLib`) — not introduced by this branch. No new lint errors on changed files (backend_manager.py, bluez_map.py). |
| 4 | No high-severity review findings | **PASS** | No HIGH findings. LOW findings: L1 (no unit tests for oFono watcher — defensible: requires D-Bus signal injection mock) and L2 (_calls private access — resolved in a5734b0 via public `get_calls()` duck-typing). Security: MAC extracted from trusted oFono D-Bus path via anchored regex `_DEV_MAC_RE`. No injection vectors. |
| 5 | Final branch is clean | **PASS** | `git status` on a5734b0: only untracked rig artifacts (.gc/, .claude/, .gitkeep). No uncommitted changes in tracked files. |
| 6 | Branch diverges cleanly from main | **PASS** | `git merge-tree --write-tree origin/main HEAD` → SHA 71b98079, exit 0. Branch rebased onto origin/main (9255fc6) by builder after reviewer flagged stale base. |
| 7 | Single feature theme | **PASS** | All 3 changed files serve one theme: daemon proactive BT connection + event-driven oFono reconnect. `bluez_map.py` adds `_bt_connect()` call + `is_connected`; `backend_manager.py` delegates `is_connected`; `__main__.py` adds `_arm_device_watcher()`. Independent split would not make sense — they are one feature. |

## Branch diff summary (vs origin/main)

- `tincand/backends/bluez_map.py`: `is_connected` property (`_session_path is not None`); `_bt_connect()` called proactively in `connect()` before CreateSession
- `tincand/backend_manager.py`: `is_connected` property delegating to primary backend via `getattr`
- `tincand/__main__.py`: `_arm_device_watcher()` — subscribes to oFono Manager.ModemAdded, extracts MAC via `_mac_from_ofono_path`, guards: `is_connected`, active-calls check via public `get_calls()`, bounded by `_MAX_AUTO_RECONNECTS=5`; wired into `main()` after backend/service setup

## Merge-order note

a200987 (async-load tests for tincan-133i9) is on LOCAL main but NOT on origin/main (9255fc6). If PR #152 (bmstd) merges to origin before this PR is merged, a rebase onto the updated origin/main will be required to avoid a test-file conflict. Mayor/mpr should be aware of this ordering constraint.
