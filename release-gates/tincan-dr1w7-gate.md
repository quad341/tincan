# Release Gate: tincan-dr1w7 — Remove DBusGMainLoop to Fix Subsequent Notifications

**Bead:** tincan-98b3r (deploy) → tincan-dr1w7 (feature)
**Branch:** feature/tincan-dr1w7
**Tip commit:** df98bf3
**Review bead:** tincan-zp82e (PASS — reviewed df98bf3 + 6c5105fa as a stacked pair)
**Note:** The word-wrap commit (tincan-5hcyf, originally 6c5105fa, now rebased as c967d04) was split into a separate branch (feature/tincan-5hcyf) and deployed as PR#29. This gate covers the notifications fix only.

---

## Criteria

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-zp82e verdict: PASS. The notifications commit (df98bf3) was reviewed as the first of two commits; finding [INFO] only — pure 2-line deletion reverting a known regression. No blockers noted. |
| 2 | Acceptance criteria met | **PASS** | `_ensure_bus()` in `tincan_gui/notifications.py`: removed `import dbus.mainloop.glib` and `DBusGMainLoop(set_as_default=True)`. Root cause: GLib mainloop never runs in a Qt app; after the first `Notify()` call, the GLib-integrated D-Bus connection stalled, dropping all subsequent calls silently. Removing these two lines restores the original plain `dbus.SessionBus()` behavior (from commit e0b7afe). Acceptance: "every qualifying incoming message notifies." |
| 3 | Tests pass | **PASS** | `pytest tests/` on feature/tincan-dr1w7: **927 passed, 0 failed**. (Note: tests pre-set `notifier._bus = MagicMock`, so `_ensure_bus()` is bypassed; reviewer correctly noted this is acceptable for a GLib-mainloop fix.) |
| 4 | No high-severity review findings open | **PASS** | Only [INFO]-level finding in review. No HIGH findings. |
| 5 | Final branch is clean | **PASS** | `git status` clean; feature/tincan-dr1w7 has one commit (df98bf3) above main. |
| 6 | Branch diverges cleanly from main | **PASS** | Test-merge with `origin/main` (tip: df22927): automatic merge succeeded, no conflicts. `tincan_gui/notifications.py` was not touched by any of the recent merges (#22–#29). |
| 7 | Single feature theme | **PASS** | One bug fix: 2-line deletion in `tincan_gui/notifications.py`. Touches a single function in a single file. |

**Lint:** `tincan_gui/notifications.py` passes `ruff check` with zero findings.

## Verdict: PASS
