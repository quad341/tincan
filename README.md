# Tincan

![tincan](docs/assets/tincan-full.png)

A Linux desktop **phone companion** for the iPhone — like Microsoft Phone Link, but open and for Linux. Tincan talks to an iPhone over **standard Bluetooth profiles** (no jailbreak, no Apple-ID risk), so you can **send and receive SMS from your desktop**, with notifications, calls, and contacts on the roadmap.

It's structured as a headless **daemon + a thin GUI over a D-Bus bus**, so other clients — including a future AI "secretary" agent (a separate project) — can drive the same capabilities.

The name: a tin-can telephone — a humble, honest string between two endpoints.

🔗 **[tincanapp.uk](https://tincanapp.uk)**

## Status — working prototype

SMS **send and receive work today**, live-tested against an iPhone over Bluetooth MAP:

- ✅ Receive incoming SMS, with desktop notifications
- ✅ Send SMS from the GUI — delivered to the recipient's phone
- ✅ Conversation threads, dark mode, close-to-tray, clickable links
- 🚧 In progress: contact names & avatars (PBAP), conversation dedup, outbound-bubble polish
- 🗺️ Planned: full notification mirroring, calls, an MCP API — see the **[roadmap](https://github.com/quad341/tincan/issues?q=is%3Aissue+label%3Aroadmap)**

Reference setup: iPhone (iOS 26.x) ↔ Fedora 44, BlueZ 5.86, PipeWire, PySide6, Python 3.14.

## Architecture

A headless **bus** (daemon) with thin **clients**:

```
iPhone ──Bluetooth (MAP / ANCS / HFP / PBAP)──▶ BlueZ / obexd ──▶ tincand ──D-Bus──▶ tincan_gui
                                                                  im.tincan.Daemon    (+ future clients)
```

- **`tincand`** — headless daemon that owns the Bluetooth connection (OBEX **MAP** via BlueZ/obexd today; ANCS / HFP / PBAP as features land). Normalizes raw profile data into a clean domain model and exposes a D-Bus session service, `im.tincan.Daemon`.
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

## Why

Microsoft Phone Link already does calls + SMS + notifications + contacts over Bluetooth alone — on Windows. Nobody had assembled the same stack on Linux. That's the gap Tincan fills.

## License

[MIT](LICENSE) © 2026 quad341.

Tincan depends on (does not bundle) **PySide6** and **PyGObject**, which are LGPL; they are used unmodified via dynamic import, so Tincan's own code stays MIT. `dbus-python` (MIT) and `vobject` (Apache-2.0) round out the runtime dependencies.
