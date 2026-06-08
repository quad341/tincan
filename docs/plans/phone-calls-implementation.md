# Phone Calls Implementation Plan

**PM:** tincan/pm  
**Last updated:** 2026-06-07  
**Architecture ref:** tincan-xohrx (closed)  
**Spike ref:** tincan-xy2sb (blocked — hardware not present)

---

## Summary

Phone calls via HFP (Hands-Free Profile) over Bluetooth. The daemon integrates
with oFono to control call state; the GUI shows an incoming-call dialog and
in-call panel. All implementation is gated on the SCO audio spike passing on
real RTL8761B hardware.

Designer completed all 4 designs on 2026-06-07. Three builder beads are slung
to tincan/builder and waiting on tincan-xy2sb to pass.

---

## Bead Tree

### In builder queue — blocked on spike tincan-xy2sb

| Bead | Title | Design ref | Target |
|------|-------|------------|--------|
| tincan-jni3z | Build tincan_gui call UI: IncomingCallDialog, InCallPanel, DTMFKeypad | tincan-ts1yc ✓ | tincan/builder |
| tincan-0e6na | Implement tincand/call_controller.py + im.tincan.Calls D-Bus interface | tincan-qp8mi ✓ | tincan/builder |
| tincan-pqq3a | Amend tincan.spec: add oFono dependency for phone calls feature | tincan-hp8wf ✓ | tincan/builder |

These unblock automatically once tincan-xy2sb passes.

### Closed design beads (reference only)

| Bead | Covers | Closed |
|------|--------|--------|
| tincan-ts1yc | GUI call UI wireframes (IncomingCallDialog + InCallPanel + DTMFKeypad) | 2026-06-07 |
| tincan-qp8mi | tincand/call_controller.py + im.tincan.Calls D-Bus spec | 2026-06-07 |
| tincan-fx79v.2 | MainWindow QStackedWidget state machine design | 2026-06-07 (covered by tincan-jni3z) |
| tincan-hp8wf | Packaging amendment: oFono COPR vs bundle vs manual | 2026-06-07 |

---

## Dependency Graph

```
tincan-m9bbs (operator: plug RTL8761B + install oFono)
  → tincan-xy2sb (SCO audio spike)
       → tincan-jni3z (call_dialog.py / incall_panel.py / main.py wiring) → tincan/builder
       → tincan-0e6na (call_controller.py + D-Bus) → tincan/builder
       → tincan-pqq3a (tincan.spec oFono dep) → tincan/builder
```

---

## fx79v.1 / fx79v.2 Clarification (2026-06-07)

tincan-fx79v.1 ("Build call_panel.py") was a false-close — `call_panel.py` was never
implemented. This was caught and resolved:

- tincan-fx79v.1: noted as **superseded by tincan-jni3z** (confirmed by mayor)
- tincan-fx79v.2: closed — state machine wiring is included in tincan-jni3z scope
- tincan-jni3z uses the correct file names from tincan-ts1yc: `call_dialog.py` and
  `incall_panel.py` (not the abandoned `call_panel.py` from fx79v)

---

## Spike Unblock Protocol

When the user plugs in the RTL8761B and installs oFono (tincan-m9bbs), the
investigator runs tincan-xy2sb. If all 5 acceptance criteria pass:
1. Investigator closes tincan-xy2sb and mails tincan/architect
2. Three builder beads (tincan-jni3z, tincan-0e6na, tincan-pqq3a) become unblocked
3. Builder picks them up; tincan-pqq3a's implementation method is determined by OQ-1 in spike notes

---

## Packaging Decision Gate

tincan-pqq3a's implementation method depends on OQ-1 from the spike:
- **Option A** (preferred): COPR-hosted oFono package exists → add `Requires: ofono` + `Requires: ofono-plugins-hfp-hf-bluez5`
- **Option B** (fallback): No COPR → bundle oFono binary in tincan COPR spec
- **Option C** (last resort): Manual build → document in docs/install-ofono.md
