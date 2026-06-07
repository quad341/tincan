# Tincan

![tincan](docs/assets/tincan-full.png)

A Linux desktop **phone companion** for the iPhone — like Microsoft Phone Link, but open and for Linux. Tincan talks to an iPhone over **standard Bluetooth profiles** (no jailbreak, no Apple-ID risk), so you can **send and receive SMS and group messages from your desktop**, mirror your phone's app notifications, and see real contact names — with calls on the roadmap.

It's structured as a headless **daemon + a thin GUI over a D-Bus bus**, so other clients — including a future AI "secretary" agent (a separate project) — can drive the same capabilities.

The name: a tin-can telephone — a humble, honest string between two endpoints.

🔗 **[tincanapp.uk](https://tincanapp.uk)**

## Status — working prototype

Messaging **sends and receives today**, live-tested against an iPhone over Bluetooth MAP:

- ✅ **SMS** — receive (with desktop notifications) and send from the GUI, delivered to the recipient's phone
- ✅ **Group MMS** — receive, send, and a dedicated group conversation view
- ✅ **App notification mirroring (ANCS)** — see notifications from phone apps on your desktop, with per-app filtering
- ✅ **Message history** — a local SQLite cache, so conversations persist across restarts
- ✅ **Contact names (PBAP)** — real names on conversations
- ✅ **Desktop UX** — conversation threads, dark mode, close-to-tray, clickable links, "Delivered ✓", color emoji on Wayland, one-click launch
- ✅ **Internationalization** — translatable UI (i18n pipeline)
- 🚧 In progress: contact **avatars & search**, conversation-dedup polish
- 🗺️ Planned: **phone calls** (HFP audio), **packaging & distribution**, an **MCP API** for agents — see the **[roadmap](https://github.com/quad341/tincan/issues?q=is%3Aissue+is%3Aopen+label%3Aroadmap)**

Reference setup: iPhone (iOS 26.x) ↔ Fedora 44, BlueZ 5.86, PipeWire, PySide6, Python 3.14.

## Installation

### Requirements

- **Linux** desktop with systemd (Fedora 40+, Ubuntu 24.04+, or equivalent)
- **BlueZ 5.72+** with `bluez-obexd` — available in most distributions
- **Python 3.10+** (3.12+ recommended)
- **PySide6** — `python3-pyside6` on Fedora / `pip install PySide6` elsewhere
- **python3-dbus** and **python3-gobject** (`python3-gi`) for D-Bus and ANCS
- **python3-vobject** for vCard parsing (PBAP contacts)
- An **iPhone** running iOS 14+ with Bluetooth on and already paired to the Linux host

> ⚠️ **BlueZ experimental features are required**
>
> Tincan uses ANCS (Apple Notification Center Service), which needs the
> `Experimental` flag in BlueZ.  Without it the daemon starts, but ANCS
> notifications will not arrive.
>
> Edit `/etc/bluetooth/main.conf`:
>
> ```ini
> [General]
> Experimental = true
> ```
>
> Then restart BlueZ:
>
> ```bash
> sudo systemctl restart bluetooth
> ```
>
> Verify it took effect:
>
> ```bash
> bluetoothctl show | grep -i experimental
> # Expected: ExperimentalFeatures: yes
> ```

### Install via COPR (Fedora / RHEL)

```bash
sudo dnf copr enable quad341/tincan
sudo dnf install tincan
```

All dependencies (`python3-pyside6`, `python3-dbus`, `python3-gobject`,
`python3-vobject`, `bluez-obexd`) are available in the official Fedora 42+
repositories — no third-party repos required beyond the COPR itself.

### Install from PyPI

```bash
pip install tincan
```

### Install from source

```bash
git clone https://github.com/quad341/tincan.git
cd tincan
pip install -e .
```

### Start the daemon

```bash
# Replace AA:BB:CC:DD:EE:FF with your iPhone's Bluetooth address
python -m tincand --device AA:BB:CC:DD:EE:FF
```

Find your iPhone's address in `bluetoothctl devices` or System Settings → Bluetooth.

### Start the GUI

```bash
python -m tincan_gui
```

The GUI connects to the running daemon over D-Bus automatically.

### Pair your iPhone

1. On the iPhone: **Settings → Bluetooth** — find your Linux hostname in the device list.
2. Tap it and accept the pairing PIN shown on both devices.
3. On first ANCS connect, iOS shows a **"Show Notifications"** consent prompt — accept it on the phone.
4. If the daemon was already running, restart it after pairing.

### Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Daemon exits "not connected" immediately | iPhone not paired or Bluetooth off | Pair via `bluetoothctl` first; check `hciconfig` |
| No app notifications | BlueZ experimental not enabled | Follow the `Experimental = true` steps above |
| No messages / contacts | obexd not running | `sudo systemctl start bluetooth-obexd` or check `obexd --nodetach` |
| GUI shows "daemon not found" | Daemon not started | Run `python -m tincand` in a terminal first |

## Architecture

A headless **bus** (daemon) with thin **clients**:

```
iPhone ──Bluetooth (MAP / ANCS / HFP / PBAP)──▶ BlueZ / obexd ──▶ tincand ──D-Bus──▶ tincan_gui
                                                                  im.tincan.Daemon    (+ future clients)
```

- **`tincand`** — headless daemon that owns the Bluetooth connection (OBEX **MAP** messaging, **ANCS** notifications, and **PBAP** contacts via BlueZ/obexd today; **HFP** calls as they land). Normalizes raw profile data into a clean domain model and exposes a D-Bus session service, `im.tincan.Daemon`.
- **`tincan_gui`** — a PySide6 (Qt) desktop app; a pure client of the daemon.

This repository is **purely the UI + bus**. The AI "secretary" agent that will consume it (Claude integration, call transcription, voice synthesis) lives in a separate project.

## Running it

Prereqs: a **paired** iPhone with Bluetooth on, BlueZ + obexd, the system `python3-gi` and `python3-dbus`, plus the pip deps below.

```bash
pip install -r requirements.txt          # PySide6, vobject

# 1. Start the daemon (use your iPhone's Bluetooth address)
PYTHONPATH=. python -m tincand --backend map --device AA:BB:CC:DD:EE:FF

# 2. Start the GUI
PYTHONPATH=. python -m tincan_gui
```

On first connect, iOS shows a **"Show Notifications"** consent prompt for the paired device — accept it on the phone, then reconnect (the MAP link requires it).

## Development

```bash
pytest          # run the test suite (headless — offscreen Qt)
ruff check .    # lint
```

## Documentation

- [docs/PLAN.md](docs/PLAN.md) — vision, design principles, architecture, phased roadmap
- [docs/PROTOCOLS.md](docs/PROTOCOLS.md) — the Bluetooth profiles (ANCS, MAP, HFP, PBAP) and how iOS behaves
- [docs/LIMITATIONS.md](docs/LIMITATIONS.md) — honest "what it can and can't do"
- [docs/TESTING.md](docs/TESTING.md) — testing approach

## Android?

Tincan's Bluetooth stack (MAP/ANCS/PBAP over BlueZ) works the same way in theory for an Android phone, but **Android is a non-goal for this project**. Android users should look at **[KDE Connect](https://community.kde.org/KDEConnect)** — a mature, well-supported Android ↔ Linux integration app available on Google Play and F-Droid.

## Why

Microsoft Phone Link already does calls + SMS + notifications + contacts over Bluetooth alone — on Windows. Nobody had assembled the same stack on Linux. That's the gap Tincan fills.

## Vibe-maintained

Tincan is a **vibe-maintained** project — the codebase is developed and maintained by autonomous AI coding agents working from a shared backlog. Human contributors set direction; agents implement, test, and ship.

Contributions are **very welcome**. You don't need to understand every line — open an issue or a PR and the agents will engage with it.

If you're curious about this development style, Steve Yegge's writing is a good primer:
- [Vibe Maintainer](https://steve-yegge.medium.com/vibe-maintainer-a2273a841040) — the piece this project takes its name from

## License

[MIT](LICENSE) © 2026 quad341.

Tincan depends on (does not bundle) **PySide6** and **PyGObject**, which are LGPL; they are used unmodified via dynamic import, so Tincan's own code stays MIT. `dbus-python` (MIT) and `vobject` (Apache-2.0) round out the runtime dependencies.
