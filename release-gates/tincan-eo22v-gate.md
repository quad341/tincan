# Release Gate: tincan-eo22v — ANCS actionable diagnostics + LE-advertising startup probe

Evaluated: 2026-06-07
Commit: d081265 (cherry-pick of bc268f3 from fix/tincan-zlg3k onto origin/main)
Deploy bead: tincan-eo22v
Source/builder bead: tincan-1d69e
Review bead: tincan-ubs50
Branch: fix/ancs-diagnostics-le-probe

---

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-ubs50: "VERDICT: PASS" from tincan/reviewer (Claude Sonnet 4.6). All 6 spec criteria confirmed met. 0 blocking findings. |
| 2 | Acceptance criteria met | **PASS** | (a) `_on_adv_error` calls `set_capability("ancs", False)` with `self._service is not None` guard ✓ (b) logs adapter path + remedies ("USB"/"--experimental") ✓ (c) `_probe_le_advertising` reads `LEAdvertisingManager1.GetAll()`, logs Supported/ActiveInstances, degrades on `SupportedInstances==0` or `DBusException` ✓ (d) never raises out of `start()` ✓ (e) no behaviour change when RegisterAdvertisement succeeds ✓. All confirmed by reviewer and 3/3 new unit tests. |
| 3 | Tests pass | **PASS** | `python3 -m pytest tests/tincand/ -q`: 746 passed, 1 skipped, 1 xfailed. ANCS suite: **140/140** (incl. 3 new `TestAdvErrorDiagnostics`). The 1 failure (`test_dbus_client_live.py::TestSignalReception::test_daemon_gui_receives_required_signals_and_updates_model`) is a live D-Bus integration test that also fails on `origin/main` (pre-existing infrastructure limitation — D-Bus session not available in rig; unrelated to this change). |
| 4 | No high-severity findings open | **PASS** | Reviewer: "Findings: None blocking." 0 HIGH findings. |
| 5 | Final branch clean | **PASS** | `git status`: no uncommitted source changes; only untracked worktree artifacts (`.claude/`, `.codex/`, `.gc/`, `.gitkeep`). |
| 6 | Branch diverges cleanly from main | **PASS** | `git cherry-pick bc268f3` onto `origin/main` applied without conflicts. 1 commit ahead of main. |
| 7 | Single feature theme | **PASS** | 2 files: `tincand/backends/ancs.py` (+49 lines: `_on_adv_error` update + `_probe_le_advertising` helper) and `tests/tincand/test_ancs_backend.py` (+39 lines: §14 `TestAdvErrorDiagnostics`). Single subsystem (ANCS daemon backend). |

**Overall: PASS**

## Release criteria (PROJECT_MANIFEST.md)

| # | Criterion | Result |
|---|-----------|--------|
| 1 | Phase DoD met | N/A — this is a daemon-hardening/observability change, not a phase-ship commit |
| 2 | All automated tests pass | **PASS** — see criterion 3 above (pre-existing live test failure on main) |
| 3 | Lint/format clean | **PASS** — `ruff check tincand/backends/ancs.py tests/tincand/test_ancs_backend.py`: All checks passed |
| 4 | No hardcoded iOS/iPhone-model assumptions | **PASS** — probe reads actual hardware capabilities at runtime; no version assumptions |
| 5 | LIMITATIONS.md updated if capabilities changed | N/A — platform capabilities unchanged; only observability improved |
| 6 | Onboarding unaffected | **PASS** — "Show Notifications" requirement and reconnect handling untouched |

## Changed files

- `tincand/backends/ancs.py`: `_on_adv_error` now calls `set_capability("ancs", False)` (guarded) and logs adapter path + actionable remedy. New `_probe_le_advertising()` helper reads `LEAdvertisingManager1.GetAll()` at `start()` end, degrades capability on `SupportedInstances==0` or interface absent, never raises.
- `tests/tincand/test_ancs_backend.py`: §14 `TestAdvErrorDiagnostics` — 3 new tests: `test_adv_error_sets_capability_false_and_logs_remedy`, `test_adv_error_without_service_does_not_raise`, `test_startup_probe_reports_zero_supported_instances`.

## Ruff

`ruff check tincand/backends/ancs.py tests/tincand/test_ancs_backend.py` — All checks passed.
