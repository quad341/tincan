# Plan: wire `call_link_ready` into `_apply_capabilities` (tincan-bhij3)

## Goal

The daemon exposes a second, dynamic call-readiness capability, `call_link_ready`
(added tincan-c7b8g / commit 3e5ddb7, daemon-side tests in tincan-cq5c7 / PR #175),
reflecting whether `CallController` currently has a live, bound `VoiceCallManager`.
This is distinct from the existing `call_setup_ready` (static — HFP SELinux module
presence only). The GUI never learned about the new flag: the title-bar Dial
button and the per-thread Call button gate only on `call_setup_ready`, so both
can render enabled while no phone is actually bound — the user clicks, and
`CallController.dial()` raises `RuntimeError` because `self._vcm is None`.

Full design (state model, exact copy, wiring recommendations, a11y audit,
suggested test coverage, wireframe reference) lives on tincan-bhij3 itself,
written by the designer. This plan just records the decomposition.

## Source

`source:actual-designer` — design is complete, no `needs-design` loop-back.
Verified against current worktree HEAD 2026-07-13: all structural details in
the design (existing branch shapes, style strings, fallback dicts) match
current code exactly; only the design doc's line numbers have drifted
(~15-30 lines, other work landed in between). Children below call this out
explicitly so builder/validator locate by method name, not line number.

## Decomposition

Two children — this is a single cohesive wiring change (one PR-sized surface:
`tincan_gui/main.py` capability sync + `tincan_gui/thread_view.py` one method),
split along the builder/test-authoring line rather than by file, matching the
precedent set by the daemon-side half of this same feature (tincan-c7b8g
builder → tincan-cq5c7 validator, PR #175):

- **tincan-uuia9** (`ready-to-build` → `tincan/builder`) — wire the new
  capability flag through `_apply_capabilities`, add the 3rd state to
  `_sync_call_state`'s precedence chain for both the title-bar dial button and
  `ThreadHeader.set_call_button`, reset on disconnect, close the
  `setAccessibleDescription` a11y gap on both widgets while touching them.
  No new banner (deliberate — see design rationale).

- **tincan-piiml** (`needs-tests` → `tincan/validator`, blocked-by
  tincan-uuia9) — 5 suggested cases: default-False semantics, disabled-state
  copy/a11y assertions, disconnect reset, precedence ordering (setup-not-ready
  beats link-not-ready), and asserting `setAccessibleDescription()` return
  values directly rather than just widget state.

Test bead is gated behind the build bead (real `bd dep add ... blocks`, not just
narrative) since the suggested tests assert against the new implementation's
exact internals (attribute name, tooltip string, accessible-description
pairing) rather than being written test-first.

## Out of scope (per design, unchanged)

- `_on_call_incoming` — only gates `disable_answer()` on `call_setup_ready`.
  CallAdded/CallRemoved D-Bus signals structurally imply `call_link_ready` was
  already `True` when this handler runs.
- Any banner for `call_link_ready` — the condition is transient/self-healing
  (tincan-c7b8g's reconnect logic already handles recovery in the background);
  a banner that flickers on/off as the link blips would be fatigue, not signal.
  The disabled-button tooltip is sufficient.
