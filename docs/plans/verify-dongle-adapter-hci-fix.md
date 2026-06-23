# Plan: Fix verify_dongle_adapter — hciN Injection via CallController Constructor

**Root bead:** tincan-hzcfj  
**Date:** 2026-06-23  
**PM:** tincan/pm

---

## Problem

`call_audio.verify_dongle_adapter(modem_path)` always returns `False`.
oFono HFP modem paths encode the adapter *name* (`hciN`) and the remote device
MAC — never the local adapter MAC. Checking for a MAC fragment
(`_DONGLE_ADAPTER_FRAGMENT`) in the path can never match.

This is a diagnostic-only fix. The function warns but does not gate SCO routing
(that's OQ1, explicitly deferred to a future bead).

---

## Architecture decision: A1 — Constructor injection

`expected_hci` is derived in `__main__.py` from the already-resolved
`adapter_path` and passed into `CallController` as `adapter_hci`. This avoids
module-level mutable state (A2) and hot-path D-Bus calls (A3).

Design sign-off (tincan-hzcfj): zero UI delta. Existing `AudioErrorPanel` in
`call_panel.py` is the correct user signal for SCO failure; no new UI needed.

---

## Bead tree

```
tincan-hzcfj  (root — architecture + design complete)
├── tincan-hzcfj.1  [ready-to-build → builder]
│   Implement hciN-based adapter check: verify_dongle_adapter + CallController injection
│
└── tincan-hzcfj.2  [needs-tests → validator]  ← blocked by tincan-hzcfj.1
    Test: CallController.adapter_hci propagation through _bind_modem
```

---

## tincan-hzcfj.1 — Implementation (builder)

Three files change atomically. The builder **must** also fix the CI-breaking
test changes in the same PR (test_call_audio.py imports removed constants and
calls old one-arg signature).

| File | Change |
|------|--------|
| `tincand/call_audio.py` | Remove `_DONGLE_ADAPTER_FRAGMENT`; rename USB constants; rewrite `verify_dongle_adapter(modem_path, expected_hci)` with hciN regex |
| `tincand/call_controller.py` | Add `adapter_hci=""` kwarg to `__init__`; pass `self._adapter_hci` to `verify_dongle_adapter` in `_bind_modem` |
| `tincand/__main__.py` | Parse hciN from `adapter_path` after `_resolve_adapter_path()`; inject into `CallController()` |
| `tests/tincand/test_call_audio.py` | Update imports; rewrite `TestVerifyDongleAdapter` with two-arg signature |

Key guardrails:
- Do NOT gate `_bind_modem` on the return value (OQ1 deferred)
- `_HCI_RE` uses `\b` word-boundary
- `adapter_hci=""` must return `False` without crashing

---

## tincan-hzcfj.2 — Additional tests (validator, after .1 merges)

In `tests/tincand/test_call_controller.py`:
- `CallController` constructor stores `adapter_hci`
- `_bind_modem` passes it to `verify_dongle_adapter` (via mock)
- `__main__` hciN extraction logic (unit-testable portion)

---

## Out of scope

- **OQ1:** Gating SCO routing on `verify_dongle_adapter()` result — separate bead
- **OQ2:** Generalizing USB IDs to come from `list_adapters()` — separate bead
- **Pre-call adapter warning UI** — design spec exists in tincan-hzcfj notes if OQ1 is ever scoped
