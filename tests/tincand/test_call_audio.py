"""Tests: tincand/call_audio.py — verify_dongle_adapter, verify_usb_autosuspend_off.
Bead: tincan-3by2j (corrected: tincan-ggh48)

Coverage:
  verify_dongle_adapter:
  - Returns True when adapter_hci matches a path component in modem_path.
  - Returns False when adapter_hci does not match any path component.
  - Returns True (graceful skip) when adapter_hci is empty.
  - No WARNING logged when adapter_hci matches.
  - WARNING logged when adapter_hci is set but path does not contain it.

  verify_usb_autosuspend_off:
  - Returns True when /sys/bus/usb/devices does not exist (sysfs absent — no block).
  - Returns True when matching vendor:product device is not found (dongle absent — no block).
  - Returns True when matching device has power/control='on' (autosuspend disabled).
  - Returns False when matching device has power/control='auto' (autosuspend active).
  - WARNING logged when power/control != 'on'.
  - Returns True when matching device has no power/control file (treated as no block).
  - Non-matching devices do not trigger False even when their control='auto'.
  - Unreadable device directories (OSError) are skipped without crashing.

pathlib.Path is patched at the module level; real sysfs never touched.
"""
from __future__ import annotations

import logging
import pathlib
import subprocess

import pytest

