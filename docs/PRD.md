# PRD: Calls UI — Arbitrary Dialpad + Per-Thread Dial Button (tincan-8dehj)

**Status:** Draft
**Author:** tincan/planner
**Date:** 2026-06-29
**Source bead:** tincan-8dehj
**Type:** Feature (UI — calls)
**Priority:** P2

---

## Problem Statement

Tincan supports outbound HFP calls at the daemon level (`im.tincan.Calls.Dial` over
D-Bus; `dbus_client.dial()` at `dbus_client.py:771`) but the GUI has no way to
initiate one. The in-call panel (`InCallPanel`, `IncomingCallDialog`) is incoming-only.
The existing `DTMFKeypad` widget (`call_panel.py:600`) appends tones mid-call; its
display is `setReadOnly(True)` — it is not a pre-dial number-entry UI.

Two distinct gaps exist:

1. **No arbitrary dialer.** There is no way to type a phone number and place an
   outbound call from the desktop — equivalent to opening the Phone app and dialling
   manually.

2. **No per-thread Dial action.** When a 1:1 conversation is open, there is no direct
   "call this contact" affordance. The user must know the phone number and enter it
   manually elsewhere.

A group SMS thread has no single dialable number, so any Dial action must be absent
or disabled there.

**Who is affected:** All tincan desktop users who want to place outbound calls via
their paired iPhone, whether to an existing contact in a thread or to an arbitrary
number.

---

## Goals

| # | Goal | Measurable Outcome |
|---|------|--------------------|
| G1 | User can place a call to any arbitrary phone number from the GUI | A number-entry dialpad is reachable from the main window and successfully calls `dbus_client.dial()` on accept |
| G2 | User can call a thread's contact in one action from a 1:1 conversation | A visible "Dial" button in the 1:1 thread view calls `dbus_client.dial(_current_phone)` when tapped |
| G3 | Group threads present no confusing or broken Dial affordance | Dial button is hidden (preferred) or disabled with tooltip on group threads (`is_group=True`) |
| G4 | Call flow transitions seamlessly into `_enter_call()` | After `dial()` returns a call_id, the GUI transitions to the `InCallPanel` without requiring a manual trigger |
| G5 | Dialpad is inert when calls capability is unavailable | Button and dialpad are disabled when `_call_setup_ready=False` (SELinux module absent) with an explanatory tooltip |

## Non-Goals

- Changes to `tincand` or the D-Bus API (daemon-side `Calls.Dial` already works)
- Mid-call DTMF changes — `DTMFKeypad` is in scope only as a reference; do not
  modify it for this feature
- Voicemail dialling, extension codes, or SIP/VoIP (HFP-only scope)
- A full contacts browser inside the dialpad (arbitrary number entry is sufficient)
- Implementing the outbound-call-answered flow (the existing `_enter_call` path
  handles it; this feature only adds the trigger)
- Internationalisation / number formatting (E.164 normalisation is not in scope for
  this iteration)

---

## User Stories

| ID | Story |
|----|-------|
| US1 | As a user, I want to open a dialpad from the main window and enter any phone number so that I can place a call to a number not in my conversation list. |
| US2 | As a user reading a 1:1 message thread, I want a single tap to call that contact so that I don't have to manually copy and enter their number elsewhere. |
| US3 | As a user in a group thread, I want the UI to be clear that I cannot call "the group" so that I don't waste time looking for a broken Dial button. |
| US4 | As a user whose HFP setup is not complete (SELinux module not loaded), I want a clear explanation of why calling is unavailable so I know what to fix. |
| US5 | As a user who initiates a call, I want the in-call panel to appear automatically so I'm not left staring at the compose view after dialling. |

---

## Functional Requirements

### FR1 — Arbitrary Dialpad

**FR1.1 — Dialpad entry point.**
A dialpad button or action must be accessible from the main window's toolbar or
conversation-list header area. It is always available (subject to FR1.5), regardless
of which conversation is open.

**FR1.2 — Dialpad UI.**
The dialpad must provide:
- A phone-number input field (editable; not `setReadOnly(True)`)
- `0–9`, `*`, `#` keys (12-key numeric grid — designer specifies exact layout)
- A "Call" / "Dial" confirm action that calls `dbus_client.dial(entered_number)`
- A cancel / dismiss action
- A backspace key or gesture to delete the last character

