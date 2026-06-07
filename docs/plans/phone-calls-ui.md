# Phone Calls UI — Implementation Plan

**Source bead:** tincan-fx79v  
**Design:** tincan/designer (2026-06-07)  
**PM:** tincan/pm  

## Goal

Implement the Phone Calls UI as designed: incoming call dialog, in-call panel, DTMF keypad, and audio error state. The design is complete (OQ-5 resolved); architecture D-Bus interface confirmation is still in progress (tincan-xohrx).

## Decision: Floating Modal + Inline Panel

- Incoming call → `IncomingCallDialog` (QDialog, semi-modal, centered on MainWindow)
- In-call → `InCallPanel` replaces compose bar via QStackedWidget

## Beads

| Bead | Title | Target | Blocks / Status |
|------|-------|--------|-----------------|
| tincan-fx79v.1 | Build call_panel.py (4 widget classes) | builder | No blockers — start immediately |
| tincan-fx79v.2 | Wire MainWindow QStackedWidget state machine | builder | Blocked on tincan-xohrx (D-Bus interface) |
| tincan-fx79v.3 | D-Bus client: HFP call signals + send_dtmf | builder | Needs tincan-xohrx confirmed (cycle prevents hard dep) |
| tincan-fx79v.4 | Behavioral tests for call_panel.py | validator | Blocked on tincan-fx79v.1 |

## Dependency graph

```
tincan-fx79v.1 (UI classes) ──────────────────────────────► builder (now)
                │
                ▼
tincan-fx79v.4 (tests) ──────────────────────────────────► validator (after .1)

tincan-xohrx (architecture) ────────────────────────────► architect (now unblocked)
                │
                ▼
tincan-fx79v.2 (MainWindow wiring) ─────────────────────► builder (after xohrx)
tincan-fx79v.3 (D-Bus client) ──────────────────────────► builder (after xohrx)
```

## Key constraints for builder

1. `tincan_gui/call_panel.py` is a new file — all 4 classes live there.
2. Reuse `AvatarWidget` from `avatar.py` — no new avatar logic.
3. Error body text must be `#a3a3a3` (not `#9ca3af`) — a11y audit correction.
4. `IncomingCallDialog` must call `raise_()` + `activateWindow()` on show.
5. `DTMFKeypad.tone_pressed` → `dbus_client.send_dtmf(key)` — if method absent, log and return (don't raise).

## D-Bus signals required from tincand (pending tincan-xohrx)

| Signal | Args | Handler |
|--------|------|---------|
| `IncomingCall` | caller_name, caller_number | Show IncomingCallDialog |
| `CallConnected` | — | Show InCallPanel |
| `CallEnded` | — | Restore ComposePanel |
| `AudioError` | reason: str | Show AudioErrorPanel |
| `AudioRestored` | — | Show InCallPanel |

## A11y action items (builder)

1. Error body text: `#a3a3a3` (not `#9ca3af`)
2. Call `QAccessible.updateAccessibility()` when `AudioErrorPanel` becomes visible
3. `IncomingCallDialog.raise_()` + `activateWindow()` on show

## Wireframes

Full design spec (with ASCII wireframes, component code, state machine, a11y audit):  
`bd show tincan-fx79v`

Excalidraw file:  
`/home/jaword/projects/gc-management/.gc/worktrees/tincan/designer/tincan-fx79v/phone-calls-ui.excalidraw`
