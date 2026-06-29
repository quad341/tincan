"""HFP call audio automation (tincan-zmpml).

Encodes the manually-validated 2026-06-11 recipe:
  (1) verify modem is on the RTL8761B dongle adapter (not MT7925 built-in)
  (2) SELinux module check — handled at startup by hfp_capability.py
  (3) verify dongle USB autosuspend is disabled
  (4) set oFono CallVolume Speaker/Mic to max when call goes active
  (5) wire PipeWire SCO routing: bluez_input→sink, source→bluez_output; tear down on hangup
  (6) uplink TTS mixer: null-sink mixing (mic + iris_tts) → bluez_output (tincan-rfb86)
"""
from __future__ import annotations

import logging
import pathlib
import subprocess
from dataclasses import dataclass, field

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


# ---------------------------------------------------------------------------
# Uplink TTS mixer (tincan-rfb86)
# ---------------------------------------------------------------------------
# Builds a PipeWire null-sink mixing graph:
#   (mic + iris_tts) → null-sink → bluez_output
# Barge-in: BargeInController gates TTS mute when operator mic is active.
# ---------------------------------------------------------------------------

_UPLINK_MIXER_SINK = "tincan_iris_uplink_mix"


@dataclass
class UplinkMixerCtx:
    """Live context for the uplink TTS mixer; pass to teardown_uplink_mixer()."""
    module_id: int
    mixer_sink_name: str
    mic_links: list[tuple[str, str]] = field(default_factory=list)
    tts_links: list[tuple[str, str]] = field(default_factory=list)
    out_links: list[tuple[str, str]] = field(default_factory=list)


