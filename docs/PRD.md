# PRD: 2026-06-27 Test-Pass Bug Cluster

**Status:** Draft  
**Author:** tincan/planner  
**Date:** 2026-06-27  
**Source beads:** tincan-zdvh9 (P1), tincan-w1oxf, tincan-2sfow, tincan-gadjv, tincan-uchl4, tincan-fjv0n, tincan-m0rt8 (all P2)  
**Type:** Bug-fix batch — UI test pass 2026-06-27  
**Priority:** P1 blocker (tincan-zdvh9) + P2 polish

---

## Problem Statement

A UI test pass on 2026-06-27 surfaced seven defects across Bluetooth settings, connection UX,
and general UI rendering. One is a P1 test-pass blocker; six are P2 polish items identified in
the same session. All were filed against the same `tincan-gui` PID (`1220658`) with
`current_phone=""`, `connected_device=""`, `messages_ok=false` — the app was running but
never connected.

**Affected user:** Operator with a dual-adapter setup (MT7925 built-in + RTL8761B dongle)
on roglet (Fedora/Wayland, PySide6). iPhone not connected during the session.

**Context:** Most of these regressions are traceable to PR #144 ("resilient tincand bring-up —
adapter mismatch banner + BT device picker"), which added substantial new code paths in
`settings_dialog.py`, `main.py`, `degradation_banners.py`, and `dbus_service.py`.

---

## Goals

| # | Goal | Measurable Outcome |
|---|------|--------------------|
| G1 | Adapter selection persists across settings-close and app restart | QSettings key `bluetooth/adapter_path` reads back the correct path after dialog close; on restart the daemon receives the saved path |
| G2 | Reconnect button gives immediate visible feedback | Button enters a "reconnecting" visual state within one render frame; user can see the action was registered |
| G3 | Status banner reflects true connection failure cause, not a hardcoded "out of range" | "Bluetooth out of range" text does not appear when the device is known to be in range but disconnected for other reasons |
| G4 | Desktop notifications toggle persists across settings-close and app restart | `notifications/desktop_enabled` reads back the saved value on next dialog open |
| G5 | Adapter and device combo-boxes display full text without truncation | Each combo has a minimum width sufficient to show typical Bluetooth adapter aliases and MAC addresses unclipped |
| G6 | Toolbar icon buttons (settings ⚙, bug 🐞, notifications 🔔) are visible on the target platform | Buttons render their glyph or fallback text visibly on Wayland/PySide6/Fedora |
| G7 | HFP/LE capability area renders correctly when disconnected | No orange rectangle appears when no adapter data is loaded; the capability row is hidden or shows a placeholder |
| G8 | "New Conversation" dialog is not accessible when disconnected | The compose-new button/action is disabled (or a clear inline message is shown) when `connected_device` is empty |

## Non-Goals