from tincand import call_audio
from tincand.call_audio import (
    _DONGLE_USB_PRODUCT,
    _DONGLE_USB_VENDOR,
    _pw_current_links,
    setup_sco_routing,
    verify_aec_in_path,
    verify_dongle_adapter,
    verify_usb_autosuspend_off,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_device(
    parent: pathlib.Path,
    name: str,
    vendor: str,
    product: str,
    control: str | None = "on",
) -> pathlib.Path:
    """Create a minimal fake sysfs USB device directory under *parent*."""
    dev = parent / name
    dev.mkdir()
    (dev / "idVendor").write_text(vendor + "\n")
    (dev / "idProduct").write_text(product + "\n")
    if control is not None:
        (dev / "power").mkdir()
        (dev / "power" / "control").write_text(control + "\n")
    return dev


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_usb_root(tmp_path, monkeypatch):
    """Redirect pathlib.Path('/sys/bus/usb/devices') to an existing tmp dir."""
    usb_root = tmp_path / "usb_devices"
    usb_root.mkdir()
    _orig = pathlib.Path

    def _factory(*args, **kwargs):
        if args and str(args[0]) == "/sys/bus/usb/devices":
            return usb_root
        return _orig(*args, **kwargs)

    monkeypatch.setattr("tincand.call_audio.pathlib.Path", _factory)
    return usb_root


@pytest.fixture
def missing_usb_root(tmp_path, monkeypatch):
    """Redirect pathlib.Path('/sys/bus/usb/devices') to a non-existent path."""
    missing = tmp_path / "no_usb_devices"
    _orig = pathlib.Path

    def _factory(*args, **kwargs):
        if args and str(args[0]) == "/sys/bus/usb/devices":
            return missing
        return _orig(*args, **kwargs)

    monkeypatch.setattr("tincand.call_audio.pathlib.Path", _factory)
    return missing


# ---------------------------------------------------------------------------
# §1 verify_dongle_adapter
# ---------------------------------------------------------------------------

class TestVerifyDongleAdapter:
    """verify_dongle_adapter — True iff /{adapter_hci}/ appears in modem_path."""

    def test_returns_true_when_adapter_hci_matches_path(self):
        path = "/hfp/org/bluez/hci1/dev_D0_6B_78_33_46_20"
        assert verify_dongle_adapter(path, "hci1") is True

    def test_returns_false_when_adapter_hci_not_in_path(self):
        path = "/hfp/org/bluez/hci0/dev_D0_6B_78_33_46_20"
        assert verify_dongle_adapter(path, "hci1") is False

    def test_returns_true_when_adapter_hci_empty(self):
        assert verify_dongle_adapter("/hfp/org/bluez/hci0/dev_D0_6B_78_33_46_20", "") is True

    def test_no_warning_when_adapter_hci_matches(self, caplog):
        with caplog.at_level(logging.WARNING, logger="tincand.call_audio"):
            verify_dongle_adapter("/hfp/org/bluez/hci1/dev_D0_6B_78_33_46_20", "hci1")
        assert not any(r.levelname == "WARNING" for r in caplog.records)

    def test_warning_logged_when_adapter_hci_not_in_path(self, caplog):
        with caplog.at_level(logging.WARNING, logger="tincand.call_audio"):
            verify_dongle_adapter("/hfp/org/bluez/hci0/dev_D0_6B_78_33_46_20", "hci1")
        assert any(r.levelname == "WARNING" for r in caplog.records)


# ---------------------------------------------------------------------------
# §2 verify_usb_autosuspend_off
# ---------------------------------------------------------------------------

class TestVerifyUsbAutosuspendOff:
    """verify_usb_autosuspend_off — checks RTL8761B USB power/control via sysfs."""

    def test_returns_true_when_usb_devices_absent(self, missing_usb_root):
        assert verify_usb_autosuspend_off() is True

    def test_returns_true_when_dongle_not_found(self, fake_usb_root):
        _make_device(fake_usb_root, "3-1", vendor="1d6b", product="0002", control="auto")
        assert verify_usb_autosuspend_off() is True

    def test_returns_true_when_control_is_on(self, fake_usb_root):
        _make_device(
            fake_usb_root, "3-2",
            vendor=_DONGLE_USB_VENDOR,
            product=_DONGLE_USB_PRODUCT,
            control="on",
        )
        assert verify_usb_autosuspend_off() is True

    def test_returns_false_when_control_is_auto(self, fake_usb_root):
        _make_device(
            fake_usb_root, "3-2",
            vendor=_DONGLE_USB_VENDOR,
            product=_DONGLE_USB_PRODUCT,
            control="auto",
        )
        assert verify_usb_autosuspend_off() is False

    def test_warning_logged_when_control_is_auto(self, fake_usb_root, caplog):
        _make_device(
            fake_usb_root, "3-2",
            vendor=_DONGLE_USB_VENDOR,
            product=_DONGLE_USB_PRODUCT,
            control="auto",
        )
        with caplog.at_level(logging.WARNING, logger="tincand.call_audio"):
            verify_usb_autosuspend_off()
        assert any(r.levelname == "WARNING" for r in caplog.records)

    def test_returns_true_when_control_file_absent(self, fake_usb_root):
        _make_device(
            fake_usb_root, "3-2",
            vendor=_DONGLE_USB_VENDOR,
            product=_DONGLE_USB_PRODUCT,
            control=None,
        )
        assert verify_usb_autosuspend_off() is True

    def test_non_matching_device_auto_does_not_trigger_false(self, fake_usb_root):
        _make_device(fake_usb_root, "3-1", vendor="1d6b", product="0002", control="auto")
        assert verify_usb_autosuspend_off() is True

    def test_skips_unreadable_device_catches_oserror(self, fake_usb_root):
        (fake_usb_root / "3-broken").mkdir()
        _make_device(
            fake_usb_root, "3-2",
            vendor=_DONGLE_USB_VENDOR,
            product=_DONGLE_USB_PRODUCT,
            control="on",
        )
        assert verify_usb_autosuspend_off() is True


# ---------------------------------------------------------------------------
# SCO routing + AEC verification (tincan-jukpc / tincan-97mlk.2)
# ---------------------------------------------------------------------------

_MAC = "D0:6B:78:33:46:20"
_MACF = "d0_6b_78_33_46_20"


class _FakePw:
    """Fake for call_audio._run_pw dispatching on the CLI args."""

    def __init__(
        self,
        outputs: str = "",
        inputs: str = "",
        links: str = "",
        default_sink: str = "",
        default_source: str = "",
        link_rc: int = 0,
        link_stderr: str = "",
    ) -> None:
        self.outputs = outputs
        self.inputs = inputs
        self.links = links
        self.default_sink = default_sink
        self.default_source = default_source
        self.link_rc = link_rc
        self.link_stderr = link_stderr
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> subprocess.CompletedProcess:
        self.calls.append(list(args))

        def _cp(rc: int = 0, out: str = "", err: str = "") -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(args=args, returncode=rc, stdout=out, stderr=err)

        if args[0] == "pactl":
            name = self.default_sink if args[1] == "get-default-sink" else self.default_source
            return _cp(out=name + "\n")
        if args == ["pw-link", "-o"]:
            return _cp(out=self.outputs)
        if args == ["pw-link", "-i"]:
            return _cp(out=self.inputs)
        if args == ["pw-link", "-l"]:
            return _cp(out=self.links)
        if args[0] == "pw-link" and args[1] == "-d":
            return _cp()
        # link creation: pw-link <out> <in>
        return _cp(rc=self.link_rc, err=self.link_stderr)

    def link_attempts(self) -> list[tuple[str, str]]:
        return [
            (c[1], c[2]) for c in self.calls
            if c[0] == "pw-link" and len(c) == 3 and not c[1].startswith("-")
        ]


_AEC_OUTPUTS = f"""bluez_input.{_MACF}:capture_MONO
iris_aec_src:capture_FL
iris_aec_src:capture_FR
alsa_input.usb-Mic:capture_MONO
iris_aec_sink:monitor_FL
"""

_AEC_INPUTS = f"""bluez_output.{_MACF}:playback_MONO
iris_aec_sink:playback_FL
iris_aec_sink:playback_FR
alsa_output.pci-0000:playback_FL
alsa_output.pci-0000:playback_FR
"""


class TestSetupScoRouting:
    def _routed(self, fake, monkeypatch):
        monkeypatch.setattr(call_audio, "_run_pw", fake)
        return setup_sco_routing(_MAC)

    def test_port_listing_uses_valid_pw_link_flags(self, monkeypatch):
        """Regression tincan-jukpc: --list-outputs/--list-inputs are not real flags."""
        fake = _FakePw(outputs=_AEC_OUTPUTS, inputs=_AEC_INPUTS,
                       default_sink="iris_aec_sink", default_source="iris_aec_src")
        self._routed(fake, monkeypatch)
        assert ["pw-link", "-o"] in fake.calls
        assert ["pw-link", "-i"] in fake.calls
        assert not any("--list-outputs" in c or "--list-inputs" in c for c in fake.calls)

    def test_routes_through_default_aec_devices(self, monkeypatch):
        """With an AEC pair as default devices, SCO must route through it."""
        fake = _FakePw(outputs=_AEC_OUTPUTS, inputs=_AEC_INPUTS,
                       default_sink="iris_aec_sink", default_source="iris_aec_src")
        links = self._routed(fake, monkeypatch)
        assert links
        downlink_targets = {inp for out, inp in links if out.startswith("bluez_input")}
        uplink_sources = {out for out, inp in links if inp.startswith("bluez_output")}
        assert all(t.startswith("iris_aec_sink:") for t in downlink_targets)
        assert all(s.startswith("iris_aec_src:") for s in uplink_sources)
        assert not any("alsa" in t for t in downlink_targets | uplink_sources)

    def test_no_default_devices_links_nothing(self, monkeypatch):
        """Without defaults there is no safe target — return [] so the controller retries."""
        fake = _FakePw(outputs=_AEC_OUTPUTS, inputs=_AEC_INPUTS)
        links = self._routed(fake, monkeypatch)
        assert links == []
        assert fake.link_attempts() == []

    def test_existing_link_counts_as_success(self, monkeypatch):
        """WirePlumber may have already made the link — 'File exists' is success."""
        fake = _FakePw(
            outputs=_AEC_OUTPUTS, inputs=_AEC_INPUTS,
            default_sink="iris_aec_sink", default_source="iris_aec_src",
            link_rc=1, link_stderr="failed to link ports: File exists",
        )
        links = self._routed(fake, monkeypatch)
        assert links

    def test_no_sco_ports_returns_empty_and_links_nothing(self, monkeypatch):
        fake = _FakePw(outputs="alsa_input.usb-Mic:capture_MONO\n",
                       inputs="alsa_output.pci-0000:playback_FL\n",
                       default_sink="alsa_output.pci-0000",
                       default_source="alsa_input.usb-Mic")
        links = self._routed(fake, monkeypatch)
        assert links == []
        assert fake.link_attempts() == []


class TestPwCurrentLinks:
    def test_parses_both_link_directions(self, monkeypatch):
        graph = (
            "alsa_output.pci-0000:playback_FL\n"
            "  |<- echo-cancel-playback:output_FL\n"
            f"bluez_input.{_MACF}:capture_MONO\n"
            "  |-> iris_aec_sink:playback_FL\n"
        )
        monkeypatch.setattr(call_audio, "_run_pw", _FakePw(links=graph))
        links = _pw_current_links()
        assert ("echo-cancel-playback:output_FL",
                "alsa_output.pci-0000:playback_FL") in links
        assert (f"bluez_input.{_MACF}:capture_MONO",
                "iris_aec_sink:playback_FL") in links


class TestVerifyAecInPath:
    def _verify(self, graph, monkeypatch):
        monkeypatch.setattr(call_audio, "_run_pw", _FakePw(links=graph))
        return verify_aec_in_path(_MAC)

    def test_ok_when_both_invariants_hold(self, monkeypatch):
        graph = (
            f"bluez_input.{_MACF}:capture_MONO\n"
            "  |-> iris_aec_sink:playback_FL\n"
            "iris_aec_src:capture_FL\n"
            f"  |-> bluez_output.{_MACF}:playback_MONO\n"
        )
        ok, detail = self._verify(graph, monkeypatch)
        assert ok, detail

    def test_tts_playback_into_uplink_is_allowed(self, monkeypatch):
        """An agent's TTS stream into the uplink is intended, not an echo path."""
        graph = (
            f"bluez_input.{_MACF}:capture_MONO\n"
            "  |-> iris_aec_sink:playback_FL\n"
            "iris_aec_src:capture_FL\n"
            f"  |-> bluez_output.{_MACF}:playback_MONO\n"
            "pw-cat:output_FL\n"
            f"  |-> bluez_output.{_MACF}:playback_MONO\n"
        )
        ok, detail = self._verify(graph, monkeypatch)
        assert ok, detail

    def test_raw_mic_on_uplink_fails(self, monkeypatch):
        graph = (
            f"bluez_input.{_MACF}:capture_MONO\n"
            "  |-> iris_aec_sink:playback_FL\n"
            "iris_aec_src:capture_FL\n"
            f"  |-> bluez_output.{_MACF}:playback_MONO\n"
            "alsa_input.usb-Mic:capture_MONO\n"
            f"  |-> bluez_output.{_MACF}:playback_MONO\n"
        )
        ok, detail = self._verify(graph, monkeypatch)
        assert not ok
        assert "raw microphone" in detail

    def test_downlink_not_in_reference_fails(self, monkeypatch):
        graph = (
            f"bluez_input.{_MACF}:capture_MONO\n"
            "  |-> alsa_output.pci-0000:playback_FL\n"
            "iris_aec_src:capture_FL\n"
            f"  |-> bluez_output.{_MACF}:playback_MONO\n"
        )
        ok, detail = self._verify(graph, monkeypatch)
        assert not ok
        assert "reference" in detail

    def test_speaker_bypass_alongside_reference_fails(self, monkeypatch):
        graph = (
            f"bluez_input.{_MACF}:capture_MONO\n"
            "  |-> iris_aec_sink:playback_FL\n"
            f"bluez_input.{_MACF}:capture_MONO\n"
            "  |-> alsa_output.pci-0000:playback_FL\n"
            "iris_aec_src:capture_FL\n"
            f"  |-> bluez_output.{_MACF}:playback_MONO\n"
        )
        ok, detail = self._verify(graph, monkeypatch)
        assert not ok
        assert "bypass" in detail

    def test_no_sco_nodes_fails(self, monkeypatch):
        graph = (
            "alsa_input.usb-Mic:capture_MONO\n"
            "  |-> echo-cancel-capture:input_MONO\n"
        )
        ok, detail = self._verify(graph, monkeypatch)
        assert not ok
        assert "absent" in detail

    def test_empty_graph_fails(self, monkeypatch):
        ok, detail = self._verify("", monkeypatch)
        assert not ok

    def test_module_echo_cancel_naming_also_recognized(self, monkeypatch):
        graph = (
            f"bluez_input.{_MACF}:capture_MONO\n"
            "  |-> echo-cancel-playback:playback_FL\n"
            "echo-cancel-capture:capture_FL\n"
            f"  |-> bluez_output.{_MACF}:playback_MONO\n"
        )
        ok, detail = self._verify(graph, monkeypatch)
        assert ok, detail
