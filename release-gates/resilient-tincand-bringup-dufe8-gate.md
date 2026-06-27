# Release Gate: resilient-tincand-bringup-dufe8 (Group 2)

**Bead:** tincan-u25u7  
**Source bead:** tincan-r60ca  
**Branch (tincan):** feat/resilient-tincand-bringup-dufe8 @ 261d15c  
**Branch (tincan-iris):** feat/resilient-tincand-bringup-dufe8 @ b81555a  
**Gate evaluated:** 2026-06-27

## Verdict: PASS

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-r60ca — Verdict: PASS from tincan/reviewer (Claude). Notes: "All 5 features present and spec-compliant. No security blockers." |
| 2 | Acceptance criteria met | **PASS** | All 5 features verified by reviewer and code-checked (see below) |
| 3 | Tests pass | **PASS** | tincan: 2088 passed, 2 skipped, 10 xfailed. tincan-iris: 1285 passed, 13 skipped, 3 xpassed. Pre-existing `mcp` import error on test_mcp_server.py confirmed present on main — not a regression. |
| 4 | No high-severity findings | **PASS** | 3 LOW findings (non-blocking): dead `_adapter_mismatch_warning` state, missing PlainText format on QLabel, start-failure/unit-absent conflation in up.py. Zero HIGH findings. |
| 5 | Final branch is clean | **PASS** | `git status` — no staged or modified tracked files on either branch. Untracked: .claude/, .codex/, docs/plans/, worktrees/ (gitignored artifacts). |
| 6 | Branch diverges cleanly from main | **PASS** | `git merge-base --is-ancestor origin/main feat/...` → 0 for both repos. No conflicts. |
| 7 | Single feature theme | **PASS** | All commits address "resilient tincand bring-up": adapter mismatch detection (GUI banner), BT device picker (settings), iris up/doctor D-Bus integration. One subsystem, one theme. |

## Acceptance Criteria Check

| Feature | Spec ref | Status |
|---------|----------|--------|
| iris/up.py: `_bring_up_tincand()` + `_print_tincand_readiness()` — start if inactive, 10s health wait, 3x D-Bus retries, 4-case readiness output | tincan-m9t6h.1 | PRESENT — verified by reviewer + 51 iris tests pass |
| iris/doctor.py: `_tincand_deep_check()` — D-Bus GetStatus() probe, health + adapter_warning + call_setup_ready; auto-runs on `--check tincand` | tincan-m9t6h.2 | PRESENT |
| tincan_gui/degradation_banners.py + main.py: AdapterMismatchBanner (amber, non-dismissible), 5s poll timer | tincan-5y8km.2 | PRESENT |
| tincan_gui/dbus_client.py: `get_status()` defaults for adapter_warning + device_discovered | — | PRESENT |
| tincan_gui/settings_dialog.py: `_DeviceLoader` (oFono HFP modem discovery), BT Device picker, saves `bluetooth/device_address` to tincan.ini | tincan-ddnwh.3 | PRESENT |

## Commits in PR

**tincan** (above origin/main):
- 258e2b9 feat(tincand): resilient bring-up — watchdog, device auto-discovery, adapter_warning (tincan-dufe8) [Group 1, separately reviewed]
- 27d64b4 feat(gui): AdapterMismatchBanner — persistent amber warning for wrong BT adapter (tincan-5y8km.2)
- ea35b80 feat(gui): BT device picker in settings + adapter_warning/device_discovered defaults (tincan-5y8km.2, tincan-ddnwh.3)
- 261d15c feat(gui): Bluetooth Device picker in Settings — saves to tincan.ini (tincan-ddnwh.3)

**tincan-iris** (above origin/main):
- 7996e89 feat(doctor): want-down sentinel hint in tincand DOWN output (tincan-i5dlb.2) [Group 1, separately reviewed]
- 6f790c6 feat(up): tincand bring-up tier — `_bring_up_tincand` + `_print_tincand_readiness` (tincan-m9t6h.1)
- b81555a feat(doctor): tincand deep check — `_tincand_deep_check`, ServiceDescriptor, JSON detail (tincan-m9t6h.2)

## Non-blocking findings (from review tincan-r60ca)

1. **[LOW]** main.py:747 — `_adapter_mismatch_warning` is dead state (initialized, never read)
2. **[LOW]** degradation_banners.py:465 — `QLabel.setText()` without `setTextFormat(PlainText)` (trusted source, no security risk)
3. **[LOW]** up.py:112-115 — start failure conflated with unit-absent (operator can distinguish via journald)
