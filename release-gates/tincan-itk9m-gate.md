# Release Gate: tincan-itk9m (mock spawn_daemon in GUI conftest)

**Deploy bead:** tincan-4kdgj  
**Source bead:** tincan-itk9m  
**Branch:** feat/call-ui-jni3z-land  
**Commit:** 7671900d27ce05af4898ba6f4d75c766840a1b37  
**Date:** 2026-06-10  
**Result:** ❌ FAIL

---

## Gate Checklist

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | ✅ PASS | tincan-i01j6 CLOSED with `REVIEW VERDICT: PASS` (tincan/reviewer, 2026-06-10). All 6 findings informational, zero blockers. |
| 2 | Acceptance criteria met | ✅ PASS | Three items from tincan-itk9m addressed: (1) autouse `_no_daemon_spawn` fixture in conftest.py patching `tincan_gui.main.spawn_daemon`; (2) `PYTEST_CURRENT_TEST` env guard in daemon_launcher.py; (3) regression test in test_main_daemon.py verifying zero Popen calls. |
| 3 | Tests pass | ✅ PASS | Reviewer confirmed: 1711 passed, 6 skipped, 6 xfailed. Pre-existing mcp import error in test_mcp_server.py unrelated to this diff. |
| 4 | No high-severity review findings open | ✅ PASS | All findings in tincan-i01j6 are informational PASS; count of unresolved HIGH = 0. |
| 5 | Final branch is clean | ✅ PASS | No uncommitted changes on feat/call-ui-jni3z-land. |
| 6 | Branch diverges cleanly from main | ❌ **FAIL** | `git merge-tree` shows a merge conflict in `tincan_gui/daemon_launcher.py`. Root cause: `f4d2c28` (PR #114, merged 2026-06-10 12:22 PDT) added a `TINCAN_ALLOW_DAEMON_SPAWN` guard to `daemon_launcher.py`. Commit 7671900 (2026-06-10 12:29 PDT) added a different `PYTEST_CURRENT_TEST` guard to the same lines. The branch was not rebased after PR #114 merged. These approaches conflict and cannot auto-merge. |
| 7 | Single feature theme | n/a | Gate halted at criterion 6. |

---

## Conflict Detail

**`tincan_gui/daemon_launcher.py` — conflicting daemon-guard approaches:**

`origin/main` (f4d2c28, PR #114):
```python
if "pytest" in sys.modules and not os.environ.get("TINCAN_ALLOW_DAEMON_SPAWN"):
    _log.warning("spawn_daemon: skipped — running under pytest ...")
    return None
```

`feat/call-ui-jni3z-land` (7671900):
```python
if os.environ.get("PYTEST_CURRENT_TEST"):
    _log.debug("spawn_daemon: skipped (running under pytest)")
    return None
```

Both address tincan-itk9m but via different mechanisms. PR #114 also already states "Addresses tincan-itk9m."

---

## Additional Context for Builder

- PR #113 (`feat(calls): wire HFP answer/hangup/dial + call_setup_ready cap`) is already open against `main` using `feat/call-ui-jni3z-land` as head. Commit 7671900 was pushed to this branch **after** PR #113 was opened (PR at 19:02Z, commit at 19:29Z), so PR #113 now silently includes the daemon fix.
- Since `f4d2c28` (already in `main`) also addresses tincan-itk9m, the builder should evaluate whether 7671900 still adds value on top of f4d2c28's approach, or whether the fix is already covered and 7671900 can be dropped.
- Branch must be rebased on `origin/main` and the `daemon_launcher.py` conflict resolved before deploy can proceed.

---

**Routing:** Back to builder (`tincan/builder`) — rebase required.
