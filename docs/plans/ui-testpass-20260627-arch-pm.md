# PM Plan: 2026-06-27 UI Test-Pass Batch — Arch Handoff (FR-A1/A2/A3 + FR-C2/C3 refinements + OQ1)

**Date:** 2026-06-27  
**PM beads consumed:** tincan-vfb6o, tincan-og6ec, tincan-80rkb, tincan-oitb6, tincan-0g4z5, tincan-wag5s  
**Design specs:** tincan-vfb6o (FR-D refinement), tincan-og6ec (FR-A2+A3), tincan-80rkb (FR-A1), tincan-oitb6 (FR-C2 emoji), tincan-0g4z5 (FR-C3 annotation), tincan-wag5s (OQ1)  
**Source:** tincan-0xzqi (architect root-cause) → designer handoff → PM  
**Prior plan:** docs/plans/ui-testpass-20260627-c-pm.md (Cluster C — FR-C1/C2/C3/D toolbar+guard batch)

---

## Summary

Designer completed specs for the Arch Handoff batch (FR-A1, FR-A2+A3, OQ1, plus refinements to
FR-D and FR-C2/C3). Six implementation beads created:

| Bead | Title | Routing | Notes |
|------|-------|---------|-------|
| tincan-mybn5 | Fix adapter selection priority: two-pass in _populate_adapter_combo (FR-A1) | ready-to-build → builder | New; no prior impl |
| tincan-2d3m4 | Fix _adapter_mismatch_annotation orphan: hide guard in _populate_adapter_combo + _refresh (FR-C3) | ready-to-build → builder | Blocked by tincan-mybn5 (both touch empty-list branch) |
| tincan-gvgwt | Add StateABanner.set_reason() + set_reconnecting() (FR-A2+A3) | ready-to-build → builder | New; no prior impl |
| tincan-96nsi | Refine compose-new button disabled state: tooltip wording + accessible name (FR-D follow-up) | ready-to-build → builder | Refines tincan-bz9go (CLOSED); tooltip wording + accessibleName |
| tincan-5d053 | Extend _emoji_font_families() with Noto Emoji + Qt generic family + startup diagnostic (FR-C2) | ready-to-build → builder | Different code path from tincan-0oxkd (toolbar buttons); fixes message bubble emoji in text_render.py |
| tincan-3s41m | Fix QSettings path: use Path.home() instead of $HOME (OQ1 hardening) | ready-to-build → builder | Defensive hardening per architect; warranted regardless of OQ1 operator re-test |

---

## Dependency graph

```
tincan-mybn5 (FR-A1)   →blocks→  tincan-2d3m4 (FR-C3)
tincan-gvgwt (FR-A2+A3)           (independent)
tincan-96nsi (FR-D)                (independent)
tincan-5d053 (FR-C2 emoji)         (independent)
tincan-3s41m (OQ1 QSettings)       (independent)
```

All 5 independent beads can be built concurrently. FR-C3 (tincan-2d3m4) unblocks after FR-A1 merges.

---

## Routing

All six beads → `tincan/builder`.

---

## Context: what was already built

The prior PM session (ui-testpass-20260627-c-pm.md) already produced and the builder closed:
- tincan-psnc5 (FR-C1 combo width) — confirmed implemented; no action
- tincan-bz9go (FR-D compose guard basic) — implemented; tincan-96nsi is a refinement
- tincan-0oxkd (FR-C2 toolbar icons) — QIcon.fromTheme for toolbar buttons; implemented
- tincan-easo3 (FR-C3 show/hide invariants) — broad show/hide; tincan-2d3m4 adds specific annotation guard

---

## OQ1 operator re-test

tincan-wag5s (OQ1) identified a required operator action: launch `tincan-gui` with
`HOME=/home/jaword` and re-test adapter persistence, notifications toggle, conversation cache.
The 3 persistence bugs (tincan-zdvh9, tincan-w1oxf, tincan-m0rt8) were closed as
likely env artifacts. Mayor has been mailed to confirm whether the re-test was performed.
The QSettings Path.home() fix (tincan-3s41m) is defensive hardening that proceeds regardless.

---

## Acceptance Summary

| Feature | Acceptance |
|---------|-----------|
| FR-A1 | Saved adapter selection persists across settings close+reopen (HOME=correct); no amber widget when adapter list empty |
| FR-A2+A3 | Banner says "Not connected" on first launch; "Connection lost" after prior connect; Reconnect button shows busy state |
| FR-C3 | No orphaned amber annotation visible when adapter list empty; stale warnings don't reappear |
| FR-D refinement | Tooltip says "Connect a device to start a new conversation"; disabled button announces "New conversation — connect a device first" to screen reader |
| FR-C2 emoji | Emoji renders in message bubbles on Fedora with only google-noto-emoji-fonts installed; startup log shows no warning |
| OQ1 QSettings | Settings persist whether launched from rig shell or application menu; Path.home() used for QSettings path |
