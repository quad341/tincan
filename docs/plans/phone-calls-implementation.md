# Phone Calls Implementation Plan

**PM:** tincan/pm  
**Date:** 2026-06-07  
**Architecture ref:** tincan-xohrx (closed)  
**Spike ref:** tincan-xy2sb (blocked — hardware not present)

---

## Summary

Phone calls via HFP (Hands-Free Profile) over Bluetooth. The daemon integrates
with oFono to control call state; the GUI shows an incoming-call dialog and
in-call panel. All implementation is gated on the SCO audio spike passing on
real RTL8761B hardware.

---

## Bead Tree

### Immediately actionable (spike not required)

| Bead | Title | Status | Target |
|------|-------|--------|--------|
| tincan-fx79v.2 | Wire MainWindow: QStackedWidget panel-swap state machine | ready-to-build | tincan/builder |

Architecture (tincan-xohrx) is confirmed — D-Bus signal names locked. Builder
can stub with local signals while waiting for the full daemon integration.

### Blocked on spike tincan-xy2sb

| Bead | Title | Status | Target |
|------|-------|--------|--------|
| tincan-0e6na | Implement tincand/call_controller.py + im.tincan.Calls D-Bus interface | blocked | tincan/builder |
| tincan-jni3z | Build tincan_gui call UI: IncomingCallDialog, InCallPanel, DTMFKeypad | blocked | tincan/builder |
| tincan-pqq3a | Amend tincan.spec: add oFono dependency for phone calls feature | blocked | tincan/builder |

These unblock automatically once tincan-xy2sb passes.

---

## Design References

| Design bead | Covers |
|-------------|--------|
| tincan-qp8mi | tincand/call_controller.py + im.tincan.Calls D-Bus interface spec |
| tincan-ts1yc | tincan_gui/call_dialog.py + tincan_gui/incall_panel.py + dbus_client.py additions |
| tincan-fx79v  | Full GUI wireframe + state machine spec (parent of fx79v.2) |
| tincan-hp8wf  | Packaging amendment: oFono COPR vs bundle vs manual options |

---

## Dependency Graph

```
tincan-m9bbs (operator: plug RTL8761B + install oFono)
  → tincan-xy2sb (SCO audio spike)
       → tincan-0e6na (call_controller.py)
       → tincan-jni3z (call_dialog.py / incall_panel.py)
       → tincan-pqq3a (tincan.spec oFono dep)

tincan-xohrx (architecture, closed)
  → tincan-fx79v.2 (wire MainWindow QStackedWidget) ← immediately actionable
```

---

## Known Risk: tincan-fx79v.1 Closure Gap

tincan-fx79v.1 ("Build call_panel.py") was marked **closed** but no corresponding
commit or PR exists, and `tincan_gui/call_panel.py` is absent from the repo.

**Impact:** tincan-fx79v.2 (wiring the panel-swap) references widget classes that
do not yet exist. The builder should stub the wiring against the tincan-ts1yc
design (call_dialog.py / incall_panel.py file names) rather than the fx79v.1
design (call_panel.py), since tincan-ts1yc is the current canonical spec.

tincan-jni3z (new bead, blocked) covers the actual widget implementation.
Mayor has been notified.

---

## Spike Unblock Protocol

When the user plugs in the RTL8761B and installs oFono (tincan-m9bbs), the
investigator runs tincan-xy2sb. If all 5 acceptance criteria pass:
1. Investigator closes tincan-xy2sb and mails tincan/architect
2. Three blocked builder beads (tincan-0e6na, tincan-jni3z, tincan-pqq3a) become ready
3. Builder picks them up and routes tincan-pqq3a's chosen option (A/B/C) per spike notes

---

## Packaging Decision Gate

tincan-pqq3a's implementation method depends on OQ-1 from the spike:
- **Option A** (preferred): COPR-hosted oFono package exists → add `Requires: ofono` + `Requires: ofono-plugins-hfp-hf-bluez5`
- **Option B** (fallback): No COPR → bundle oFono binary in tincan COPR spec
- **Option C** (last resort): Manual build → document in docs/install-ofono.md