**FR1.3 — Number validation.**
The "Call" action must be disabled (greyed) if the entered string does not satisfy
`_is_dialable()` (`main.py:69` — ≥4 contiguous digits after stripping non-digit
characters). No error dialog needed; disabling the button is sufficient.

**FR1.4 — Keyboard input.**
The number input field must accept direct keyboard digit input without requiring
on-screen key taps. `Return` / `Enter` must trigger "Call" when the field is dialable.

**FR1.5 — Capability gate.**
When `_call_setup_ready=False` (daemon reported `call_setup_ready=False` in
capabilities), the dialpad entry point must be disabled with a tooltip:
`"Call setup incomplete — load the tincan HFP SELinux module to enable calls."` or
equivalent. The designer may choose to show a banner instead of a tooltip.

**FR1.6 — Post-dial transition.**
After `dbus_client.dial()` returns a non-empty call_id, the dialpad must close and
`_enter_call()` (`main.py:1564`) must be invoked to show the in-call panel. Error
handling: if `dial()` returns empty string (daemon-side failure), the dialpad stays
open and shows an inline error (designer decides exact copy/position).

---

### FR2 — Per-Thread Dial Button on 1:1 Conversations

**FR2.1 — Dial button placement.**
A "Dial" (phone) button must appear within the active conversation area when a 1:1
thread is open (`is_group=False`). Designer specifies exact placement — candidate
locations: thread header bar, compose bar alongside the Send button, or a dedicated
action row above the compose widget.

**FR2.2 — 1:1-only visibility.**
The Dial button must be:
- **Visible** when `is_group=False`
- **Hidden** (strongly preferred) when `is_group=True`

If hidden-vs-disabled is a non-obvious choice in context, designer may prefer
disabled-with-tooltip (`"Can't call a group thread"`), but hidden is the preferred
default to avoid clutter.

**FR2.3 — Dialable guard.**
When `_current_phone_dialable=False` (the thread's phone string is a raw name
unresolvable to a number), the Dial button must be disabled with a tooltip:
`"Phone number unavailable for this contact"` or equivalent. This mirrors the
existing compose-guard at `main.py:773-779`.

**FR2.4 — Call setup guard.**
When `_call_setup_ready=False`, the Dial button must be disabled (same gate as
FR1.5). Tooltip: same wording as FR1.5.

**FR2.5 — Action: dial thread contact.**
On click (when all guards pass), the button must call `dbus_client.dial(_current_phone)`
and then follow the same post-dial transition as FR1.6.

**FR2.6 — State synchronisation.**
The button's enabled/disabled/hidden state must update immediately when:
- A conversation is opened or closed (selected_phone changes)
- The daemon reports a new capabilities dict (call_setup_ready changes)
- The daemon connects or disconnects

---

### FR3 — Outbound Call Transition

**FR3.1 — `_enter_call()` wiring for outbound.**
The existing `_enter_call(caller_name)` method (`main.py:1564`) must be callable for
outbound calls. Currently it is only triggered from incoming-call signals. The
builder must wire the outbound path so that after `dial()` succeeds, `_enter_call()`
is invoked with the callee's resolved name (from `_conversations_by_id` if available,
otherwise the raw number).

**FR3.2 — In-call panel shows outbound direction.**
The in-call panel must correctly show the call as outbound (not display it as an
unknown incoming call). The existing `add_call(call_id, number, direction, state)`
on `InCallPanel` accepts a `direction` parameter; the builder must pass `"outbound"`.
This is a builder concern, but the PRD flags it to prevent the designer
from designing an "incoming" variant for outbound.

---

## Non-Functional Requirements

| ID | Requirement | Metric |
|----|-------------|--------|
| NFR1 | Dialpad opens in < 200 ms from button click | Measured from click to dialog/panel fully painted |
| NFR2 | No new pip dependencies | PySide6 + stdlib only |
| NFR3 | All new buttons have `setAccessibleName()` | Screenreader accessible; checked in tests |
| NFR4 | No regressions in existing call panel tests | All tests in `tests/tincan_gui/` touching `call_panel` pass |
| NFR5 | Dial button state is covered by a pytest-qt behavioural test | Test invokes state change + asserts enabled/visible, not just widget existence |

---

## Technical Constraints

*(derived from `docs/PROJECT_MANIFEST.md`)*

