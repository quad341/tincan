# Release Gate: hciN-based adapter check (tincan-hzcfj.1)

**Branch:** `fix/hcin-adapter-hzcfj.1`  
**Tip commit:** `97c6cb5`  
**Gate evaluated:** 2026-06-23  
**Deploy bead:** tincan-p3m4h  
**Review bead:** tincan-s4wpy (CLOSED — PASS)

## Verdict: PASS

All 7 criteria pass. Cleared for PR.

---

## Criterion Checklist

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | ✅ PASS | Review bead tincan-s4wpy closed PASS; 11/11 AC verified by reviewer |
| 2 | Acceptance criteria met | ✅ PASS | All 11 AC verified (see below) |
| 3 | Tests pass | ✅ PASS | 1985 passed, 1 skipped, 6 xfailed (see below) |
| 4 | No high-severity findings open | ✅ PASS | Reviewer found no security issues; no HIGH findings |
| 5 | Final branch is clean | ✅ PASS | `git status` — no uncommitted tracked changes |
| 6 | Branch diverges cleanly from main | ✅ PASS | `git merge-base --is-ancestor origin/main HEAD` confirmed |
| 7 | Single feature theme | ✅ PASS | All changes in one subsystem: HFP adapter hciN matching |

---

## Acceptance Criteria (11/11)

1. `verify_dongle_adapter('/hfp/.../hci1/...', 'hci1')` → True, INFO, no WARNING ✅
2. `verify_dongle_adapter('/hfp/.../hci0/...', 'hci1')` → False, WARNING ✅
3. `verify_dongle_adapter('/org/ofono/unknown', 'hci1')` → False ✅
4. `verify_dongle_adapter('', 'hci1')` → False ✅
5. `verify_dongle_adapter('/hfp/.../hci1/...', '')` → False ✅
6. `_DONGLE_ADAPTER_FRAGMENT` absent from all files (grep clean) ✅
7. USB constants renamed `_RTL8761B_USB_VENDOR`/`_RTL8761B_USB_PRODUCT` ✅
8. `CallController` accepts `adapter_hci` kwarg, stores as `self._adapter_hci` ✅
9. `_bind_modem` passes `self._adapter_hci` to `verify_dongle_adapter` ✅
10. `__main__.py` derives hciN from `adapter_path` and injects into `CallController` ✅
11. CI: 49/49 tests pass (includes new §7–9 tests; 1985 total passing) ✅

---

## Test Run

```
pytest tests/ --ignore=tests/tincand/test_mcp_server.py
1985 passed, 1 skipped, 6 xfailed, 1 warning in 38.93s
```

`test_mcp_server.py` excluded: pre-existing `ModuleNotFoundError: No module named 'mcp'`
present on `origin/main` — not introduced by this branch.

---

## Lint

`ruff check` on feature-branch-modified files (`call_controller.py`, `__main__.py`,
`call_audio.py`): one pre-existing E402 in `__main__.py` (line 14 — `from gi.repository
import GLib` after a module-level constant). Confirmed identical on `origin/main` — not
introduced by this branch. No new lint violations.

---

## Files Changed

- `tincand/call_audio.py` — replaced `_DONGLE_ADAPTER_FRAGMENT` with `_HCI_RE`; renamed USB constants
- `tincand/call_controller.py` — `CallController.__init__` accepts `adapter_hci` kwarg; `_bind_modem` calls `verify_dongle_adapter(modem_path, self._adapter_hci)`
- `tincand/__main__.py` — derives `adapter_hci` from `adapter_path`; injects into `CallController`
- `tests/tincand/test_call_controller.py` — new §7–9 tests
- `tests/tincand/test_call_audio.py` — updated for renamed constants
- `docs/plans/verify-dongle-adapter-hci-fix.md` — plan artifact (non-functional)
