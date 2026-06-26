"""HFP call audio automation (tincan-zmpml).

Encodes the manually-validated 2026-06-11 recipe:
  (1) verify modem is on the RTL8761B dongle adapter (not MT7925 built-in)
  (2) SELinux module check — handled at startup by hfp_capability.py
  (3) verify dongle USB autosuspend is disabled
  (4) set oFono CallVolume Speaker/Mic to max when call goes active
  (5) wire PipeWire SCO routing: bluez_input→sink, source→bluez_output; tear down on hangup
"""
from __future__ import annotations

import logging
import pathlib
import subprocess

_log = logging.getLogger(__name__)

# USB vendor:product for ASUS USB-BT500 (RTL8761B)
_DONGLE_USB_VENDOR = "0b05"
_DONGLE_USB_PRODUCT = "1bf6"

_CALL_VOLUME_MAX = 100
_OFONO_BUS = "org.ofono"
_IFACE_CALL_VOLUME = "org.ofono.CallVolume"


def verify_dongle_adapter(modem_path: str, adapter_hci: str = "") -> bool:
    """Return True if modem_path routes through the RTL8761B dongle.

    Checks by adapter index (e.g. ``hci1``) — not by MAC — since BlueZ HFP
    modem paths use the adapter index, not the adapter MAC address.

    Returns True without warning when ``adapter_hci`` is empty (verification
    skipped; caller has not configured a preferred adapter).
    """
    if not adapter_hci:
        _log.debug("call_audio: verify_dongle_adapter skipped — no adapter_hci configured")
        return True
    ok = f"/{adapter_hci}/" in str(modem_path)
    if ok:
        _log.info("call_audio: modem %s on expected adapter %s ✓", modem_path, adapter_hci)
    else:
        _log.warning(
            "call_audio: modem %s not on configured adapter %s — "
            "HFP SCO audio likely broken. Connect iPhone to the ASUS USB-BT500 (%s).",
            modem_path,
            adapter_hci,
            adapter_hci,
        )
    return ok


def verify_usb_autosuspend_off() -> bool:
    """Return True if the RTL8761B dongle has USB autosuspend disabled.

    USB autosuspend causes corrupted SCO packets mid-call; the udev rule
    52-tincan-usb-bt500-no-autosuspend.rules must be in effect.
    """
    usb_root = pathlib.Path("/sys/bus/usb/devices")
    if not usb_root.exists():
        _log.debug("call_audio: /sys/bus/usb/devices missing — skipping autosuspend check")
        return True
    for dev in usb_root.iterdir():
        try:
            vendor = (dev / "idVendor").read_text().strip()
            product = (dev / "idProduct").read_text().strip()
            if vendor != _DONGLE_USB_VENDOR or product != _DONGLE_USB_PRODUCT:
                continue
            control = dev / "power" / "control"
            if not control.exists():
                return True
            state = control.read_text().strip()
            if state != "on":
                _log.warning(
                    "call_audio: dongle USB power/control=%r (want 'on') — "
                    "check /etc/udev/rules.d/52-tincan-usb-bt500-no-autosuspend.rules",
                    state,
                )
                return False
            _log.info("call_audio: dongle USB autosuspend disabled (power/control=on) ✓")
            return True
        except OSError:
            continue
    _log.debug("call_audio: dongle %s:%s not found in /sys — skipping autosuspend check",
               _DONGLE_USB_VENDOR, _DONGLE_USB_PRODUCT)
    return True


def set_ofono_call_volume(system_bus: object, modem_path: str) -> None:
    """Set oFono CallVolume SpeakerVolume and MicrophoneVolume to max.

    Default is 50% (0x32); faint or silent audio results until maxed.
    """
    try:
        import dbus
        vol = dbus.Interface(
            system_bus.get_object(_OFONO_BUS, modem_path),
            _IFACE_CALL_VOLUME,
        )
        vol.SetProperty("SpeakerVolume", dbus.Byte(_CALL_VOLUME_MAX))
        vol.SetProperty("MicrophoneVolume", dbus.Byte(_CALL_VOLUME_MAX))
        _log.info("call_audio: oFono CallVolume Speaker/Mic → %d ✓", _CALL_VOLUME_MAX)
    except Exception as exc:
        _log.warning("call_audio: oFono CallVolume set failed (%s) — audio may be faint", exc)


# ---------------------------------------------------------------------------
# PipeWire SCO routing via pw-link
# ---------------------------------------------------------------------------

def _pw_list_outputs() -> list[str]:
    """Return available pw-link output port names (sources)."""
    try:
        r = subprocess.run(
            ["pw-link", "--list-outputs"],
            capture_output=True, text=True, timeout=5,
        )
        return [line.split()[0] for line in r.stdout.splitlines() if line.strip()]
    except Exception as exc:
        _log.debug("call_audio: pw-link --list-outputs failed: %s", exc)
        return []


