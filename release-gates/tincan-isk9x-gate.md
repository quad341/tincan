# Release Gate: tincan-isk9x — batch2 GUI fixes

Evaluated: 2026-06-08
Commit: 52ee59b (tip of fix/gui-bugs-batch1)
Deploy bead: tincan-isk9x
Review bead: tincan-kf1hi (batch2 — 4 bugs reviewed at f304b0e)

---

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | **PASS** | tincan-kf1hi closed with verdict PASS at commit f304b0e. Reviewer ran full suite (1666 tests) on the branch, covering all 4 commits. Post-review commit 52ee59b is a lint-only clean-up of reviewer-flagged pre-existing ruff errors (I001/E501 in thread_view.py) + test docstring update — no logic changes. |
| 2 | Acceptance criteria met | **PASS** | All 4 batch2 bugs CLOSED with close reasons referencing f304b0e: tincan-yxajc (DBusGMainLoop at main() start fixes ActionInvoked dispatch), tincan-sl54r (mainloop fix + immediate UI update in _on_notification_mark_read), tincan-ndm0k (AlignLeft\|AlignTop overrides browser-CSS justify), tincan-36af0 (_emoji_font_families() on badge QLabel). Batch1 bugs (16fa23d: cxtrq, rx37n, sq05d, yil9p, hrfuv, iy61t; 42d9927: b10bs, 15xl9, 67s7h, hpk7b) also on branch and passed in the full suite run. |
| 3 | Tests pass | **PASS** | `python -m pytest tests/ -q --ignore=tests/tincand/test_mcp_server.py`: **1666 passed, 6 skipped, 6 xfailed, 0 failures** (36.69s). test_mcp_server.py excluded — pre-existing `mcp` module not installed (noted by reviewer). |
| 4 | No high-severity findings open | **PASS** | Reviewer: "No OWASP concerns. No user input, no injection risk, no credential exposure, no new attack surface." One non-blocking coverage gap filed as tincan-80wbb (sl54r UI path). |
| 5 | Final branch clean | **PASS** | `git status` clean — no uncommitted changes. Untracked: `.beads/`, `.claude/`, `.codex/`, `.gc/`, `.gemini/` (tooling, not part of the PR). |
| 6 | Branch diverges cleanly from main | **PASS** | 4 commits above `origin/main` (fork point da693df). Zero merge conflicts. |
| 7 | Single feature theme | **PASS** | All 4 commits are P2/P3 bug fixes from the 2026-06-08 bug-report batch. Primary surface is `tincan_gui/` (13 fixes); one minor daemon fix (tincan-hpk7b in 42d9927, `tincand/__main__.py`) resolves hardcoded adapter path for the active test device. All ship together as a single session's batch. |

**Overall: PASS**

## Commit log (above main)

```
52ee59b fix(gui): split QtGui import to fix E501/I001 lint; update stale docstring
f304b0e fix(gui): notification actions never fire; text justified; emoji badge box
42d9927 fix(gui): title-bar icons invisible in light theme; digits drop; list clips; ANCS adapter hardcoded
16fa23d fix(gui): batch P2 bug fixes — linkify, copy, dedup, emoji preview, theme, bool settings
```

## Changed files

- `tincan_gui/__main__.py`: new `--dark`/`--light` and `--adapter` passthrough args
- `tincan_gui/_settings.py`: `bool_value()` helper for PySide6 INI bool coercion
- `tincan_gui/conversation_list.py`: emoji preview in RichText format; top card margin fix
- `tincan_gui/main.py`: DBusGMainLoop before SessionBus (notification actions fix); _on_notification_mark_read immediate UI clear; palette-change stylesheet reconnect
- `tincan_gui/notification_center.py`: _emoji_font_families() on badge QLabel
- `tincan_gui/notifications.py`: bool_value() for settings reads
- `tincan_gui/settings_dialog.py`: bool_value() for settings reads
- `tincan_gui/thread_view.py`: bare-URL linkification; copy fix; _emoji_font_families() with QFontInfo; AlignLeft text alignment; lint fix (import split)
- `tincan_gui/tray.py`: bool_value() for settings reads
- `tincand/__main__.py`: --adapter / TINCAN_ADAPTER + _resolve_adapter_path() auto-detection
- `tests/tincan_gui/test_sent_bodies.py`: docstring update for always-track behavior

## Ruff (pre-existing, not introduced by this branch)

- `tincan_gui/degradation_banners.py:17` F401 (pre-existing, file not in diff)
- `tincan_gui/settings_dialog.py:445` E501 (pre-existing, line not in diff)
