# Tincan — How to Launch & Test

A layered guide, from "zero setup, works today" up to "real iPhone over Bluetooth."
Tincan = Linux desktop iPhone companion: a **PySide6 GUI** (`tincan_gui/`) talking to a
**D-Bus daemon** (`tincand/`) that speaks standard Bluetooth profiles (MAP for SMS,
ANCS for notifications) to a paired iPhone.

> **Status (2026-06-02):** The GUI is real and tested. The daemon now has an entry
> point (`python -m tincand`) and a pluggable backend system (MockBackend, MapBackend,
> AncsBackend). Phase-1a/1b are implemented. The phase-0 MAP spike (m01) was run
> against real hardware — OQ-1 (SMS bodies), OQ-2 (iMessage present, relabeled
> sms-gsm), and PushMessage send all confirmed. m02 (ANCS) and m03 (concurrent)
> still need hardware validation (tincan-r23 gate). The onboarding wizard is
> **UI-only** (no real BlueZ pairing yet). Layers 0–2 work today.

---

## Setup (Fedora 44 — the reference host)

```bash
# Python GUI + test deps (a venv is fine)
python -m pip install "PySide6>=6.5" pytest pytest-qt

# System deps for the daemon + hardware spikes
sudo dnf install python3-dbus python3-gobject bluez bluez-obexd
# ANCS notifications spike also needs:  pip install ancs4linux
```

| You want to… | Needs |
|---|---|
| Run the tests | PySide6, pytest, pytest-qt |
| See the GUI (mock data) | PySide6, dbus-python |
| Run the daemon | dbus-python |
| Run the spikes | dbus-python, PyGObject, bluetoothd, obexd, (ancs4linux), **a paired iPhone** |

---

## Layer 0 — Unit tests (no hardware, ~3 s)

```bash
cd ~/projects/tincan
QT_QPA_PLATFORM=offscreen python -m pytest tests/ -v
```
- **Expect:** `228 passed`. `QT_QPA_PLATFORM=offscreen` renders Qt to a buffer so **no windows pop up** and it works over SSH.
- **Covers:** GUI widgets (conversation list, thread view, unread badges, search/filter, avatars), accessibility/contrast (WCAG 2.1 AA), the daemon state machine, and the GUI's D-Bus client signal bridges (mocked).
- **Does NOT cover:** real Bluetooth, real MAP/ANCS, live daemon↔GUI. See Layers 3–4.

## Layer 1 — GUI smoke test, mock mode (no hardware, no daemon)

```bash
cd ~/projects/tincan
python -m tincan_gui          # opens the real window
# headless / screenshot only:  QT_QPA_PLATFORM=offscreen python -m tincan_gui
```
The GUI ships with built-in stub data, so it renders **without a daemon or phone**.
Walk through and eyeball:
- [ ] Conversation list shows sample threads (Alice, Bob, Family) with unread badges.
- [ ] Clicking a conversation opens the thread view with inbound/outbound bubbles
      (and a "body unavailable" bubble — the ANCS-only degraded case).
- [ ] The compose box is present; sending prints a `[stub]` line to the terminal
      (real send isn't wired — `SendMessage` is a stub).
- [ ] Title bar shows a connection/capability chip; degradation banners (A/B/C) appear
      for the various "phone connected but X unavailable" states.
- [ ] Onboarding wizard pages render (Welcome → Detect BT → Pair PIN → Show
      Notifications → Connected). **Note:** these are UI mockups — no real pairing.

## Layer 2 — Daemon ↔ GUI over live D-Bus

**Now runnable.** The daemon has a `python -m tincand` entry point with a MockBackend
that emits canned conversations and cycles through `Connected` / `CapabilityChanged` /
`MessageReceived` events on a timer — no iPhone required.

```bash
cd ~/projects/tincan
# Terminal 1: start the daemon with mock backend
python -m tincand --backend mock --device test

# Terminal 2: launch the GUI
python -m tincan_gui
```

What to verify:
- [ ] GUI shows "Connected" chip within ~3 seconds (MockBackend emits `Connected` on start).
- [ ] Canned conversations (Alice, Bob, Family) appear in the conversation list.
- [ ] Thread view updates as `MessageReceived` fires on timer.
- [ ] Degradation banners A/B/C cycle on/off as the mock timer drives capability changes.

The daemon also accepts `--backend bluez-map --device AA:BB:CC:DD:EE:FF` for the real
MAP backend (requires a paired iPhone with Show Notifications enabled).

## Layer 3 — Hardware spikes: the pairing flow (REAL iPhone)

This answers the four open questions and fills in `spikes/FINDINGS.md`.

### 3a. Pair the iPhone over Bluetooth (one-time)
```bash
bluetoothctl
# in the prompt:
power on
agent on
default-agent
scan on                      # wait until your iPhone appears, note its MAC AA:BB:CC:DD:EE:FF
pair AA:BB:CC:DD:EE:FF       # confirm the 6-digit code on BOTH the iPhone and here
trust AA:BB:CC:DD:EE:FF
connect AA:BB:CC:DD:EE:FF
scan off
quit
```
Then **on the iPhone**: Settings → Bluetooth → tap the (i) next to this computer →
enable **Show Notifications** (and Sync Contacts if testing PBAP). This permission is
what unlocks MAP (SMS) and ANCS — without it the spikes return empty.

Make sure the services are up: `systemctl status bluetooth` and that **obexd** is
running on your session bus (it autostarts on demand; `/usr/libexec/bluetooth/obexd`).

### 3b. Run the spikes
```bash
export DEVICE_ADDR=AA:BB:CC:DD:EE:FF

python spikes/m01_map.py            # OQ-1 ✅ YES — SMS bodies over MAP confirmed
                                    # OQ-2 ✅ YES — iMessage present, listed as sms-gsm type
                                    # SEND ✅ YES — PushMessage delivers; iOS upgrades to iMessage for iMessage contacts
python spikes/m02_ancs.py           # OQ-3 ⏳ PENDING — needs hardware run (tincan-r23)
                                    #   (run with: --direct-gatt for direct GATT path, default uses ancs4linux)
python spikes/m03_concurrent.py     # OQ-4 ⏳ PENDING — needs hardware run (tincan-r23)
```
MAP spikes are validated. ANCS + concurrent spikes still need a hardware run —
record results in `spikes/FINDINGS.md` under OQ-3 and OQ-4.

## Layer 4 — End-to-end (REAL iPhone + daemon) — future

Once Layer 2's daemon backend is wired to real BlueZ/obexd/ancs4linux:
pair the phone → start `tincand` → launch the GUI → a real SMS to the iPhone should
appear in the thread view, and a reply from the GUI should send via MAP PushMessage.
Not buildable until the daemon backend and the onboarding pairing logic exist.

---

## What still needs BUILDING or VALIDATING

Already built (Phase-1a/1b):
- ✅ `tincand` entry point + MockBackend + MapBackend + AncsBackend
- ✅ MAP inbox polling (`poll_inbox`), message send (`send_message`)
- ✅ ANCS backend (ancs4linux-based, needs hardware validation tincan-r23)

Still needed:
- Run m02_ancs.py and m03_concurrent.py against a real iPhone (tincan-r23)
- Onboarding wizard wired to real BlueZ pairing + capability detection
  (`tincan_gui/onboarding.py` has the UI but no Bluetooth).
- `SendMessage` in the GUI wired to `MapBackend.send_message()` (GUI side still stub).
- HFP calls and PBAP contacts (later phases).
- Fill in `spikes/FINDINGS.md` OQ-3 and OQ-4 after hardware run.
