# Release Gate: tincan-5dus

**Feature:** GUI routing, timestamps, text selection, compose-new (tincan-w5c5/tw41/jm9t/pyn5)
**Bead:** tincan-5dus (source: tincan-ppg3)
**Commit:** 82ab5fe (already on main — local-only repo, direct-merge process)
**Gate run:** 2026-06-03
**Result:** PASS

## Gate Checklist

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | PASS | tincan-ppg3 closed with PASS verdict by all.reviewer; no HIGH findings |
| 2 | Acceptance criteria met | PASS | See detail below — all 4 sub-features verified in code |
| 3 | Tests pass | PASS | 578 pass, 3 fail — all 3 are pre-existing TestHealingToActive ANCS rearm failures (BLOCKER-3); no new failures introduced |
| 4 | No HIGH findings open | PASS | 0 HIGH findings per tincan-ppg3 review |
| 5 | Final branch clean | PASS | Local-only repo; 82ab5fe committed directly to main; `git status` clean aside from untracked infra files |
| 6 | Branch diverges cleanly from main | PASS | Commit already on main; no divergence |
| 7 | Single feature theme | PASS | All 4 sub-features address the same user-facing concern: correct message display and interaction in the GUI message layer (routing, timestamps, text selection, compose-new) |

## Criterion 2 Detail — Acceptance Criteria (4 sub-features)

### tincan-w5c5 — Message routing fix
**PASS** — `tincan_gui/main.py` `_on_message_received` (line 357): routing guard at line 364 skips messages where `conv_id != self._current_phone`; `_on_conversation_updated` (line 384) detects new `conv_id` not in `_conversations_by_id` and adds it to the list; `empty_label` explicitly hidden/shown in `load_thread`/`append_message`.

### tincan-tw41 — MAP timestamp parsing
**PASS** — `tincand/backends/bluez_map.py` `_parse_map_datetime()` at line 98 converts MAP `YYYYMMDDTHHMMSS` format to `HH:MM`; called at lines 240 and 260 for both inbox and sent messages.

### tincan-jm9t — Text selection and link clickability
**PASS** — `tincan_gui/thread_view.py` `_linkify()` at line 28 wraps `https?://` URLs in `<a>` tags; `MessageBubble` body labels set `Qt.TextInteractionFlag.TextBrowserInteraction` (line 128); `setText(_linkify(...))` with `RichText` format (line 130).

### tincan-pyn5 — Compose-new button
**PASS** — `tincan_gui/conversation_list.py` emits `compose_new_requested` signal (line 269); '+' button connected to signal emit (line 320); `tincan_gui/main.py` `_on_compose_new()` at line 436 shows `QInputDialog` for phone number and opens a blank thread.

## Criterion 3 Detail — Pre-existing Test Failures

```
FAILED tests/tincand/test_ancs_backend.py::TestHealingToActive::test_rearm_success_calls_set_capability_ancs_true
FAILED tests/tincand/test_ancs_backend.py::TestHealingToActive::test_rearm_success_clears_heal_timer_id
FAILED tests/tincand/test_ancs_backend.py::TestHealingToActive::test_rearm_success_resets_ancs_needs_repair
```

All three are pre-existing ANCS rearm failures tracked as BLOCKER-3. The commit message for 82ab5fe noted "12 = 3 ANCS healing + 9 live-daemon env" failures at build time; the 9 live-daemon env failures were subsequently fixed by tincan-bsti (b939a8c), so the current run shows only 3.

## Decision

Gate **PASS**. Commit 82ab5fe is on main. Bead closed.
