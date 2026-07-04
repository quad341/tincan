# Plan: First-run onboarding — installation → paired → configured, without heroics

**Bead (epic):** tincan-u57gf
**Date:** 2026-07-04
**Status:** planned (sequenced after the reliability baseline, tincan-97mlk)

## Problem

Today you need to be *really* motivated to get tincan working at all — and
iris multiplies that. A new user/machine faces, in order, with no guidance:

1. Install the app (RPM exists for Fedora; pip path otherwise).
2. A BlueZ new enough (or patched) for the ext-adv bug, plus
   `bluetoothd --experimental` for ANCS.
3. An SCO-capable adapter (reference: ASUS USB-BT500), the udev rule that
   disables the broken built-in, and USB autosuspend off.
4. The SELinux module for SCO fd passing.
5. oFono installed/enabled, WirePlumber switched to the ofono HFP backend,
   in the right start order.
6. Pair the iPhone; accept the iOS **"Show Notifications"** consent (without
   which MAP drops); reconnect.
7. Per-app notification filtering, adapter selection, device address config.

None of this is guided by the app. `tincan_gui` has **no first-run flow
wired**: `pairing_wizard.py` is only reachable from a repair notification,
and `onboarding.py` is dead code (imported nowhere — to be deleted in the
MVVM epic, tincan-dmchi).

## Goal

From a fresh Fedora machine to "message received on desktop, test call with
no echo" in under 30 minutes, with the app telling you what's wrong at every
step instead of you diffing your setup against tribal knowledge.

## Approach

Three layers, cheapest first:

### 1. `INSTALL.md` — the honest written path (no code)

One document, ordered, copy-pasteable, covering steps 1–6 above with the
*why* one sentence each and links to the root-cause docs. Everything the
wizard can never do (buy a dongle, install packages, SELinux) lives here.
The README links to it; the README itself stops accreting setup fragments.

### 2. `tincan doctor` — detection (shared with the reliability epic)

The live-health tripwire (child of tincan-97mlk) doubles as the onboarding
brain: each check knows its remediation hint. Checks: BlueZ version/patch,
experimental flag, adapter SCO capability + autosuspend, SELinux module,
oFono present/running, WirePlumber backend, device paired, MAP connectable,
ANCS notifying, modem online, and — during a test call — SCO nodes present
and AEC in the path.

### 3. First-run wizard in the GUI — the guided flow

On start with no configured device: launch a doctor-driven wizard.

- Each page = one doctor check-group; green ticks for what's already fine;
  fix-it instructions (and buttons where possible: install udev rule, write
  WirePlumber conf, enable ofono via pkexec) for what isn't.
- Pairing page reuses `pairing_wizard.py` (dual-mode ANCS+MAP), including
  explicit phone-side steps with screenshots: Settings → Bluetooth → device
  → **Show Notifications** ON.
- Final page: send-yourself-a-test-message and (if call-capable) a test call
  with an AEC verification, so "done" means *verified working*, not
  "wizard finished."
- Re-runnable from Settings ("Set up / repair connection") — the same flow
  is the repair flow, replacing the current notification-only entry point.

## Non-goals

- Distro-agnostic polish (Fedora first; the INSTALL.md notes where other
  distros diverge).
- iris onboarding — separate project; but iris's `SETUP.md` should link to
  tincan's INSTALL.md as its prerequisite step 0, and `iris doctor` should
  invoke/inherit tincan's checks rather than duplicating them.

## Sequencing

After the reliability baseline (tincan-97mlk): a wizard that walks users
into a stack where ANCS silently regresses and calls need manual oFono
poking would just industrialize disappointment. Doctor checks land first
(they serve the baseline), wizard UI lands with/after the MVVM epic's
viewmodel layer so it's born testable.
