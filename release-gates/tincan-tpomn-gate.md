# Release Gate: tincan-tpomn

**Feature:** contact names auto-resolve on MAP first poll  
**Deploy bead:** tincan-rhtcf  
**Source bead:** tincan-tpomn  
**Commit:** `5ea0433` (cherry-picked as `1b86e25` on `feature/tincan-tpomn`)  
**Branch:** `feature/tincan-tpomn` off `origin/main` (`678c379`)  
**Gate date:** 2026-06-04  
**Result: PASS**

---

## Criterion 1 — Review PASS present

| Reviewer | Verdict | Evidence |
|----------|---------|----------|
| tincan/all.reviewer (Claude Sonnet 4.6) | PASS | Review bead tincan-t36xt; notes: "REVIEW VERDICT: PASS" — 841/841 tests, ruff clean, logic correct |

✅ **PASS** — First-pass review PASS present. (Second-pass reviewer disabled.)

---

## Criterion 2 — Acceptance criteria met

**Acceptance:** "contact names show without a manual refresh."

**Root cause addressed:** `_emit_messages` was building `Conversation` objects using the raw MAP Sender field (phone number) even when PBAP had already populated `_contact_store` with resolved names. PBAP fires via `GLib.idle_add` (~1–3s), MAP polls at 5s — so by first poll the store has names but `_conversations` is empty, making `update_contact()` a no-op. Fix: in `_emit_messages`, for phone-keyed senders, call `_contact_store.resolve_name(sender)` and prefer that over MAP Sender when available.

**Tests added (§7):**
- §7.1 phone-keyed sender with resolved PBAP name → `display_name` = PBAP name ✓
- §7.2 phone-keyed sender without PBAP entry → `display_name` = MAP Sender ✓
- §7.3 name-keyed sender (not phone) → `display_name` unchanged (no store lookup) ✓

✅ **PASS**

---

## Criterion 3 — Tests pass

**Command:** `python -m pytest tests/ --tb=short -q`

**Feature branch result:** 2 failed, 779 passed (781 collected)

**Baseline (`origin/main`) result:** 2 failed (same tests — verified by reverting to origin/main)

**Pre-existing failures (not introduced by this commit):**
- `tests/tincan_gui/test_ancs_capability.py::TestStateCBannerStatusChip::test_chip_shows_connected_limited_when_ancs_false`
- `tests/tincan_gui/test_desktop_notifications.py::TestSettingsDialogAccessibility::test_appearance_section_has_no_interactive_controls`

**Net new failures introduced by 5ea0433:** 0

The §7 tests added by this commit (3 cases) all pass.

Note: builder ran 841/841 on local `main` (which carries additional later commits not yet shipped); the feature branch carries only `origin/main` + this cherry-pick, hence 781 collected.

✅ **PASS** — no regression vs baseline

---

## Criterion 4 — No high-severity review findings open

Review findings from tincan-t36xt:
- **Informational (non-blocking):** `_norm_phone` (last-10-digits) and `normalize_phone` (strip US/CA country code) diverge for non-US/CA international numbers — pre-existing inconsistency, not introduced by this commit.
- No HIGH findings.

✅ **PASS** — 0 unresolved HIGH findings

---

## Criterion 5 — Final branch is clean

```
$ git status
On branch feature/tincan-tpomn
Your branch is ahead of 'origin/main' by 1 commit.
nothing to commit, working tree clean
```

✅ **PASS**

---

## Criterion 6 — Branch diverges cleanly from main

Cherry-pick of `5ea0433` onto `origin/main` (`678c379`) completed with no conflicts.

```
Auto-merging tincand/backends/bluez_map.py
[feature/tincan-tpomn 1b86e25] fix(map): use PBAP-resolved name in _emit_messages (tincan-tpomn)
 2 files changed, 88 insertions(+)
```

✅ **PASS**

---

## Criterion 7 — Single feature theme

Single commit, single subsystem: MAP backend (`tincand/backends/bluez_map.py`) + associated tests. The change adds contact-name resolution at the point where conversations are first built. No other subsystems touched.

✅ **PASS**

---

## Gate summary

| # | Criterion | Result |
|---|-----------|--------|
| 1 | Review PASS present | ✅ PASS |
| 2 | Acceptance criteria met | ✅ PASS |
| 3 | Tests pass (no regression) | ✅ PASS |
| 4 | No high-severity findings | ✅ PASS |
| 5 | Final branch clean | ✅ PASS |
| 6 | Branch diverges cleanly from main | ✅ PASS |
| 7 | Single feature theme | ✅ PASS |

**Overall: PASS — proceed with PR.**
