# Release Gate: HFP call control daemon — im.tincan.Calls (tincan-0e6na)

**Deploy bead:** tincan-97qfw  
**Source bead:** tincan-t9ujy (review)  
**Branch:** `feat/call-controller-0e6na`  
**Base branch:** `fix/hfp-sco-selinux-policy` (PR #106)  
**Head commit:** `0cd4433ce183060be6f1885e84672c500c760ecb`  
**PR:** quad341/tincan#119 (https://github.com/quad341/tincan/pull/119)  
**Date:** 2026-06-10  
**Verdict:** ✅ PASS

> **Stack note:** PR #119 is based on `fix/hfp-sco-selinux-policy` (PR #106).
> PR #119 cannot land until PR #106 merges. PR #106 is currently OPEN with
> an architectural hold (gm-5d2m3) and has a conflict with `main` that must
> be resolved before #106 can merge.

---

## Gate Criteria

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | ✅ PASS | tincan-t9ujy closed with pass verdict; 3-model ensemble (Qwen + Claude/Opus 4.8 + Codex); synthesis: fix-merge, all blockers non-blocking |
| 2 | Acceptance criteria met | ✅ PASS | See detail below |
| 3 | Tests pass | ✅ PASS | 1729 passed, 1 skipped, 6 xfailed — ruff clean (see detail) |
| 4 | No HIGH findings open | ✅ PASS | No HIGH findings; MEDIUM tracked in tincan-d0p50 (non-blocking: gated by call_setup_ready) |
| 5 | Final branch clean | ✅ PASS | `git status` — nothing to commit, working tree clean |
| 6 | Branch diverges cleanly from main | ✅ PASS | PR's own commits (9c0820c, 0cd4433c) touch only new files; README.md conflict with main originates entirely from #106 base, not from #119 commits |
| 7 | Single feature theme | ✅ PASS | Single bead, single subsystem: HFP call control daemon (call_controller.py + im.tincan.Calls D-Bus interface) |

---

## Criterion 2 — Acceptance criteria detail

**call_controller.py** — `CallController` class:
- `_discover_modem()`: HFP modem discovery with 30s exponential retry on ModemAdded signal
- `answer_call()`, `hangup_call()`, `dial()`, `send_dtmf()`: oFono VoiceCallManager/VoiceCall bridge
- `call_setup_ready` guard via `is_call_setup_ready()` (raises `NotAvailable` when False)
- 5s audio timeout guard → `AudioError(sco_timeout)` signal; `AudioRestored` on recovery
- Hardcoded `_IPHONE_MAC_FRAGMENT` for reference HW (expected; tracked for multi-device in z2l9w)

**dbus_service.py** — `IFACE_CALLS = "im.tincan.Calls"`:
- Methods: `Dial(number→call_id)`, `Answer(call_id)`, `Hangup(call_id)`, `SendDtmf(key)`
- Signals: `IncomingCall(caller_name, caller_number)`, `CallConnected()`, `CallEnded()`, `AudioError(reason)`, `AudioRestored()`
- All methods gated by `call_setup_ready` → `org.ofono.Error.NotAvailable` when HFP not ready

**tincand/__main__.py**: `CallController` instantiated at startup and wired to service.

**0cd4433c (post-review addition)**: Contract tests in `tests/tincand/test_calls_interface.py` (166 lines):
- Dial/Answer/Hangup/SendDtmf → `NotAvailable` when `call_setup_ready` is False
- `ServiceUnknown` when no controller wired
- `SendDtmf` rejects invalid keys with `InvalidArgument`
- `_resolve_call('')` fallback to single active call

---

## Criterion 3 — Test detail

```
pytest (full suite, excl. test_mcp_server.py — pre-existing missing-dep skip):
1729 passed, 1 skipped, 6 xfailed, 1 warning

ruff check tincand/ tests/tincand/test_calls_interface.py → All checks passed.
```

Test count increased by 13 from reviewed commit (9c0820c → 0cd4433c): all from new
`test_calls_interface.py` contract tests. The new commit is tests-only; no logic changes.

---

## Open findings (non-blocking)

| Severity | Finding | Tracking |
|----------|---------|---------|
| MEDIUM | GUI/daemon method mismatch: `main.py` calls `HangUp()/Hold()/Unhold()/RetrySco()`; daemon exports `Hangup(call_id)/Answer()/Dial()/SendDtmf()`. Unreachable today (all methods gated by `call_setup_ready`). | tincan-d0p50 |
| LOW | Retry/bind duplication race in `_discover_modem()` — double VCM signal handler registration possible | tincan-z2l9w |
| LOW | Stale `_KNOWN_PENDING_DAEMON_IFACES` in test_dbus_contract.py:118 — `im.tincan.Calls` still listed as pending, causing 5 tests to xfail | tincan-z2l9w |
| INFO | `_IPHONE_MAC_FRAGMENT = d0_6b_78_33_46_20` — hardcoded reference HW MAC | tracked for multi-device |