- Fixing the underlying Bluetooth connection failure itself (that is the operator's environment; no code bug is confirmed)
- Changing the adapter selection UX flow (restart-required banner, etc.) beyond fixing persistence
- Adding retry logic or exponential backoff to `RequestReconnect`
- iMessage or other protocol work

---

## User Stories

| ID | Story |
|----|-------|
| US1 | As a user who switches BT adapters in Settings, I want to reopen Settings and see my choice still selected so I know the UI is trustworthy. |
| US2 | As a user who clicks Reconnect, I want some immediate visual response so I know the app received my action. |
| US3 | As a user who sees a banner saying "Bluetooth out of range," I want that to be true — I should not see that message when my phone is sitting on the desk next to the computer. |
| US4 | As a user who enabled desktop notifications, I want that setting to survive closing and reopening the Settings panel. |
| US5 | As a user who cannot figure out what the orange box in BT Settings is for, I want it to either show useful content or not appear at all. |

---

## Bug Cluster A — P1 Blocker: BT Adapter Selection + Connection (tincan-zdvh9)

**Source bug reports:** bug-1782587130 (selection doesn't stick), bug-1782587215 (false "out of
range"), bug-1782587250 (reconnect no feedback, wrong adapter shown)

### FR-A1 — Adapter selection must round-trip correctly

When the user changes the adapter combo and closes Settings, re-opening Settings must show
the newly selected adapter.

**Technical context (planner's findings):**

- `_on_adapter_changed` (settings_dialog.py:932) calls `s.setValue("bluetooth/adapter_path", path); s.sync()`. The write is correct.
- `_populate_adapter_combo` (settings_dialog.py:882) selects by `a.get("is_selected") OR (saved_path and path == saved_path)`. Since it's `OR` and the loop keeps overwriting `selected_idx`, the last adapter satisfying either condition wins. If the daemon reports the OLD adapter as `is_selected=True` and QSettings has the NEW adapter as `saved_path`, both adapters match and the NEW adapter wins (last match) — which is correct.
- **Suspected failure mode:** `get_adapters()` returns an empty list (daemon not running or D-Bus unavailable), causing `_populate_adapter_combo` to take the "no adapters" branch (line 841–848) and hide the combo entirely. The selection "disappears" visually even though QSettings has the right value.
- **Architect task:** Determine whether (a) the daemon is failing to start/respond, (b) `get_adapters()` has a bug when the daemon is running but disconnected, or (c) there is a race condition between the dialog opening and the async adapter load thread (`_AdapterLoader`). Confirm the correct fix.

**Acceptance criteria:**
1. After changing adapter in Settings and closing the dialog, reopening Settings shows the new adapter selected.
2. After an app restart (with daemon restarted), the adapter resolved by the daemon matches the QSettings value.
3. If no adapters are returned by the daemon, the combo hides cleanly — when the adapter list later loads (e.g., via Refresh), the saved adapter is pre-selected.

### FR-A2 — "Bluetooth out of range" banner must not appear for non-range failures

`StateABanner` (degradation_banners.py:40-54) emits "⊗ Connection lost — Bluetooth out of
range" and "· Bluetooth out of range · reconnecting…" for ALL disconnected states regardless
of cause.

**Technical context:**

- `main.py:715`: `self._banner_a.show()` is called in `_on_daemon_status` whenever `connected=False`. There is no signal from the daemon distinguishing "device genuinely out of range" from "connection failed for another reason."
- The daemon's `GetStatus()` returns `adapter_warning` (set by `verify_dongle_adapter` via the mismatch path) but does not expose a `disconnect_reason` field.

**Acceptance criteria:**
1. When the device has never connected during a session (no prior `daemon_connected` signal), the banner must not say "out of range." It should say something neutral like "Not connected" or "No device paired."
2. "Bluetooth out of range" text is reserved for a confirmed range/signal loss (TBD by architect — may require a daemon-side disconnect reason field, or a heuristic such as: "out of range" only after a previously-successful connection is lost).
3. The banner text in the reconnecting state must not contradict what the operator can physically observe.

**Open question for architect:** Should the daemon expose a `disconnect_reason` field in `GetStatus()`, or should the GUI infer from connection history (was there ever a `daemon_connected` event this session)?

### FR-A3 — Reconnect button must give immediate visual feedback

`_on_reconnect_clicked` (main.py:999) calls `request_reconnect()` with no visual state change.

**Acceptance criteria:**
1. Within one render frame of clicking Reconnect, the button enters a visually distinct state (disabled, spinner, text change to "Reconnecting…", or equivalent).
2. The button returns to its normal state after a timeout or after a `daemon_connected` / `daemon_disconnected` signal.
3. The behavior matches the existing `ANCSRepairBanner.set_reconnecting(True)` pattern already implemented for the ANCS repair banner (main.py:1004).

**Note:** `ANCSRepairBanner.set_reconnecting()` is already wired at main.py:1004 and provides a reference implementation. `StateABanner` should adopt the same pattern.

---

## Bug Cluster B — P2: Settings Persistence (tincan-w1oxf)

**Source bug report:** bug-1782587308 (desktop notifications toggle resets)

`_on_notif_toggled` (settings_dialog.py:798–802) saves to QSettings. On re-open, line 388–390
reads the value back. The write path looks correct.

**Suspected failure mode:** Same root cause as FR-A1 — if the app was launched with a non-standard
`HOME` (see tincan-m0rt8 below), `QSettings("tincan", "tincan")` resolves to
`$HOME/.config/tincan/tincan.ini` using the wrong home directory. Writes go to the wrong path;
on the next session (with correct HOME), they are not visible.

**Acceptance criteria:**
1. After toggling desktop notifications ON and closing Settings, re-opening Settings shows the toggle still ON.
2. After an app restart, the toggle retains its last-saved state.
3. If the root cause is a shared QSettings path issue with FR-A1, a single fix covers both.

**Architect note:** Confirm whether `QSettings("tincan", "tincan")` uses `QStandardPaths` internally
(which respects `QCoreApplication::setOrganizationName`) vs. bare `$HOME`. If HOME mismatch is
the cause, verify whether the daemon launcher or systemd unit is setting HOME incorrectly.

---

## Bug Cluster C — P2: UI Rendering (tincan-2sfow, tincan-gadjv, tincan-uchl4)

### FR-C1 — Adapter and device combos must not clip their content (tincan-2sfow)

**Source:** bug-1782587278 (dropdowns too short, text cut off when closed)

The `QComboBox` widgets for adapter and device (settings_dialog.py:555, 626) have no
`setMinimumWidth()` or `setMinimumContentsLength()` set. PySide6 sizes them to the current
item's pixel width, which may be narrower than needed.

**Acceptance criteria:**
1. Both the adapter combo and device combo display their full text (adapter alias + MAC, device MAC + name) without horizontal clipping when the combo is in its collapsed (closed) state.
2. Minimum approach: `setMinimumContentsLength(N)` where N is chosen so that a typical "RTL8761B Bluetooth Adapter (A0:AD:9F:7A:15:8E)" string is not clipped. Alternatively, `setSizeAdjustPolicy(AdjustToContents)` with `setMinimumWidth(280)` or similar.
3. The fix must not break the two-line rich delegate for the adapter combo (the `_AdapterItemDelegate.sizeHint` at settings_dialog.py:257 already returns h=50px; width is separate).

### FR-C2 — Toolbar icon buttons must be visible (tincan-gadjv)

**Source:** bug-1782587181 (settings ⚙, bug 🐞, notifications 🔔 icons not visible)

The toolbar uses emoji glyphs rendered via `_emoji_font_families()` (imported from
`thread_view.py`). On the test machine (Wayland / Fedora / PySide6), the glyphs may not
render due to font resolution failure.

**Technical context:**
- `_TitleBar.__init__` (main.py:167–214) sets `_gear_font.setFamilies(_emoji_font_families())` on the gear button, and `_emoji_btn_font.setFamilies(_emoji_font_families())` on bug and bell.
- `_emoji_font_families()` returns a list of candidate font family names. If none of the candidates are installed or mapped by the font manager under Wayland, the text may render as empty or as tofu.

**Acceptance criteria:**
1. The ⚙, 🐞, and 🔔 glyphs (or equivalent visible symbols) are rendered on the title bar on the reference platform (Fedora, Wayland, PySide6).
2. If `_emoji_font_families()` fails to find a matching font, the buttons must fall back to visible ASCII alternatives (e.g., "☰", "[S]", "B", "N") rather than rendering as invisible.
3. Architect to determine whether the fix is: (a) adding missing font families to `_emoji_font_families()`, (b) shipping the Noto Emoji font as a bundled asset, or (c) switching to QIcon-based rendering.

### FR-C3 — No orange rectangle in BT capability area when disconnected (tincan-uchl4)

**Source:** bug-1782587426 (empty orange rectangle between adapter and device dropdowns)

Between the adapter combo and device combo, there are several widgets:
`_adapter_badge_row` (QLabel, amber text), `_adapter_powered_off_badge`, `_adapter_restart_banner`,
`_adapter_mismatch_annotation` (color: #f59f00 amber). One or more of these appears as an orange
rectangle without useful text when the daemon is disconnected and adapter data is unavailable.

**Acceptance criteria:**
1. When no adapter data is available (daemon unreachable or adapter list empty), no orange/amber widget is visible between the adapter combo and device combo.
2. The `_adapter_mismatch_annotation` (amber QLabel) and any other capability rows must only be visible when they have content to display.
3. Architect to identify which specific widget is rendering the empty orange rectangle and ensure the show/hide logic is correct for the disconnected-at-startup case.

---

## Bug Cluster D — P2: UX Guard (tincan-fjv0n)

**Source:** bug-1782587362 (can start new conversation while disconnected)

`_on_compose_new` (main.py:1377) opens `NewConversationDialog` unconditionally regardless of
connection state. The compose-new button is connected via
`self._conv_list.compose_new_requested.connect(self._on_compose_new)` (main.py:647) with no
gating on `self._connected_device`.

**Acceptance criteria:**
1. When `connected_device` is empty (no active BT connection), the "New Conversation" action is disabled, or clicking it shows a clear inline message (e.g., "Connect to your iPhone first") rather than opening the contact dialog.
2. The disable/guard must be updated dynamically: if the device connects during a session, the action becomes available; if it disconnects, it becomes unavailable again.
3. The approach (disable button vs. error-on-click) is a design decision — route to designer for a recommendation before implementing.

---

## Bug Cluster E — P2: Investigation Required (tincan-m0rt8)

**Source:** bug-1782587328 (no cached conversations shown)

The triage note on this bead identifies a likely HOME-directory artifact: the GUI instance
during the test pass appears to have been launched with `HOME=/home/jaword/mayor-claude`
(the cohelper overlay home) rather than the operator's `HOME=/home/jaword`. This would cause:
- `QSettings("tincan", "tincan")` to write to `/home/jaword/mayor-claude/.config/tincan/tincan.ini`
- The conversation cache (stored under `$HOME/.local/share/tincan/`) to be empty (wrong directory)

**This may also explain tincan-w1oxf (notifications toggle resets) and tincan-zdvh9
(adapter selection doesn't persist)** if all bugs were filed during the same session with
the wrong HOME.

**Required action (not yet a code fix):**
1. Relaunch the GUI with `HOME=/home/jaword` explicitly.
2. Confirm whether cached conversations appear.
3. If they do: the bug is an operator-environment issue, not a code bug. Close tincan-m0rt8 as "not-a-bug". Investigate whether tincand's launcher or the gc rig harness is injecting a wrong HOME.
4. If conversations still do not appear with the correct HOME: re-open as a genuine code bug and file a new bead for the architect.

**Note:** If the wrong HOME IS confirmed as the root cause of the persistence bugs (tincan-w1oxf,
tincan-zdvh9), those beads may also be partially environmental and should be re-investigated under
the correct HOME before code fixes are made.

---

## Technical Constraints

Derived from `docs/PROJECT_MANIFEST.md`:

- **GUI is a thin client**: `tincan_gui` must not import `dbus.SystemBus()` directly; all
  BlueZ/daemon queries go through `dbus_client.py`.
- **QSettings scope**: `QSettings("tincan", "tincan")` is the shared settings namespace.
  The daemon uses `DaemonSettings` (a separate scope). GUI must never read from `DaemonSettings`
  directly (except the existing device-address lookup via an in-process import in the device combo,
  which the architect should review).
- **Daemon owns Bluetooth**: The GUI only reflects daemon state; it does not make BlueZ calls.
- **PySide6 (Qt for Python)**: UI must work on PySide6 ≥ 6.x; no PyQt5 patterns.

---

## Dependencies

- **PR #144 code** (`b7ef11a`) is the introducing commit for most of these regressions; the
  architect should use it as the boundary for blame analysis.
- **`verify_dongle_adapter`** (fixed in PR #142) is NOT implicated here; the `connect_status`
  field is already adapter-aware.
- **Firmware/driver for RTL8761B dongle** is not a tincan concern.

---

## Open Questions

| # | Question | Owner |
|---|----------|-------|
| OQ1 | Does the test-pass session's wrong HOME explain the persistence bugs (tincan-m0rt8, tincan-w1oxf, tincan-zdvh9)? | Operator — relaunch and verify |
| OQ2 | Should the daemon expose a `disconnect_reason` field to distinguish "out of range" from other failures? | Architect |
| OQ3 | Should the "New Conversation" guard be a disabled button or an error-on-click UX? | Designer |
| OQ4 | Is `_emoji_font_families()` returning a list that works on Fedora/Wayland? What font package is required? | Architect |
| OQ5 | Which specific widget is the "orange rectangle" (tincan-uchl4)? `_adapter_mismatch_annotation`, `_adapter_badge_row`, or something else? | Architect — read settings_dialog.py show/hide paths |

---

## Routing

| Bead | Target | Label | Rationale |
|------|--------|-------|-----------|
| Arch bead (A + B + C2 + C3 root cause) | tincan/architect | `needs-architecture` | Adapter persistence, reconnect feedback, disconnect_reason API, emoji font, orange rectangle — all require code-level root-cause analysis |
| Design bead (C1 + D + C2 fallback) | tincan/designer | `needs-design` | Combo minimum width spec, "compose new while disconnected" guard UX, icon fallback visual spec |
| tincan-m0rt8 | Operator re-test | — | Verify HOME before filing architecture work |
