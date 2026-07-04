# Tincan

![tincan](docs/assets/tincan-full.png)

A Linux desktop **phone companion** for the iPhone — like Microsoft Phone Link, but open and for Linux. Tincan talks to an iPhone over **standard Bluetooth profiles** (no jailbreak, no Apple-ID risk), so you can **send and receive SMS and group messages from your desktop**, mirror your phone's app notifications, and see real contact names — with calls on the roadmap.

It's structured as a headless **daemon + a thin GUI over a D-Bus bus**, so other clients — including a future AI "secretary" agent (a separate project) — can drive the same capabilities.

The name: a tin-can telephone — a humble, honest string between two endpoints.

🔗 **[tincanapp.uk](https://tincanapp.uk)**

## Status — working prototype

Messaging **sends and receives today**, live-tested against an iPhone over Bluetooth MAP:

- ✅ **SMS** — receive (with desktop notifications) and send from the GUI, delivered to the recipient's phone
- ⚠️ **Group texts aren't supported** — iOS can't send to a group over MAP (it delivers to only the first recipient) and offers no way to reply; incoming group messages appear as individual 1:1 threads. See [LIMITATIONS](docs/LIMITATIONS.md).
- ✅ **App notification mirroring (ANCS)** — see notifications from phone apps on your desktop, with per-app filtering
- ✅ **Message history** — conversations persist across restarts (today via a GUI-side cache; daemon-owned history as the single source of truth is on the roadmap)
- ✅ **Contact names (PBAP)** — real names on conversations
- ✅ **Desktop UX** — conversation threads, dark mode, close-to-tray, clickable links, "Delivered ✓", color emoji on Wayland, one-click launch
- ✅ **Internationalization** — translatable UI (i18n pipeline)
- ✅ **Phone calls (HFP)** — dial, answer, hang up, DTMF, with SCO audio via oFono + PipeWire (reference dongle required — see [COMPATIBILITY.md](COMPATIBILITY.md))
- 🚧 In progress: **reliability baseline** — ANCS auto re-arm after reconnect, HFP bring-up without manual oFono poking, gated echo cancellation (AEC) on every call
- 🗺️ Planned: **first-run onboarding**, daemon-owned message history, **packaging & distribution** — see the **[roadmap](https://github.com/quad341/tincan/issues?q=is%3Aissue+is%3Aopen+label%3Aroadmap)**

Reference setup: iPhone (iOS 26.x) ↔ Fedora 44, BlueZ 5.86, PipeWire, PySide6, Python 3.14.

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

> **ANCS notifications require a fixed BlueZ.** `bluez ≤ 5.86` has a bug — the MGMT *Add Extended Advertising Data* command is built with the wrong struct size, so it's 8 bytes too long — that breaks **all** LE advertising on kernels which validate that command's length (Linux ≈ 7.0+, a security hardening). The symptom is `RegisterAdvertisement failed … Invalid Parameters (0x0d)` and ANCS never starts (messaging/MAP/PBAP are unaffected). Fixed in BlueZ by [`2a6968b4`](https://github.com/bluez/bluez/commit/2a6968b40378dca5650e18e03ad0407738c47be5) (*advertising: Fix sending extra bytes with MGMT_OP_ADD_EXT_ADV_DATA*, 2026-06-02) — in master, **after 5.86** — so until your distro ships a release that includes it, apply the one-line patch. Full analysis + patch: [docs/ancs-bluez-ext-adv-rootcause.md](docs/ancs-bluez-ext-adv-rootcause.md).

### Phone calls (HFP) — in progress

Phone call audio requires oFono and a one-time WirePlumber backend switch.

**1. Install oFono** (Fedora 42+):
```bash
sudo dnf install ofono
sudo systemctl enable --now ofono
```

**2. Switch WirePlumber to the oFono HFP backend** (WirePlumber 0.5+):
```bash
mkdir -p ~/.config/wireplumber/wireplumber.conf.d/
cat > ~/.config/wireplumber/wireplumber.conf.d/50-hfp-ofono.conf << 'EOF'
monitor.bluez.properties = {
    bluez5.hfphsp-backend = "ofono"
}
EOF
systemctl --user restart wireplumber
```

> **Start order matters:** oFono must start (or be restarted) *after* WirePlumber
> is in oFono mode. If you see "UUID already registered" in `journalctl -u ofono`,
> run `sudo systemctl restart ofono` once.

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
