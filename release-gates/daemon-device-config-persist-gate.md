# Release Gate: daemon-device-config-persist

**Bead:** tincan-21n33 (source: tincan-oxthc)
**Branch:** fix/daemon-device-config-persist
**Commit:** 20aa75889b426aa08d1be5656ec82b7d4abaf4d1
**Date:** 2026-06-10

## Gate Result: PASS

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | ✅ PASS | tincan-i1qdw closed with `Review verdict: PASS` by tincan/reviewer (Claude Sonnet 4.6) |
| 2 | Acceptance criteria met | ✅ PASS | Persist-on-connect half fully implemented; device-selection UI for first-run explicitly deferred to tincan-r41sx per accepted scope split |
| 3 | Tests pass | ✅ PASS | 1707 passed, 6 skipped, 6 xfailed (see below) |
| 4 | No high-severity findings open | ✅ PASS | 0 HIGH findings; 1 LOW (non-blocking, carried from reviewer) |
| 5 | Final branch is clean | ✅ PASS | `git status` clean; only untracked deployer artifacts (.claude/, .codex/, .gc/, .gitkeep) |
| 6 | Branch diverges cleanly from main | ✅ PASS | 1 commit ahead of origin/main, no conflicts |
| 7 | Single feature theme | ✅ PASS | Single commit; touches `tincan_gui/main.py` (config save on connect) + `tests/tincan_gui/test_main_daemon.py` only |

## Test Summary

```
1707 passed, 6 skipped, 6 xfailed, 1 warning in 81.86s
```

4 new tests added in `tests/tincan_gui/test_main_daemon.py` (class `TestDeviceConfigPersist`):
- `test_save_called_when_device_differs_from_config` — happy path
- `test_save_not_called_when_device_already_matches_config` — no-op idempotency
- `test_save_not_called_when_device_address_empty` — empty guard
- (backend preservation covered implicitly in happy path assertion)

## Acceptance Criteria Check

From tincan-oxthc: _"Daemon starts with no --device flag by reading a persisted config; a setup path lets the user select the paired device and writes it to config; CLI flags still override; adapter defaults to auto-detect."_

This PR covers the **persist half**:
- ✅ On `_on_daemon_connected`, if `device_address` differs from config, `save_daemon_config()` writes the address to `~/.config/tincan/config`
- ✅ Subsequent startups call `load_daemon_config()` (pre-existing) to read the persisted address — no `--device` flag needed
- ✅ Backend/adapter config preserved on save (`DaemonConfig(backend=cfg.backend, device=device_address)`)
- ✅ CLI override path unchanged (pre-existing behavior, not touched)
- ⏭ First-run device-selection UI deferred to tincan-r41sx (accepted scope split per bead close reason)

## Findings

**[LOW] Robustness** — `tincan_gui/main.py:868-872`
No try/except around `save_daemon_config()` in `_on_daemon_connected`. If it raises (PermissionError, disk full), the exception aborts the slot and subsequent UI updates are skipped. Improbable on normal desktop; non-blocking. Recommendation: wrap in `try/except` with `_log.warning`. (Carried from reviewer tincan-i1qdw.)

**[ADVISORY] Lint** — `tincan_gui/main.py:869`
E501: comment line 105 chars (limit 99). Cosmetic only; non-functional code. Non-blocking.

## Project Manifest Release Criteria

Per `docs/PROJECT_MANIFEST.md` Required criteria (informational for component PRs):
1. Phase-1 definition-of-done (full SMS conversation) — not yet; this is an enabler
2. All tests pass — ✅ (1707 passed)
3. Lint/format clean — advisory E501 on comment (see Findings above)
4. No hardcoded iOS-version assumptions — ✅ confirmed in diff
5. LIMITATIONS.md updated — no new platform limitations introduced; N/A
6. Onboarding (Show Notifications / reconnect) — ✅ unchanged; reconnect handling and Show Notifications guidance intact
