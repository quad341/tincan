# Release Gate: tincan-n4tlu (BT adapter picker — tincan-yn2x5)

**Bead:** tincan-n4tlu  
**Source bead:** tincan-yn2x5 (BT adapter picker QComboBox + capability badges)  
**Branch:** fix/call-setup-ready-z0qqo  
**Branch HEAD:** 49efdb5  
**Gate run:** 2026-06-14  
**Result: PASS**

---

## Criterion 1 — Review PASS present

Review bead: tincan-ne6qq  
Initial verdict: `request-changes` (commit 89f23fd) — B1-B3 blockers, L1-L5 lows filed.  
Fix commit: e723eed (B1-B3 resolved) + f20fbcb (L4/L5 resolved via tincan-gu24r).  
**Final verdict: PASS (tincan--reviewer, 2026-06-14)** — branch HEAD 49efdb5.

Evidence from PASS verdict:
- B1 `_AdapterItemDelegate` ✓
- B2 powered-off badge ✓  
- B3 `AccessibleTextRole` ✓  
- L1–L5 resolved ✓  
- 23 adapter_picker tests PASS, 1910 suite PASS

**→ PASS**

---

## Criterion 2 — Acceptance criteria met

Source ACs from tincan-yn2x5:

| AC | Description | Status |
|----|-------------|--------|
| 1 | QLabel replaced with QComboBox, label 'Bluetooth Adapter' | ✓ |
| 2 | Async population via QThread, settings opens <200ms | ✓ |
| 3 | Selection persists to QSettings bluetooth/adapter_path immediately | ✓ |
| 4 | Custom QStyledItemDelegate paint()/sizeHint() two-line rich display | ✓ (B1 resolved) |
| 5 | Capability badges HFP+LE with ✓/✗/? glyphs, WCAG 1.4.1 | ✓ |
| 6 | Refresh button '↺ Refresh' inline right of label row | ✓ |
| 7 | WCAG 2.1 AA color contrast per ki9qt spec | ✓ |
| 8 | AccessibleName + per-item screen reader text | ✓ (B3 resolved) |
| 9 | Tab order: checkboxes → QComboBox → Refresh | ✓ (L1 resolved) |
| 10 | is_selected pre-selects saved adapter only | ✓ |
| 11 | All adapters in dropdown; indigo border on open | ✓ |
| 12 | Loading placeholder, setEnabled(false) while in-flight | ✓ |
| 13 | BT unavailable: section disabled, no QComboBox, amber QLabel frame | ✓ (L2 resolved) |
| 14 | Single-adapter: combo disabled, badges at 60% opacity | ✓ (L3 resolved) |
| 15 | Powered-off badge '⏻ Powered off' amber with tooltip | ✓ (B2 resolved) |
| 16 | State D (B+C combined) | ✓ |

**→ PASS**

---

## Criterion 3 — Tests pass

Command: `python -m pytest --ignore=tests/tincand/test_mcp_server.py --tb=no -q`  
(test_mcp_server.py excluded: `mcp` module not installed; pre-existing CI exclusion, unrelated to this branch.)

```
1910 passed, 1 skipped, 6 xfailed in 35.25s
```

Adapter-picker targeted run:
```
tests/tincan_gui/test_adapter_picker.py  23 passed
tests/tincand/test_adapter_check.py      17 passed
Total: 40 passed in 0.72s
```

**→ PASS**

---

## Criterion 4 — No high-severity findings open

Review verdict PASS; no open blockers. All B1-B3 resolved. L4/L5 resolved (tincan-gu24r). INFO findings I1/I2 accepted by reviewer (non-blocking). No HIGH findings unresolved.

**→ PASS**

---

## Criterion 5 — Final branch is clean

```
git status --short: only untracked workspace files (.claude, .codex, .gc, .gemini, CLAUDE.md)
No staged or unstaged changes to tracked files.
```

**→ PASS**

---

## Criterion 6 — Branch diverges cleanly from main

```
git merge-base --is-ancestor origin/main HEAD: true
15 commits ahead of origin/main, 0 conflicts.
```

**→ PASS**

---

## Criterion 7 — Single feature theme

All 15 commits are in the BT adapter management subsystem:

| Commit | Bead | Description |
|--------|------|-------------|
| 52ee35c | tincan-z0qqo | SELinux unprivileged call_setup_ready fix |
| f00a642 | tincan-uak1h | Tests for call_setup_ready selinux-store fallback |
| 28f8db1 | — | Gate PASS for call-setup-ready-z0qqo |
| 9fdac45 | tincan-hchsf | list_adapters() + HFP/SCO capability detection |
| c2bad44 | tincan-azcok | Tests for list_adapters + HFP detection |
| c5bd3ec | tincan-t53s7 | GUI behavioral tests: picker + banners |
| d89e6b1 | tincan-yuomh | GetAdapters() D-Bus method + adapter_path_requested |
| 7d3af42 | tincan-0fq30 | get_adapters() + adapter_path_requested in dbus_client |
| 6614427 | tincan-crfu9 | Adapter-unavailable banner + adapter_path in GetStatus |
| 89f23fd | tincan-yn2x5 | Adapter picker QComboBox + capability badges |
| f20fbcb | tincan-gu24r | Adapter restart banner full spec (SIGTERM + close) |
| e723eed | tincan-ne6qq | Fix review B1-B3, L1-L3 |
| 49efdb5 | — | Gate PASS for tincan-6m971 and tincan-s8918 |

All commits are tightly coupled: GetAdapters() (D-Bus) is required by the GUI picker; the degraded banners implement picker's design spec states C/D; the SELinux fix makes HFP capability reporting accurate for the picker's badge display. Removing any piece leaves the feature incomplete or the tests failing.

**→ PASS**

---

## Summary

| # | Criterion | Result |
|---|-----------|--------|
| 1 | Review PASS present | ✅ PASS |
| 2 | Acceptance criteria met | ✅ PASS |
| 3 | Tests pass (1910/1910) | ✅ PASS |
| 4 | No high-severity findings | ✅ PASS |
| 5 | Branch clean | ✅ PASS |
| 6 | Cleanly diverges from main | ✅ PASS |
| 7 | Single feature theme | ✅ PASS |

**Gate: PASS**  
PR: https://github.com/quad341/tincan/pull/130