def _pactl_load_null_sink(sink_name: str) -> int | None:
    """Load a PipeWire null-sink module. Return module ID, or None on failure."""
    try:
        r = subprocess.run(
            ["pactl", "load-module", "module-null-sink",
             f"sink_name={sink_name}",
             "media.class=Audio/Sink",
             "channel_map=mono"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            _log.warning(
                "call_audio: pactl load-module module-null-sink failed (rc=%d): %s",
                r.returncode, r.stderr.strip(),
            )
            return None
        module_id = int(r.stdout.strip())
        _log.info("call_audio: null-sink %r loaded as module %d", sink_name, module_id)
        return module_id
    except Exception as exc:
        _log.warning("call_audio: pactl load-module error: %s", exc)
        return None


def _pactl_unload_module(module_id: int) -> None:
    """Unload a PipeWire module by ID."""
    try:
        subprocess.run(
            ["pactl", "unload-module", str(module_id)],
            capture_output=True, text=True, timeout=5,
        )
        _log.debug("call_audio: unloaded module %d", module_id)
    except Exception as exc:
        _log.debug("call_audio: pactl unload-module error: %s", exc)


def setup_uplink_mixer(
    device_mac_fragment: str,
    tts_source_name: str | None = None,
) -> UplinkMixerCtx | None:
    """Create a PipeWire null-sink uplink mixer: (mic + optional_tts) → bluez_output.

    Returns None if required ports are not found or the null-sink cannot be created.
    """
    mac = device_mac_fragment.lower().replace(":", "_")
    sink_name = _UPLINK_MIXER_SINK

    module_id = _pactl_load_null_sink(sink_name)
    if module_id is None:
        return None

    outputs = _pw_list_outputs()
    inputs = _pw_list_inputs()

    mic_out_ports = [
        p for p in outputs
        if "capture" in p.lower()
        and "bluez" not in p.lower()
        and sink_name not in p
        and (tts_source_name is None or tts_source_name not in p)
    ]
    mixer_in_ports = [p for p in inputs if sink_name in p and "monitor" not in p]
    monitor_out_ports = [p for p in outputs if sink_name in p and "monitor" in p]
    bluez_in_ports = [p for p in inputs if "bluez_output" in p.lower() and mac in p.lower()]

    if not mic_out_ports:
        _log.warning("call_audio: uplink mixer: no mic capture ports found")
        _pactl_unload_module(module_id)
        return None
    if not mixer_in_ports:
        _log.warning(
            "call_audio: uplink mixer: no null-sink input ports for %r — unloading "
            "(PipeWire may need more time; will retry if configured)",
            sink_name,
        )
        _pactl_unload_module(module_id)
        return None
    if not bluez_in_ports:
        _log.warning("call_audio: uplink mixer: no bluez_output ports for MAC %s", mac)
        _pactl_unload_module(module_id)
        return None
    if not monitor_out_ports:
        _log.warning(
            "call_audio: uplink mixer: no null-sink monitor output ports found — unloading "
            "(PipeWire may need more time; will retry if configured)"
        )
        _pactl_unload_module(module_id)
        return None

    ctx = UplinkMixerCtx(module_id=module_id, mixer_sink_name=sink_name)

    for out in mic_out_ports:
        channel = out.rsplit(":", 1)[-1].replace("capture_", "playback_")
        target = next((p for p in mixer_in_ports if p.endswith(channel)), mixer_in_ports[0])
        if _pw_link(out, target):
            ctx.mic_links.append((out, target))

    for out in monitor_out_ports:
        channel = out.rsplit(":", 1)[-1].replace("capture_", "playback_")
        target = next((p for p in bluez_in_ports if p.endswith(channel)), bluez_in_ports[0])
        if _pw_link(out, target):
            ctx.out_links.append((out, target))

    if tts_source_name:
        connect_tts_to_uplink(ctx, tts_source_name)

    _log.info(
        "call_audio: uplink mixer ready — mic=%d tts=%d out=%d links",
        len(ctx.mic_links), len(ctx.tts_links), len(ctx.out_links),
    )
    return ctx


def connect_tts_to_uplink(mixer_ctx: UplinkMixerCtx, tts_source_name: str) -> bool:
    """Connect a TTS source port to the uplink null-sink. Returns True on success."""
    outputs = _pw_list_outputs()
    inputs = _pw_list_inputs()

    tts_out_ports = [p for p in outputs if tts_source_name in p]
    mixer_in_ports = [
        p for p in inputs
        if mixer_ctx.mixer_sink_name in p and "monitor" not in p
    ]

    if not tts_out_ports:
        _log.warning("call_audio: uplink mixer: no TTS output ports for %r", tts_source_name)
        return False
    if not mixer_in_ports:
        _log.warning(
            "call_audio: uplink mixer: no null-sink inputs for %r",
            mixer_ctx.mixer_sink_name,
        )
        return False

    created = False
    for out in tts_out_ports:
        channel = out.rsplit(":", 1)[-1].replace("capture_", "playback_")
        target = next((p for p in mixer_in_ports if p.endswith(channel)), mixer_in_ports[0])
        if _pw_link(out, target):
            mixer_ctx.tts_links.append((out, target))
            created = True

    return created


def teardown_uplink_mixer(mixer_ctx: UplinkMixerCtx) -> None:
    """Disconnect all links and unload the null-sink module."""
    all_links = mixer_ctx.mic_links + mixer_ctx.tts_links + mixer_ctx.out_links
    for out_port, in_port in all_links:
        _pw_unlink(out_port, in_port)
    _pactl_unload_module(mixer_ctx.module_id)
    _log.info(
        "call_audio: uplink mixer torn down (module %d, %d mic + %d tts + %d out links)",
        mixer_ctx.module_id,
        len(mixer_ctx.mic_links),
        len(mixer_ctx.tts_links),
        len(mixer_ctx.out_links),
    )


def apply_barge_in_frame(
    ctx: UplinkMixerCtx,
    controller: "BargeInController",
    mic_rms: float,
) -> bool:
    """Update VAD state and actuate TTS pw-links accordingly.

    On False→True transition (operator starts speaking): unlinks every port
    pair in ctx.tts_links so iris audio is removed from the uplink.
    On True→False transition (hangover expires): re-links ctx.tts_links so
    iris resumes.  Returns True while TTS is muted.
    """
    was_muted = controller.is_muted()
    now_muted = controller.update(mic_rms)

    if not was_muted and now_muted:
        for out_port, in_port in ctx.tts_links:
            _pw_unlink(out_port, in_port)
    elif was_muted and not now_muted:
        for out_port, in_port in ctx.tts_links:
            _pw_link(out_port, in_port)

    return now_muted


class BargeInController:
    """VAD-based barge-in: mutes TTS uplink while operator mic is active.

    Call update(mic_rms) each audio frame. Returns True while TTS should be
    muted (operator speaking or within the hangover window).
    """

    def __init__(self, threshold_rms: float = 500.0, hangover_frames: int = 10) -> None:
        self._threshold = threshold_rms
        self._hangover = hangover_frames
        self._silence_run = 0
        self._muted = False

    def update(self, mic_rms: float) -> bool:
        """Update with current mic RMS. Returns True if TTS should be muted."""
        if mic_rms >= self._threshold:
            self._silence_run = 0
            self._muted = True
        elif self._muted:
            self._silence_run += 1
            if self._silence_run >= self._hangover:
                self._muted = False
                self._silence_run = 0
        return self._muted

    def is_muted(self) -> bool:
        return self._muted