def _pw_list_inputs() -> list[str]:
    """Return available pw-link input port names (sinks)."""
    try:
        r = subprocess.run(
            ["pw-link", "--list-inputs"],
            capture_output=True, text=True, timeout=5,
        )
        return [line.split()[0] for line in r.stdout.splitlines() if line.strip()]
    except Exception as exc:
        _log.debug("call_audio: pw-link --list-inputs failed: %s", exc)
        return []


def _pw_link(out_port: str, in_port: str) -> bool:
    """Create a pw-link connection. Return True on success."""
    try:
        r = subprocess.run(
            ["pw-link", out_port, in_port],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            _log.debug("call_audio: linked %s → %s", out_port, in_port)
            return True
        _log.warning(
            "call_audio: pw-link %s → %s failed (rc=%d): %s",
            out_port, in_port, r.returncode, r.stderr.strip(),
        )
        return False
    except Exception as exc:
        _log.warning("call_audio: pw-link error: %s", exc)
        return False


def _pw_unlink(out_port: str, in_port: str) -> None:
    """Disconnect a pw-link connection."""
    try:
        subprocess.run(
            ["pw-link", "-d", out_port, in_port],
            capture_output=True, text=True, timeout=5,
        )
        _log.debug("call_audio: unlinked %s → %s", out_port, in_port)
    except Exception as exc:
        _log.debug("call_audio: pw-link -d error: %s", exc)


def setup_sco_routing(device_mac_fragment: str) -> list[tuple[str, str]]:
    """Wire PipeWire SCO routing for device_mac_fragment.

    Creates two link groups:
      bluez_input (far-end audio from phone) → default sink (speakers)
      default source (microphone)            → bluez_output (audio to phone)

    Returns the list of (output_port, input_port) pairs successfully linked;
    pass this to teardown_sco_routing() when the call ends.

    If ports are not yet registered (PipeWire may take ~1s after call active),
    logs a warning and returns an empty list.
    """
    if not device_mac_fragment:
        _log.warning(
            "setup_sco_routing called with empty MAC address — "
            "skipping PipeWire port wiring"
        )
        return []
    mac = device_mac_fragment.lower().replace(":", "_")

    outputs = _pw_list_outputs()
    inputs = _pw_list_inputs()

    # Ports for phone→speaker path
    bluez_out_ports = [p for p in outputs if "bluez_input" in p.lower() and mac in p.lower()]
    sink_in_ports = [p for p in inputs if "playback" in p.lower() and "bluez" not in p.lower()]

    # Ports for mic→phone path
    src_out_ports = [p for p in outputs if "capture" in p.lower() and "bluez" not in p.lower()]
    bluez_in_ports = [p for p in inputs if "bluez_output" in p.lower() and mac in p.lower()]

    if not bluez_out_ports:
        _log.warning(
            "call_audio: no bluez_input ports found for MAC %s — SCO routing skipped "
            "(PipeWire may need more time; will retry if configured)",
            mac,
        )
        return []
    if not bluez_in_ports:
        _log.warning(
            "call_audio: no bluez_output ports found for MAC %s — SCO routing skipped", mac
        )
        return []
    if not sink_in_ports:
        _log.warning("call_audio: no default sink playback ports — SCO routing skipped")
        return []
    if not src_out_ports:
        _log.warning("call_audio: no default source capture ports — SCO routing skipped")
        return []

    links: list[tuple[str, str]] = []

    # bluez_input ports expose capture_FL/FR/MONO; default sink uses playback_FL/FR/MONO
    for out in bluez_out_ports:
        channel = out.rsplit(":", 1)[-1].replace("capture_", "playback_")
        target = next((p for p in sink_in_ports if p.endswith(channel)), sink_in_ports[0])
        if _pw_link(out, target):
            links.append((out, target))

    # bluez_output ports expose playback_FL/FR/MONO; default source uses capture_FL/FR/MONO
    for inp in bluez_in_ports:
        channel = inp.rsplit(":", 1)[-1].replace("playback_", "capture_")
        source = next((p for p in src_out_ports if p.endswith(channel)), src_out_ports[0])
        if _pw_link(source, inp):
            links.append((source, inp))

    _log.info("call_audio: SCO routing established (%d links)", len(links))
    return links


def teardown_sco_routing(links: list[tuple[str, str]]) -> None:
    """Disconnect PipeWire links previously created by setup_sco_routing."""
    for out_port, in_port in links:
        _pw_unlink(out_port, in_port)
    if links:
        _log.info("call_audio: SCO routing torn down (%d links)", len(links))
