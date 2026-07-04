# E2E test case: "the Mom call" — iris dials, Call Card works, call completes, echo-free

**The daily goal (owner, 2026-07-04):** iris invokes a call to a real
person, the Call Card loads and captures, the call completes successfully —
**with AEC throughout, or the whole run is moot.**

This is the reliability epic's (tincan-97mlk) acceptance test. It is a
*run-book*: every step has a pass/fail observation. A step without an
observation is not a step.

## Rules

- **Never make the real person the first test.** Dry-run phases 1–2
  against your own voicemail or a second handset until they pass **twice
  in a row**. The real call is the production eval; a failed one costs
  goodwill you cannot re-run.
- **On any failure: stop, File-a-Bug (captures the trace), do not retry
  blind** (tincan-8o5tg). The trace is the deliverable of a failed run.

## Preconditions (once per machine)

- BT500 dongle, udev autosuspend rule, SELinux module, oFono enabled,
  WirePlumber ofono backend — per README / COMPATIBILITY.md.
- iPhone paired, "Show Notifications" granted.
- Latest `main` of tincan AND tincan-iris; tincand restarted since pulling.

## Phase 1 — substrate smoke (tincan alone)

| # | Action | PASS looks like |
|---|--------|-----------------|
| 1.1 | `systemctl --user restart tincand` (or launch by hand) | daemon up, no tracebacks in journal |
| 1.2 | `gdbus call --session -d im.tincan.Daemon -o /im/tincan -m im.tincan.Daemon.GetStatus` | `connected: true`, `messages: true`; **no manual oFono poking** (validates PR #163) |
| 1.3 | `tincan-iris/scripts/aec_audio.sh up` | `pactl get-default-sink` → `iris_aec_sink`, default source → `iris_aec_src` |
| 1.4 | Dial your own voicemail from the tincan GUI dialpad | Two-way audio within ~3s; journal shows "SCO routing established" (PR #164) |
| 1.5 | While the call is live: `GetStatus` again | **`call_audio_aec: true`** (PR #172). If false, the WARNING log names the offending node — that IS the bug report |
| 1.6 | Hang up from the GUI | Call ends cleanly; `call_audio_aec` back to false; no AudioError after hangup |
| 1.7 | Send yourself an SMS during a second call | Message arrives while call is up; UI stays responsive (PR #171) |

## Phase 2 — iris on the call

| # | Action | PASS looks like |
|---|--------|-----------------|
| 2.1 | `iris dial <your-second-number>` | Real call rings, no manual oFono; iris sees CallConnected |
| 2.2 | iris console ride-along on the live call | Far-party speech transcribed and tagged `far` — **requires iris ti-wunrs (DURING capture SCO+AEC wiring); FAILS today by design** |
| 2.3 | Speak a fact from the far handset ("the appointment is Tuesday at 3") | Call Card captures it in DURING |
| 2.4 | Address iris by name; she replies onto the line | Far handset hears iris, **no echo of the far party's own voice** (the human-ear AEC check) |
| 2.5 | Hang up | Card moves to AFTER; recap generated (iris AFTER-stage beads) |

## Phase 3 — the real call

Only after Phases 1–2 pass **twice consecutively** on the same day:

1. iris dials the real person.
2. Disclosure line lands ("I'm an AI…").
3. Conversation happens; card captures ≥1 real fact/commitment.
4. Ask the far party directly: **"do you hear yourself echoing?"** — record
   the answer; it is the ground-truth AEC measurement.
5. Clean hangup; recap reviewed in the console.

**PASS = all five, zero manual interventions from answer to hangup.**

## Current known blockers (2026-07-04)

- iris **ti-wunrs** (P1): DURING capture audio unwired (no AEC, not
  SCO-sourced) — blocks 2.2/2.3.
- AEC bring-up is manual (`aec_audio.sh up` + `bridge`); tincand verifies
  (`call_audio_aec`) but does not load it — automation is the
  `im.tincan.CallAudio` bead under tincan-xbtct.
- PRs #163/#164/#165/#171/#172 are merged but **none live-validated**;
  Phase 1 is their validation.
