# BT Adapter Selection — Implementation Plan

**PM bead:** (derived from design beads tincan-ki9qt, tincan-p4e9r, tincan-6re8d)  
**Architecture:** tincan-b14w7  
**Date:** 2026-06-14

---

## Goal

Let the user choose their Bluetooth adapter (hci0 vs hci1) from Settings → Bluetooth.
The picker shows per-adapter capability badges (HFP call audio, LE advertising) and handles
all degraded states gracefully.

---

## Bead Tree

```
tincan-hchsf  [builder]  adapter_check.py — list_adapters() + HFP detection
    └── tincan-yuomh  [builder]  daemon D-Bus API — GetAdapters() + GetStatus() + _resolve_adapter_path()
            └── tincan-0fq30  [builder]  dbus_client.py — get_adapters() + adapter fallback fields
                    ├── tincan-yn2x5  [builder]  settings_dialog.py — QComboBox picker + delegate + degraded states
                    │       └── tincan-gu24r  [builder]  settings_dialog.py — adapter-changed restart banner
                    │               └── tincan-t53s7  [validator] GUI behavioral acceptance tests
                    └── tincan-crfu9  [builder]  main.py — saved-adapter-unavailable banner
                            └── (tincan-t53s7 also depends on this)

tincan-azcok  [validator]  Unit tests for adapter_check module
    (depends on tincan-hchsf)
```

---

## Beads

| ID | Title | Target | Depends on |
|----|-------|--------|------------|
| tincan-hchsf | list_adapters() + HFP detection in adapter_check.py | builder | — |
| tincan-yuomh | GetAdapters() + GetStatus() augmentation + _resolve_adapter_path() | builder | tincan-hchsf |
| tincan-0fq30 | get_adapters() + fallback fields in dbus_client.py | builder | tincan-yuomh |
| tincan-yn2x5 | QComboBox picker + delegate + badges + degraded states | builder | tincan-0fq30 |
| tincan-gu24r | Adapter-changed restart banner in settings_dialog.py | builder | tincan-yn2x5 |
| tincan-crfu9 | Saved-adapter-unavailable banner in main.py | builder | tincan-0fq30 |
| tincan-azcok | Unit tests: adapter_check module | validator | tincan-hchsf |
| tincan-t53s7 | Behavioral acceptance tests: picker + both banners | validator | tincan-gu24r, tincan-crfu9 |

---

## Design References

- **tincan-ki9qt** → picker widget spec (consumed by tincan-yn2x5)
- **tincan-p4e9r** → restart banner (tincan-gu24r) + unavailable banner (tincan-crfu9)
- **tincan-6re8d** → degraded states spec (consumed by tincan-yn2x5)

---

## Key Constraints (from arch tincan-b14w7 §18)

1. `tincan_gui` must never import `dbus.SystemBus()` — all BlueZ queries go through daemon.
2. `list_adapters()` makes exactly ONE `GetManagedObjects()` call.
3. Path validation: `^/org/bluez/hci[0-9]+$` on all adapter paths from any source.
4. `DaemonSettings` is daemon-only — GUI writes via `QSettings`, daemon reads via `DaemonSettings`.
5. `spawn_daemon()` signature is unchanged — adapter flows through QSettings only.
6. SIGTERM (not SIGKILL) for daemon shutdown.
7. `is_selected` reflects QSettings value at call time, not the running adapter.

---

## Build Order

The dependency graph serializes naturally into three phases:

**Phase 1 (parallel):** tincan-hchsf  
**Phase 2:** tincan-yuomh (after hchsf), tincan-azcok (after hchsf in parallel)  
**Phase 3:** tincan-0fq30 (after yuomh)  
**Phase 4 (parallel):** tincan-yn2x5, tincan-crfu9  
**Phase 5:** tincan-gu24r (after yn2x5)  
**Phase 6:** tincan-t53s7 (after gu24r + crfu9)
