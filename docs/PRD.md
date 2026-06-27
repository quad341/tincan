# PRD: UI Bug Batch — Test Pass 2026-06-27 (tincan-m0rt8, tincan-fjv0n, tincan-2sfow, tincan-w1oxf, tincan-gadjv, tincan-uchl4)

**Status:** Draft
**Author:** tincan/planner
**Date:** 2026-06-27
**Source beads:** tincan-m0rt8, tincan-fjv0n, tincan-2sfow, tincan-w1oxf, tincan-gadjv, tincan-uchl4
**Type:** Bug fix batch
**Priority:** P2

---

## Problem Statement

Six bugs were surfaced during the 2026-06-27 UI test pass (`ui-testpass-20260627` label).
All are in the `tincan_gui` layer (PySide6 desktop client). None require changes to
`tincand` (the bridge daemon) or the D-Bus API — this is purely a GUI-side fix batch.

The bugs span four concern areas:

1. **Cached-conversation load (tincan-m0rt8)** — conversations may not appear on
   launch due to a suspected HOME-directory mislocation; needs investigation before
   any code change is committed.
2. **Disconnected-state guard for new conversations (tincan-fjv0n)** — the
   "compose new conversation" flow is reachable when no device is connected, which
   cannot succeed and will confuse users.
3. **Settings persistence and layout (tincan-2sfow, tincan-w1oxf)** — BT adapter/
   device combo-boxes truncate their labels, and the desktop-notifications toggle
   resets after the dialog is closed and reopened.
4. **Visual regressions (tincan-gadjv, tincan-uchl4)** — toolbar buttons lose their
   emoji glyphs on some Wayland/font configurations, and the BT settings panel shows
   an uninitialised orange rectangle between the adapter and device dropdowns.

**Who is affected:** All Linux desktop users of `tincan-gui` on a Wayland session
with PySide6.

---

## Goals

| # | Goal | Measurable Outcome |
|---|------|--------------------|
| G1 | Cached conversations appear on launch when launched with the operator's real HOME | Zero empty conversation list on launch with `HOME=/home/jaword` and a warm cache |
| G2 | New-conversation button/action is inert when no device is connected | Button is visually disabled AND keyboard shortcut is a no-op when `_connected_device == ""` |
| G3 | BT adapter and device dropdowns display their full labels without truncation | No text clipping in the closed (collapsed) state of either combo-box |
| G4 | Desktop-notifications toggle persists across settings open/close and app restart | Setting reads back the value written on the previous session |
| G5 | Toolbar buttons (gear ⚙, bug 🐞, bell 🔔) are visible on all tested Wayland/font configs | Buttons display their intended glyphs on a stock Fedora 44 Wayland session |
| G6 | No uninitialised orange rectangle in the BT settings panel | The adapter-restart banner is hidden on first open and is shown only after an adapter change |

## Non-Goals

- Changes to `tincand` or the internal D-Bus API
- Redesigning the settings dialog layout beyond fixing truncation and the spurious banner
- Adding new settings keys or persisting additional settings fields (only the existing `notifications/desktop_enabled` key is in scope)
- Supporting light-mode themes (dark mode is the only tested target)
- Internationalisation / l10n of any new or changed strings

---

## User Stories

| ID | Story |
|----|-------|
| US1 | As a user reopening the app after a prior session, I want my conversation history to appear immediately so I don't think the app lost my data. |
| US2 | As a user who opens the "New Conversation" dialog while my iPhone is still connecting, I want a clear, immediate signal that I cannot start a conversation yet rather than a silent failure. |
| US3 | As a user picking a Bluetooth adapter in Settings, I want to read the full adapter name in the dropdown without having to open it, so I can confirm I have the right adapter selected. |
| US4 | As a user who enables desktop notifications, I want that setting to still be on the next time I open Settings, so I don't have to re-enable it every session. |
| US5 | As a user on a standard Fedora 44 Wayland session, I want the toolbar buttons to be visually clear so I can identify settings, bug report, and notifications without guessing. |
| US6 | As a user opening Settings for the first time after launch, I want the BT section to look clean and informative rather than showing an unexplained orange box. |

---

## Functional Requirements

