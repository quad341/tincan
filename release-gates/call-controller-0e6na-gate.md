# Release Gate: HFP call control daemon — im.tincan.Calls (tincan-0e6na)

**Deploy bead:** tincan-q0o4k  
**Source bead:** tincan-fpwc7  
**Branch:** `feat/call-controller-0e6na`  
**Base branch:** `fix/hfp-sco-selinux-policy` (PR #106)  
**Head commit:** `8b32b95ef9f73052df2f144c46ffa2e18fbb4c3e`  
**PR:** quad341/tincan#119 (https://github.com/quad341/tincan/pull/119)  
**Date:** 2026-06-11  
**Verdict:** ✅ PASS

> **Stack note:** PR #119 is based on `fix/hfp-sco-selinux-policy` (PR #106).
> PR #119 cannot land until PR #106 merges.

> **SHA note:** Reviewer cited `88e10be` (pre-rebase equivalent of commit `89c39aa`
> "chore: release gate PASS for call-controller-0e6na"). The current HEAD `8b32b95`
> has 3 additional commits (58667ab, fedf29f, 8b32b95) that the reviewer explicitly
> reviewed and approved — their verdict covers the current HEAD.

---

## Gate Criteria

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | ✅ PASS | tincan-fpwc7 closed with PASS; tincan/reviewer (claude-sonnet-4-6) 2026-06-11; all ACs confirmed; 0 blocking findings |
| 2 | Acceptance criteria met | ✅ PASS | See detail below |
| 3 | Tests pass | ✅ PASS | 1796 passed, 1 skipped, 6 xfailed — ruff clean on new files (see detail) |
| 4 | No HIGH findings open | ✅ PASS | No HIGH findings; previous MEDIUM (GUI method mismatch) RESOLVED in fedf29f; remaining LOW |
| 5 | Final branch clean | ✅ PASS | `git status` — nothing to commit, working tree clean |
| 6 | Branch diverges cleanly from main | ✅ PASS | `git merge-tree` vs origin/main: 0 conflicts; stacked on PR #106 (prerequisite) |
| 7 | Single feature theme | ✅ PASS | Single bead, single subsystem: HFP call control daemon (call_controller.py + im.tincan.Calls D-Bus interface) |

---

## Criterion 2 — Acceptance criteria detail

**call_controller.py** — `CallController` class:
- `_discover_modem()`: HFP modem discovery with 30s exponential retry on ModemAdded signal
- `answer_call()`, `hangup_call()`, `dial()`, `send_dtmf()`: oFono VoiceCallManager/VoiceCall bridge
- `is_call_setup_ready()` promoted to module-level (mockable); raises `NotAvailable` when False
- 5s audio timeout guard → `AudioError(sco_timeout)` signal; `AudioRestored` on recovery
- Hardcoded `_IPHONE_MAC_FRAGMENT` for reference HW (tracked for multi-device)

**dbus_service.py** — `IFACE_CALLS = "im.tincan.Calls"`:
- Methods: `Dial(number→call_id)`, `Answer(call_id)`, `Hangup(call_id)`, `SendDtmf(key)`
- Signals: `IncomingCall(caller_name, caller_number)`, `CallConnected()`, `CallEnded()`, `AudioError(reason)`, `AudioRestored()`
- All methods gated by `call_setup_ready` → `org.ofono.Error.NotAvailable` when HFP not ready
- Signal subscriptions aligned with daemon interface (fedf29f resolved MEDIUM GUI-method-mismatch finding)

**tincand/__main__.py**: `CallController` instantiated at startup and wired to service.

**test_calls_interface.py** + **test_dbus_service_calls.py** (contract tests):
- Dial/Answer/Hangup/SendDtmf → `NotAvailable` when `call_setup_ready` is False
- `ServiceUnknown` when no controller wired; `SendDtmf` rejects invalid keys
- `_resolve_call('')` fallback to single active call; guard coverage on all 4 methods

---

## Criterion 3 — Test detail

```
pytest (full suite, --ignore=tests/tincand/test_mcp_server.py):
1796 passed, 1 skipped, 6 xfailed, 1 warning

pre-existing missing-dep: test_mcp_server.py — ModuleNotFoundError: mcp
(present on main since #90; not introduced by this branch)

ruff check <call-controller files>: All checks passed.

ruff check <shared test files vs main>: 4 errors in test_hfp_capability.py +
test_dbus_contract.py — all pre-existing from fix/hfp-sco-selinux-policy base
(PR #106 base had 11 errors in these files; PR #119 reduced to 4; none in
call-controller-specific code).
```

---

## Resolved findings (since previous gate tincan-97qfw)

| Severity | Finding | Resolution |
|----------|---------|------------|
| MEDIUM | GUI/daemon method mismatch: `HangUp()/Hold()/Unhold()/RetrySco()` → now `Hangup(call_id)/Answer()/Dial()/SendDtmf()` | ✅ RESOLVED in fedf29f |
| LOW | `is_call_setup_ready` not module-level (hard to mock) | ✅ RESOLVED in 8b32b95 |

## Open findings (non-blocking)

| Severity | Finding | Tracking |
|----------|---------|---------|
| LOW | Retry/bind duplication race in `_discover_modem()` — double VCM signal handler registration possible | tincan-z2l9w |
| LOW | `_KNOWN_PENDING_DAEMON_IFACES` still lists `im.tincan.Calls` as pending → 5 xfails in test_dbus_contract.py; update post-merge | tincan-z2l9w |
| INFO | `_IPHONE_MAC_FRAGMENT = d0_6b_78_33_46_20` — hardcoded reference HW MAC | tracked for multi-device |
