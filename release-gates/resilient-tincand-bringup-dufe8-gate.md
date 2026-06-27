# Release Gate: resilient-tincand-bringup-dufe8 (tincan-aw7oy)

**Bead:** tincan-aw7oy  
**Source beads:** tincan-dufe8 (daemon), tincan-5y8km.2 (AdapterMismatchBanner GUI), tincan-ddnwh.3 (BT device picker)  
**Branch:** feat/resilient-tincand-bringup-dufe8 @ bde4213  
**PR:** #144  
**Gate evaluated:** 2026-06-27  

## Verdict: PASS

All 7 criteria met. PR #144 is open; merge-request routed to mayor.

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-sa03y: "## Reviewer Verdict: PASS" for bde4213 on feat/resilient-tincand-bringup-dufe8. Reviewer confirmed E501 fixed in tincand/__main__.py; no new security issues; needs-tests bead tincan-17bsu filed for remaining test gaps per validator-dod.md option (b). |
| 2 | Acceptance criteria met | **PASS** | FR-1: `Restart=always` + `StartLimitIntervalSec=0` + watchdog service. FR-2: `call_controller._bind_modem()` → `set_adapter_warning()` → `GetStatus()`. FR-3: `_resolve_device_address()` 4-step chain. FR-4: BT device picker writes `bluetooth/device_address` to tincan.ini. AdapterMismatchBanner ACs 1-7 met (colors, 5s poll, hide/show). BT device picker ACs 1-6 met. See AC detail below. |
| 3 | Tests pass | **PASS** | 2104 passed, 2 skipped, 10 xfailed (`pytest tests/tincand/ tests/tincan_gui/`) |
| 4 | No high-severity review findings | **PASS** | Reviewer findings: [LOW] main.py:747 dead state; [LOW] degradation_banners.py:465 setText; [LOW] up.py:112-115 start/absent conflated. Remaining E501 at settings_dialog.py:277/283 (painter.drawText — pre-existing on main, shifted line numbers from reviewer's :235/:241), main.py:969 (comment, LOW), settings_dialog.py:737 (comment, LOW), hfp_capability.py:62 (file unchanged by this branch, pre-existing). No HIGH findings. |
| 5 | Final branch is clean | **PASS** | `git status` clean — only untracked agent artifacts (.claude/, .codex/, .gemini/, worktrees/, docs/plans/). Working tree has no staged or unstaged changes to tracked files. |
| 6 | Branch diverges cleanly from main | **PASS** | `git merge-base origin/main HEAD` = f1dd8ed. No conflicts. 12 files changed, 430 insertions, 22 deletions vs origin/main. |
| 7 | Single feature theme | **PASS** | Three beads are tightly coupled through the daemon adapter_warning/device_discovered API. Banner consumes adapter_warning from GetStatus; device picker writes device_address for daemon auto-discovery. All form one coherent "device setup and resilience" lifecycle. Original gate at 39919dc (261d15c) PASSED same scope; reviewer did not flag bundling. |

## Acceptance Criteria Detail

### tincan-dufe8 (Resilient daemon bring-up)
- **FR-1** PASS: `tincand.service` has `Restart=always`, `StartLimitIntervalSec=0` (removes "administratively deactivated" limit), `RestartSec=5`. `tincand-watchdog.service` + `.timer` provide belt-and-suspenders start via want-down sentinel.
- **FR-2** PASS: `call_controller._bind_modem()` calls `verify_dongle_adapter()` → `service.set_adapter_warning(warn)` on mismatch, `set_adapter_warning("")` on OK. Surfaced in `GetStatus()` as `adapter_warning(s)`.
- **FR-3** PASS: `_resolve_device_address()` implements 4-step priority: `--device` CLI → `TINCAN_DEVICE` env → `DaemonSettings bluetooth/device_address` → oFono HFP GetModems() auto-discovery.
- **FR-4** PASS: Settings BT device picker writes `bluetooth/device_address = <MAC>` to tincan.ini via `DaemonSettings.setValue()`; auto-discover clears the key.

### tincan-5y8km.2 (AdapterMismatchBanner)
- **AC1** PASS: `AdapterMismatchBanner` in `degradation_banners.py:432`, wired at `main.py:560`.
- **AC2** PASS: Non-dismissible `QFrame` — no close button.
- **AC3** PASS: `update_warning(text)` calls `_label.setText(text)`.
- **AC4** PASS: `degradation_banners.py:443` background `#fff3bf`, border `#f59f00`; icon+label both `#7c4f00`.
- **AC5** PASS: `main.py:741-746` — `update_warning("")` hides + stops timer; non-empty shows + starts 5s timer.
- **AC6** PASS: `settings_dialog.py` `_refresh_adapter_mismatch_annotation()` shows `⚠ (wanted: hciX)` on the Adapter status row.
- **AC7** PASS: `main.py:685` `setInterval(5000)` (5s poll). Timer starts on warning set, stops on clear.

### tincan-ddnwh.3 (BT device picker)
- **AC1** PASS: 'Bluetooth Device' row added to settings dialog.
- **AC2** PASS: Picker sources from oFono HFP modems (not BlueZ), via `_DeviceLoader`.
- **AC3** PASS: Default auto-discover when `bluetooth/device_address` absent from tincan.ini.
- **AC4** PASS: Pinning writes `bluetooth/device_address` (`settings_dialog.py:968`).
- **AC5** PASS: Auto-discover radio clears the key.
- **AC6** PASS: Save/Cancel via existing settings dialog buttons.

## Commits in PR #144

- 258e2b9 feat(tincand): resilient bring-up — watchdog, device auto-discovery, adapter_warning (tincan-dufe8)
- 27d64b4 feat(gui): AdapterMismatchBanner — persistent amber warning for wrong BT adapter (tincan-5y8km.2)
- ea35b80 feat(gui): BT device picker in settings + adapter_warning/device_discovered defaults (tincan-5y8km.2, tincan-ddnwh.3)
- 261d15c feat(gui): Bluetooth Device picker in Settings — saves to tincan.ini (tincan-ddnwh.3)
- 39919dc chore: release gate PASS for resilient-tincand-bringup-dufe8 (Group 2, previous gate)
- bde4213 fix(lint): wrap E501 lines in _resolve_device_address and _select_backend (tincan-1f7mi)

## Gate History
- f1dd8ed: Gate PASS (Group 1 — tincan-u25u7, at 261d15c)
- 39919dc: Gate PASS (Group 2 — tincan-u25u7, at 261d15c; pre-bde4213)
- beaacd6: Gate FAIL — cd7ec0c unreviewed + dirty workspace (removed by builder force-push)
- **this commit**: Gate PASS — tincan-aw7oy, at bde4213

## Non-blocking findings (from review tincan-sa03y)
1. **[LOW]** main.py:747 — `_adapter_mismatch_warning` is dead state
2. **[LOW]** degradation_banners.py:465 — `QLabel.setText()` without `setTextFormat(PlainText)`
3. **[LOW]** up.py:112-115 — start failure conflated with unit-absent
