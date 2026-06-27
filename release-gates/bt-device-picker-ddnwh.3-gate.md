# Release Gate: bt-device-picker-ddnwh.3 (tincan-d5yyu)

**Bead:** tincan-d5yyu  
**Branch:** feat/bt-device-picker-ddnwh.3 @ 4c643e3 (origin)  
**Gate evaluated:** 2026-06-27  

## Verdict: FAIL

**Failing criteria: #5 and #6**

### Criterion 5 — Final branch is clean: FAIL

Builder worktree is mid-rebase (`git rebase --interactive`) onto `origin/main`
(9255fc6) with an unresolved conflict in `tincan_gui/settings_dialog.py`:

```
interactive rebase in progress; onto 9255fc6
Last command done (1 command done):
   pick 0eb06bc feat(gui): Bluetooth Device picker in Settings + GetHFPDevices dbus API
Next commands to do (2 remaining):
   pick 55651be fix(lint): wrap E501 lines ...
   pick 4c643e3 fix(gui): device picker writes to tincan.ini ...
Unmerged paths:
   both modified: tincan_gui/settings_dialog.py
```

4 unresolved conflict markers remain in `tincan_gui/settings_dialog.py`
(lines 206-829). This is why ruff shows 111 lint parse errors.

### Criterion 6 — Branch diverges cleanly from main: FAIL

`git merge-tree --write-tree origin/main origin/feat/bt-device-picker-ddnwh.3`
exits 1 with conflict in `tincan_gui/settings_dialog.py`.

PR #144 merged to `origin/main` and included an EARLIER version of the BT
device picker (direct oFono D-Bus calls inline in `_DeviceLoader.run()`). This
branch's version is architecturally better (delegates to `client.get_hfp_devices()`,
adds `GetHFPDevices()` D-Bus method, uses module-level `_DEV_RE`), but conflicts
because both sides modified `settings_dialog.py` from the same pre-PR-#144 base.

## Net-new vs origin/main (valuable, not yet on main)

- `tincand/dbus_service.py`: `GetHFPDevices()` D-Bus method + `_DEV_RE` module constant
- `tincan_gui/dbus_client.py`: `get_hfp_devices()` client wrapper
- `tincan_gui/settings_dialog.py`: `_DeviceLoader` refactored to use `client.get_hfp_devices()`;
  `_devices_list` field; MAC-first label format; DaemonSettings write path improved

## Resolution

Builder should finish (or restart) the rebase of `feat/bt-device-picker-ddnwh.3`
onto `origin/main`:

**Conflict resolution guide for `tincan_gui/settings_dialog.py`:**
- Keep main's `_DeviceLoader` class signature (no constructor arg) OR keep the
  branch's `__init__(self, client)` version — but the branch version is cleaner
  since it delegates to dbus_client.get_hfp_devices(). **Keep the branch version.**
- The `_device_combo`, `_populate_device_combo`, `_on_device_changed` from main
  (added by PR #144's earlier version) need to be replaced with the branch's
  client-delegating version.
- After rebase, run tests and lint, then re-route to deployer.

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-t7ss2: PASS verdict for 4c643e3. AC1-AC5 verified; AC5 minor noted (non-blocking). |
| 2 | Acceptance criteria met | **PASS** | Branch has full AC1-AC5 implementation. |
| 3 | Tests pass | **PASS** | 2088 passed, 2 skipped, 10 xfailed on builder worktree. |
| 4 | No high-severity review findings | **PASS** | No HIGH findings from reviewer. |
| 5 | Final branch is clean | **FAIL** | Builder worktree mid-rebase; 4 unresolved conflicts in settings_dialog.py. |
| 6 | Branch diverges cleanly from main | **FAIL** | `git merge-tree` conflict in settings_dialog.py; PR #144 merged overlapping code. |
| 7 | Single feature theme | **PASS** | BT Device picker in Settings UI + GetHFPDevices daemon API — one coherent feature. |