### Bug 1: Cached Conversations Not Shown (tincan-m0rt8)

**FR1.1 — Investigation gate (must happen before any code fix).**
Before writing a code fix, the implementer MUST relaunch `tincan-gui` with
`HOME=/home/jaword` (the operator's real home, not a per-agent overlay home) and
verify whether conversations still fail to appear. The suspicion is that the UI was
launched with `HOME=/home/jaword/mayor-claude` (a cohelper agent's overlay home),
so QSettings and the message cache read from the wrong directory.

- AC: If conversations appear correctly after the HOME fix → close tincan-m0rt8 as
  "not a code bug — environment issue only." No code change required.
- AC: If conversations still fail to appear with the correct HOME → proceed to root-
  cause the `message_cache.py` and QSettings read path; file a new bead for the
  actual code defect and close tincan-m0rt8 as the parent.

**FR1.2 — Result recorded in bead notes** before closing either way.

---

### Bug 2: New-Conversation Guard When Disconnected (tincan-fjv0n)

**FR2.1 — Disable the compose-new action when not connected.**
`ConversationList.compose_new_requested` and the corresponding UI entry point must
be gated on `MainWindow._connected_device != ""`. When no device is connected:

- The "New Conversation" toolbar button or list action must be visually disabled
  (greyed/dimmed).
- The signal must not be emitted (or `_on_compose_new` must check connection and
  return early without opening the dialog).

**FR2.2 — Re-enable when connection arrives.**
When `_on_daemon_connected` fires, the new-conversation entry point must immediately
become active — no restart required.

**FR2.3 — Tooltip or accessible description.**
When the entry point is disabled, its tooltip (or accessible description) must
explain why: e.g., "Connect a device to start a new conversation."

**Acceptance Criteria:**
- AC: With no connected device, clicking "New Conversation" does nothing / button
  is visually inactive.
- AC: After the daemon connects, the button becomes active without a restart.
- AC: Tooltip on the disabled state reads: "Connect a device to start a new
  conversation" (or equivalent).
- AC: Existing behaviour for compose (FR gated by `_sync_compose_state`) is
  unchanged.

---

### Bug 3: Settings Combo-Boxes Truncate Labels (tincan-2sfow)

**FR3.1 — Adapter combo minimum width.**
`_adapter_combo` in `settings_dialog.py` must have a minimum width set such that
the full text of any adapter label (e.g. `hci1 — A0:AD:9F:7A:15:8E — RTL8761BUH`)
is visible in the closed state without clipping.

**FR3.2 — Device combo minimum width.**
`_device_combo` must have the same treatment for full device names/addresses.

**FR3.3 — Implementation note (not an architecture decision, but a constraint):**
The fix must use Qt's `setSizeAdjustPolicy(AdjustToContents)` or an explicit
`setMinimumContentsLength(N)` / `setMinimumWidth(px)`. The `_AdapterItemDelegate`
already governs the *open* state row height; this fix governs only the *closed*
state width.

**Acceptance Criteria:**
- AC: Both combo-boxes display their full label text in the closed (collapsed) state
  without "…" truncation, for adapter labels up to ~60 characters.
- AC: The dialog still fits within a 480 px minimum width without horizontal
  scrollbars.

---

### Bug 4: Desktop Notifications Setting Does Not Persist (tincan-w1oxf)

**FR4.1 — Checkbox state must survive dialog close/reopen.**
When a user sets `Desktop notifications` to checked, closing and reopening the
settings dialog must restore the checkbox to checked.

**FR4.2 — Checkbox state must survive app restart.**
When a user sets the toggle and then quits and relaunches `tincan-gui`, the
checkbox must reflect the saved value.

**FR4.3 — QSettings write must be synchronous at dialog close (not just on toggle).**
Currently `_on_desktop_toggled` fires on each checkbox change, which saves the
value. If the dialog is opened and closed without changing the checkbox (no signal),
no re-save is needed. Verify the read path in `_settings.bool_value()` correctly
coerces the INI string `"true"/"false"` back to a Python bool.

**FR4.4 — Acceptance test: cross-session persistence.**
The implementer must manually verify: enable → quit → relaunch → open settings →
checkbox is checked. Disable → quit → relaunch → open settings → checkbox is
unchecked.

**Acceptance Criteria:**
- AC: Enabling the toggle, closing the dialog, reopening: checkbox is checked.
- AC: Enabling the toggle, quitting and relaunching: checkbox is checked.
- AC: QSettings key `notifications/desktop_enabled` is readable with `bool_value()`
  and returns the expected value on re-read.

**Note on shared root cause with adapter-selection persistence:** The bead description
flags that this MAY share a root cause with adapter-selection-not-persisting (an
adjacent symptom). The implementer should check whether `adapter/path` (or equivalent)
also suffers from the same read-back bug and file a sibling bead if so. Do not scope-
creep the fix here to include adapter persistence — that is a separate bead.

---

### Bug 5: Toolbar Buttons (Gear ⚙, Bug 🐞, Bell 🔔) Not Visible (tincan-gadjv)

**FR5.1 — Emoji glyphs must render on a stock Fedora 44 Wayland session.**
The three toolbar buttons use `QToolButton.setText()` with emoji characters (⚙, 🐞,
🔔) and an explicit `QFont` with `setFamilies()` calling `_emoji_font_families()`.
If those font families are absent on the test machine (no Noto Emoji / Segoe UI
Emoji installed), the glyphs render as empty boxes or blank.

**FR5.2 — Fallback strategy.**
The fix must ensure visible, labelled buttons on any PySide6/Qt Wayland session
without requiring the user to install additional fonts. Acceptable approaches
(implementation choice for the coder):

  a. Replace emoji text with `QIcon.fromTheme()` icons (e.g. `preferences-system`,
     `tools-report-bug`, `notification-new`) with a text fallback if the theme icon
     is absent.
  b. Embed small SVG/PNG assets for each button under `tincan_gui/assets/` and load
     via `QIcon(QPixmap(path))` — no font dependency.
  c. Ship a minimal emoji subset in `tincan_gui/assets/fonts/` and load it with
     `QFontDatabase.addApplicationFont()` before the buttons are constructed.

**FR5.3 — Buttons must remain keyboard-accessible.**
Whichever approach is chosen, `setAccessibleName()` on each button must remain
(already set: "Settings", "File a bug report", "Notification center").

**Acceptance Criteria:**
- AC: On a Fedora 44 Wayland test session (standard package set, no manual font
  installs), all three buttons display their intended glyph or an equivalent icon.
- AC: On a machine where Noto Color Emoji is installed, buttons render as before.
- AC: `accessibleName()` on each button returns its existing value.

---

### Bug 6: Empty Orange Rectangle in BT Settings HFP/LE Area (tincan-uchl4)

**FR6.1 — `_AdapterRestartBanner` must be hidden on first open.**
`_adapter_restart_banner` is constructed with `.hide()` already called at line 588.
If the orange rectangle is visible on first open, the bug is either:
  a. The banner's `show()` is called unconditionally during `__init__` via some
     indirect path, or
  b. The orange border (`border: 1px solid #f97316`) is visible on the
     `_adapter_unavailable_frame` QFrame (a different widget, also styled) even
     when the frame is logically hidden.

**FR6.2 — Root-cause and fix.**
The implementer must identify which widget is rendering the orange rectangle and
fix its initial visibility:

- If it is `_adapter_restart_banner`: trace the call path that calls `.show()` on
  it before any adapter change occurs and add a guard.
- If it is `_adapter_unavailable_frame`: verify its stylesheet (line 537: dark
  background, dark border, no orange) — if orange is leaking from a parent or
  sibling QFrame, isolate the style scope.
- If it is `_adapter_badge_row` showing stale text: ensure it remains hidden until
  `_populate_adapter_combo` runs.

**FR6.3 — Visible state contract.**
The orange restart banner may only be shown after `_on_adapter_changed()` has fired
at least once in the current dialog session. It must be hidden when the dialog first
opens and when `.hide()` is explicitly called (already wired to the "Later" button).

**Acceptance Criteria:**
- AC: Opening Settings with a connected adapter shows no orange rectangle between
  the adapter and device dropdowns.
- AC: Changing the adapter selection causes the restart banner to appear.
- AC: Clicking "Later" hides the banner.
- AC: Closing and reopening Settings hides the banner again (fresh dialog instance).

---

## Non-Functional Requirements

| ID | Requirement | Metric |
|----|-------------|--------|
| NFR1 | No regressions in existing settings-dialog tests | All tests in `tests/tincan_gui/test_app_notifications_settings.py` pass |
| NFR2 | Settings dialog opens in < 300 ms on the reference host | Measured from `_open_settings()` call to `dialog.show()` return |
| NFR3 | No additional pip dependencies | Fix must use PySide6 and stdlib only; no new packages |
| NFR4 | Dark-mode styling unchanged for all un-modified widgets | Visual diff against current dark-mode screenshots shows no regressions |

---

## Technical Constraints

*(derived from `docs/PROJECT_MANIFEST.md`)*

- **GUI client:** PySide6 (Qt for Python) — `tincan_gui`; pure client of the daemon.
- **Persistence:** User settings live client-side in `~/.config/tincan/tincan.ini`
  via `QSettings("tincan", "tincan")`. The daemon owns no settings.
- **No daemon changes in scope.** `tincand` must not be modified for this batch.
- **Python 3.14** — type hints on all new public methods.
- **Style:** `ruff` + `black` must pass on all changed files.
- **Wayland target:** Fedora 44, PySide6 (system or `.venv`), no X11 assumption.
- **Clean daemon/client boundary:** no business logic or BT state in the GUI.

---

## Dependencies

| # | Dependency | Needed For | Status |
|---|------------|-----------|--------|
| D1 | `QSettings("tincan","tincan")` in `~/.config/tincan/tincan.ini` | FR4 settings persistence | Existing |
| D2 | Qt theme icon set OR bundled SVG assets | FR5 toolbar visibility fallback | TBD — implementer choice |
| D3 | Running daemon (for FR2 connection-state test) | FR2 compose-guard integration test | Existing |

---

## Open Questions

| # | Question | Owner | Due |
|---|----------|-------|-----|
| OQ1 | Is tincan-m0rt8 actually a code bug? Must relaunch with correct HOME first. | implementer | Before starting FR1 code work |
| OQ2 | Does adapter-path selection ALSO fail to persist across dialog close? (may share root cause with tincan-w1oxf) | implementer | During FR4 investigation |
| OQ3 | Which icon approach is preferred for FR5 — theme icons, bundled assets, or embedded font? | coder / designer | Before implementing FR5 |
| OQ4 | On the test machine where tincan-gadjv was observed: is Noto Color Emoji installed? | operator | Flag during investigation |
| OQ5 | Is the orange rectangle in tincan-uchl4 the `_adapter_restart_banner` or a different widget? | implementer | Root-cause step of FR6 |

---

## Handoff Notes for Downstream Agents

These are all **GUI-layer bugs** in `tincan_gui`. No architecture decisions are needed
(the daemon/client boundary is not changing, no new D-Bus interfaces, no new domain
types). The following routing applies:

- **Architect:** Not required for this batch. All bugs are implementation-level
  within the existing PySide6 GUI layer.
- **Designer:** OQ3 (icon approach for FR5) requires a design call. Route tincan-uchl4
  and tincan-gadjv to the designer for a visual decision before the coder implements.
- **Coder:** FR1 (investigate first), FR2, FR3, FR4, FR6 can proceed directly to the
  coder once this PRD is accepted and OQ1/OQ5 are resolved.

**Implementation order recommendation (not a hard constraint):**
1. FR1 (investigate HOME issue) — cheapest, may close tincan-m0rt8 with no code
2. FR6 (orange rectangle) — likely a one-liner show/hide guard
3. FR3 (dropdown truncation) — pure layout, no logic change
4. FR4 (settings persistence) — verify read/write path; likely a `bool_value` coercion issue
5. FR2 (new-conversation guard) — small state check + UI update
6. FR5 (toolbar icons) — depends on OQ3 design decision

---

*PRD covers beads: tincan-m0rt8, tincan-fjv0n, tincan-2sfow, tincan-w1oxf, tincan-gadjv, tincan-uchl4*
