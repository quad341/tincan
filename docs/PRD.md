# PRD: Multi-Call Support — Lifecycle Fix + Full Exposure (tincan-6t7ym)

**Status:** Draft  
**Author:** tincan/planner  
**Date:** 2026-06-24  
**Source bead:** tincan-6t7ym  
**Type:** Bug fix + feature  
**Priority:** P2

---

## Problem Statement

`tincand` and the tincan GUI assume at most one concurrent call. This produces two
distinct failure classes:

### Class 1 — State-corruption bug in `call_controller.py`

`tincand` already mirrors oFono's full call list in `self._calls: dict[str,
CallState]`, so the data model is correct. The lifecycle event handlers do not use it
correctly:

- **`_on_call_removed` (line 346–352)** fires `on_call_ended` **and tears down SCO
  audio on every call removal**, regardless of how many calls remain. When one of two
  concurrent calls ends, tincand reports "the call ended" and destroys the audio of
  the call the user is still on. The audio teardown must only happen when no calls
  remain.

- **`_on_call_property_changed` (line 354–374)** transitions only on
  `state == "active"` → `on_call_connected` and `"terminated"` → `on_call_ended`. It
  never emits events for `held` or `waiting` state transitions — so the GUI never
  learns that a call was put on hold or that a second call is waiting.

- **`_on_audio_timeout` (line 389–395)** sets `audio_error = True` on **every** call
  in `_calls`, even those not involved in the timed-out audio setup.

### Class 2 — Missing exposure: multi-call state and control are invisible

- **Call-waiting is never surfaced.** `_on_call_added` (line 342) emits `IncomingCall`
  only when `state == "incoming"`. A call-waiting that arrives during an active call
  comes from oFono as `state == "waiting"` — it is stored in `_calls` but no signal
  reaches any client. The second call is invisible to the GUI and to any future MCP
  client.

- **`im.tincan.Calls` D-Bus interface is missing:** `GetCalls` (enumerate current
  calls with id, number, direction, state), `CallWaiting` signal, `CallHeld` signal,
  `SwapCalls` / `HoldAndAnswer` / `ReleaseAndAnswer` control methods.

- **GUI `call_panel.py`** has `IncomingCallDialog` (handles one incoming call) and
  `InCallPanel` (shows one caller; no swap/hold/answer-waiting controls).

**Who is affected:** Any tincan user who receives a second call while already on a
call. The corruption bug (Class 1) produces no-audio for the surviving call — a hard,
non-recoverable failure during the call.

**Relationship to iris:** iris policy for call-waiting (what iris *does* when a second
call arrives) is explicitly deferred — see tincan-iris ADR-0006. This bead is about
the transport (tincand) and the GUI being fully featured underneath, regardless of
what iris eventually does.

---

## Goals

| # | Goal | Measurable Outcome |
|---|------|--------------------|
| G1 | Correct per-call lifecycle | `on_call_ended` fires only when `_calls` is empty after removal; audio teardown fires only for the call that actually ended; `_on_audio_timeout` marks only the timed-out call's `audio_error` |
| G2 | Held and waiting state transitions surfaced | `_on_call_property_changed` emits events for `held` and `waiting` transitions; clients receive signals for every state change |
| G3 | `im.tincan.Calls` exposes full call list | Clients can call `GetCalls` to enumerate all current calls (id, number, direction, state); `CallWaiting` and `CallHeld` signals are emitted on state changes |
| G4 | Multi-call control exposed | `im.tincan.Calls` exposes `SwapCalls`, `HoldAndAnswer`, `ReleaseAndAnswer`, per-call `Answer(call_id)`, per-call `Hangup(call_id)`, backed by oFono |
| G5 | GUI shows all concurrent calls with controls | tincan GUI renders active + waiting + held calls; provides answer-waiting, swap, hold, and per-call hangup controls |
| G6 | No regressions on single-call flows | Incoming call, answer, in-call, and hangup flows for a single call work identically to the pre-fix state |

## Non-Goals

- **iris policy for call-waiting** — what iris does when a second call arrives is
  deferred; iris may ignore the extra call entirely. See tincan-iris ADR-0006.
- **Multi-party (conference) calls** — merging two calls into a conference is out of
  scope; oFono models this separately and tincan has no use case for it yet.
- **DTMF on held calls** — DTMF is only meaningful for the active call; no change to
  existing DTMF routing.
- **Changing SCO audio routing or PipeWire wiring** — the audio stack is separate
  from multi-call control.
- **On-device multi-call testing** — acceptance criteria are defined; on-device
  validation (two concurrent live calls) is a manual QA step, not a CI gate.
- **tincan-mcp multi-call exposure** — MCP (phase 5) can consume the new D-Bus
  interface unchanged when it exists; no MCP changes in this bead.

---

## User Stories

| ID | Story |
|----|-------|
| US1 | As a user already on a call who receives a second call, I want the GUI to show the waiting call with the caller's name/number so I can decide whether to answer, ignore, or hang up without losing the current call. |
| US2 | As a user with a held call and an active call, I want a swap button in the GUI so I can bring the held call back to active with one tap. |
| US3 | As a user who answers a waiting call, I want my current active call to automatically move to held so I can resume it when I'm done. |
| US4 | As a developer running tincand with two concurrent calls, I want `GetCalls` on `im.tincan.Calls` to return both calls with correct states so I can build and test against the real interface. |
| US5 | As a user mid-call when one of two calls ends, I want the audio on my remaining call to continue uninterrupted — the bug today silently destroys it. |

---

## Functional Requirements

### FR1 — Per-call audio teardown

`_on_call_removed` MUST check `self._calls` after removing the ended call. SCO audio
teardown (`teardown_sco_audio()`) and the `on_call_ended` event MUST only fire when
`self._calls` is empty after the removal.

**Acceptance criterion:** In a two-call scenario, ending one call leaves the other
call's audio intact. `on_call_ended` is not emitted until the last call is removed
from `_calls`.

### FR2 — Per-call `audio_error` flag

`_on_audio_timeout` MUST set `audio_error = True` only on the call whose audio setup
timed out, identified by call ID. It MUST NOT iterate over all calls in `_calls`.

**Acceptance criterion:** In a unit test with two calls in `_calls`, triggering an
audio timeout for call A leaves call B's `audio_error = False`.

### FR3 — `held` and `waiting` state transitions in `_on_call_property_changed`

`_on_call_property_changed` MUST handle `state == "held"` and `state == "waiting"` in
addition to the existing `"active"` and `"terminated"` cases:

- `"held"` → emit `CallHeld(call_id, number)` on `im.tincan.Calls`
- `"waiting"` → emit `CallWaiting(call_id, number, direction)` on `im.tincan.Calls`
- `"active"` (existing) → emit `CallConnected(call_id, number)` on `im.tincan.Calls`
- `"terminated"` (existing) → emit `CallEnded(call_id)` on `im.tincan.Calls`

**Acceptance criterion:** A unit test that injects a `PropertyChanged("State",
"waiting")` for a tracked call observes a `CallWaiting` signal; same for `"held"`.

### FR4 — Call-waiting surfaced via `_on_call_added`

`_on_call_added` MUST emit an event for calls with `state == "waiting"`, not just
`state == "incoming"`. The event for a waiting call MUST be distinct from an incoming
call (different signal or field) so clients can differentiate.

**Acceptance criterion:** A simulated oFono `CallAdded` with `state="waiting"` causes
tincand to emit a `CallWaiting` signal on `im.tincan.Calls`.

### FR5 — `GetCalls` enumeration on `im.tincan.Calls`

`im.tincan.Calls` MUST expose a `GetCalls()` method returning an array of structs:
`(call_id: str, number: str, direction: str, state: str)` for every call currently in
`self._calls`.

**Acceptance criterion:** With two concurrent calls in `_calls`, a `busctl call
im.tincan.Calls GetCalls` returns two entries with correct ids, numbers, directions,
and states.

### FR6 — Multi-call control methods on `im.tincan.Calls`

`im.tincan.Calls` MUST expose the following control methods, each backed by the
corresponding oFono `org.ofono.VoiceCallManager` method:

| tincan method | oFono method | Description |
|--------------|-------------|-------------|
| `SwapCalls()` | `SwapCalls()` | Swap active ↔ held |
| `HoldAndAnswer()` | `HoldAndAnswer()` | Put active on hold; answer waiting |
| `ReleaseAndAnswer()` | `ReleaseAndAnswer()` | Hang up active; answer waiting |
| `Answer(call_id: str)` | per-call `org.ofono.VoiceCall.Answer()` | Answer a specific call |
| `Hangup(call_id: str)` | per-call `org.ofono.VoiceCall.Hangup()` | Hang up a specific call |

Errors from oFono MUST propagate as D-Bus errors to the caller.

**Acceptance criterion:** `busctl call im.tincan.Calls SwapCalls` with two concurrent
calls (one active, one held) causes oFono to swap them, and subsequent `GetCalls`
shows the swapped states.

### FR7 — GUI shows all concurrent calls with state

`tincan_gui` call panel MUST render all calls currently returned by `GetCalls`, with
a per-call row showing: caller name/number, direction indicator, state badge (active /
held / waiting).

The in-call panel MUST update in real time as `CallWaiting`, `CallHeld`,
`CallConnected`, and `CallEnded` signals arrive.

**Acceptance criterion:** In a simulated two-call scenario (one active, one waiting),
the GUI renders two rows; when the waiting call is answered, it transitions to active
and the formerly-active call shows as held.

### FR8 — GUI multi-call controls

The in-call panel MUST include:

- **Swap** button (visible when at least one held + one active call): calls `SwapCalls`
- **Answer & Hold** button (visible when a waiting call exists): calls `HoldAndAnswer`
- **Answer & Release** button (visible when a waiting call exists): calls `ReleaseAndAnswer`
- **Hangup** button per call: calls `Hangup(call_id)` for that specific call

Controls are shown/hidden based on the current call set state, not statically.

**Acceptance criterion:** With two calls (active + waiting), "Answer & Hold" and
"Answer & Release" buttons are visible; with two calls (active + held), "Swap" and
per-call Hangup buttons are visible. With a single active call, only a single Hangup
button is visible (no regression from current state).

---

## Non-Functional Requirements

| # | Requirement | Metric |
|---|-------------|--------|
| NF1 | Unit test coverage | Unit tests MUST cover: FR1 (audio teardown only on last call), FR2 (audio_error scoped to one call), FR3 (held and waiting signals emitted), FR4 (call-waiting from CallAdded). Tests MUST run without a live oFono bus. |
| NF2 | D-Bus interface backward compatibility | The `im.tincan.Calls` changes MUST be additive. Existing signals (`IncomingCall`, `CallEnded`, `CallConnected`) and existing methods remain unchanged; new methods/signals are additions. |
| NF3 | Signal subscription cleanup | Any per-call oFono subscriptions (e.g., `VoiceCall.PropertyChanged`) MUST be unsubscribed when the call is removed from `_calls`. No stale subscriptions accumulate across calls. |
| NF4 | GUI state machine correctness | The GUI control visibility logic MUST be driven by the received call-state signals, not by client-side state inference. No caching of call state in the GUI beyond what the latest signal conveyed. |

---

## Technical Constraints

From `docs/PROJECT_MANIFEST.md` and live code review:

1. **`self._calls: dict[str, CallState]` is already maintained** — `CallAdded`,
   `CallRemoved`, and `GetCalls` from oFono are already mirrored. FR1–FR4 are
   correctness fixes to the handlers; no new data structure is needed.

2. **oFono `org.ofono.VoiceCallManager` provides `SwapCalls`, `HoldAndAnswer`,
   `ReleaseAndAnswer`** — already present in oFono `hfp_hf_bluez5`; tincand only
   needs to proxy them through `im.tincan.Calls`. No new oFono API integration.

3. **Per-call `org.ofono.VoiceCall` objects** — oFono represents each call as a
   D-Bus object at `/hfp/org/bluez/hciN/dev_.../voicecall01` (etc). `Answer()` and
   `Hangup()` are per-call methods on this object; tincand must look up the object
   path from `call_id`.

4. **`im.tincan.Calls` interface is in `dbus_service.py` lines 617–737** — extending
   the interface is additive; existing signal/method registrations are not affected.

5. **GUI client model** — `tincan_gui` is a pure client of `im.tincan.Calls`; it must
   not own call-state logic. All state is derived from D-Bus signals received from
   tincand.

6. **GLib mainloop** — all D-Bus callbacks run in the GLib mainloop; no threading is
   needed for the tincand side.

7. **`call_panel.py` uses `IncomingCallDialog` and `InCallPanel`** — these classes
   must be extended (not replaced); the single-call code path remains for callers in
   the non-waiting state.

8. **Python conventions** — `ruff` + `black`; type hints on modified public methods
   and new D-Bus interface additions.

---

## Dependencies

| Dependency | Status | Notes |
|-----------|--------|-------|
| `self._calls` dict in `CallController` | Present | Already maintained; no new data structure needed |
| oFono `SwapCalls` / `HoldAndAnswer` / `ReleaseAndAnswer` | Available | Standard `org.ofono.VoiceCallManager` methods; present in `hfp_hf_bluez5` |
| Per-call oFono `VoiceCall` object paths | Available | oFono emits these with `CallAdded`; tincand must retain the path mapping |
| `im.tincan.Calls` D-Bus interface | Exists (partial) | `dbus_service.py` lines 617–737; to be extended additively |
| `call_panel.py` GUI component | Exists (single-call) | `IncomingCallDialog` + `InCallPanel`; to be extended for multi-call display |
| tincan-iris ADR-0006 | Reference | Defines the iris/tincan ownership boundary; iris policy is out of scope here |

---

## Open Questions

| # | Question | Needed from |
|---|----------|-------------|
| OQ1 | Should `HoldAndAnswer` and `ReleaseAndAnswer` be exposed as separate buttons, or collapsed into a single "Answer" button that picks the right oFono method based on current call state? | Designer |
| OQ2 | What visual treatment distinguishes a held call from an active call in the multi-call list? (e.g., greyed label, "HELD" badge, muted audio indicator) | Designer |
| OQ3 | When two calls are active (one held, one active), should there be a single "End All Calls" action, or only per-call hangup? | Designer / Jim |
| OQ4 | Should tincand proxy `VoiceCallManager.GetCalls()` directly for `GetCalls`, or maintain its own authoritative copy built from `CallAdded`/`CallRemoved` events and return that? | Architect |
| OQ5 | Is there a risk that oFono's `VoiceCallManager.SwapCalls` / `HoldAndAnswer` / `ReleaseAndAnswer` fail silently for HFP-HF profiles that don't support CHLD? Should tincand check capability or let the oFono error propagate? | Architect |