- **GUI client:** PySide6 (Qt for Python) — `tincan_gui`; pure client of the daemon.
- **Daemon boundary:** `dbus_client.dial(number)` is the only call surface; no daemon
  changes are in scope.
- **Calling is phase 3:** The daemon HFP path is implemented; this feature is the
  missing GUI trigger layer only.
- **`_is_dialable(s)` (`main.py:69`):** Validation predicate to reuse for the dialpad
  input guard (FR1.3) — do not duplicate.
- **`_enter_call(caller_name)` (`main.py:1564`):** Must be reused for the outbound
  post-dial flow — do not duplicate.
- **`_call_setup_ready` flag (`main.py:534,807`):** Capability gate populated from
  daemon `call_setup_ready` cap key; guards all call actions.
- **Group thread detection:** `conv_data.is_group` (`ConversationData`); already
  available at conversation-open time.
- **Python 3.14, ruff + black** must pass on all changed files.
- **Dark-mode only** — Wayland/Fedora 44, no light mode.

---

## Dependencies

| # | Dependency | Needed For | Status |
|---|------------|-----------|--------|
| D1 | `dbus_client.dial(number)` | FR1.6, FR2.5 — place outbound call | Exists (`dbus_client.py:771`) |
| D2 | `_enter_call(caller_name)` | FR3.1 — transition to in-call UI | Exists (`main.py:1564`); needs outbound wiring |
| D3 | `_is_dialable(s)` | FR1.3 — validate dialpad input | Exists (`main.py:69`) |
| D4 | `_call_setup_ready` flag | FR1.5, FR2.4 | Exists (`main.py:534`); populated from daemon caps |
| D5 | `conv_data.is_group` | FR2.2 — hide Dial on group threads | Exists in `ConversationData` |
| D6 | Designer: dialpad layout spec | FR1.2 — number-entry UI | **Required — this PRD routes to designer** |
| D7 | Designer: Dial button placement spec | FR2.1 — thread action placement | **Required — this PRD routes to designer** |

---

## Open Questions

| # | Question | Owner | Due |
|---|----------|-------|-----|
| OQ1 | Should the arbitrary dialpad be a modal dialog, a side panel, or a popover? The designer must decide given the existing compose-stack / call-stack layout in `MainWindow`. | designer | Before builder starts |
| OQ2 | Should the per-thread Dial button show a phone icon, a label "Call", or both? What is the correct disabled-vs-hidden policy for group threads? | designer | Before builder starts |
| OQ3 | When `dial()` fails (daemon returns empty call_id), should the error be inline in the dialpad, a toast/snackbar, or a QMessageBox? | designer | Before builder starts |
| OQ4 | For outbound calls that connect, `_enter_call(caller_name)` is currently populated from incoming-call signals. What caller name should be shown for an outbound call placed to an unknown number (not in contacts)? Fallback = raw number string. | builder | Implementation |
| OQ5 | Should the dialpad entry point be in the toolbar (always visible), or only visible in the conversation area when calls are available? | designer | Before builder starts |

---

## Handoff Notes for Downstream Agents

This feature requires **design work only** before the builder can act. No architecture
changes are needed — the daemon D-Bus API is complete, and all required GUI hooks
(`dial()`, `_enter_call()`, `_is_dialable()`) exist.

**Architect:** Not required. The daemon/client boundary is unchanged; no new D-Bus
interfaces or domain types needed.

**Designer:** Two UI elements need a visual spec:
1. The **arbitrary dialpad** — modal dialog, panel, or popover; number-entry field +
   12-key grid + Call/Cancel/Backspace actions.
2. The **per-thread Dial button** — placement within the 1:1 conversation view;
   icon, label, enabled/hidden state rules.

The designer must resolve OQ1–OQ3 and OQ5. The builder can begin implementing
FR1–FR2 only after the designer's spec is committed.

**Builder (after design):** Implement FR1–FR3 in `tincan_gui/main.py` and
`tincan_gui/call_panel.py`. Reuse `_is_dialable()`, `_enter_call()`, and
`_call_setup_ready`; do not duplicate. Wire the Dial button's enabled/hidden state
through `_sync_compose_state()`-style logic or its own sync method. Add a
pytest-qt behavioural test (NFR5).

---

*PRD covers bead: tincan-8dehj*
