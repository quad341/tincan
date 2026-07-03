"""Tests: tincand/call_audio.py — setup_sco_routing (SCO ↔ default devices).

Regression guard for the flag bug: setup_sco_routing must discover ports with
``pw-link -o`` / ``pw-link -i`` (the real flags). The long forms
``--list-outputs`` / ``--list-inputs`` are NOT valid pw-link options — pw-link
prints usage to stderr and returns an empty list, which silently disabled all
SCO routing (every call logged "no bluez_input ports — SCO routing skipped").

All subprocess calls are mocked — no real PipeWire or pactl required.
"""
from __future__ import annotations

import subprocess

import pytest

from tincand.call_audio import setup_sco_routing

_MAC = "d0_6b_78_33_46_20"

# Under the ambient-AEC setup the default sink/source are iris_aec_sink/src.
_OUTPUTS = "\n".join([
    "iris_aec_src:capture_FL",
    "iris_aec_src:capture_FR",
    "alsa_input.usb-mic:capture_MONO",          # raw mic (must NOT be chosen)
    f"bluez_input.{_MAC}.0:capture_FL",          # far-party downlink
    f"bluez_input.{_MAC}.0:capture_FR",
])
_INPUTS = "\n".join([
    "iris_aec_sink:playback_FL",
    "iris_aec_sink:playback_FR",
    "alsa_output.pci.analog-stereo:playback_FL",  # raw speakers (must NOT be chosen)
    f"bluez_output.{_MAC}.1:playback_FL",         # uplink to phone
    f"bluez_output.{_MAC}.1:playback_FR",
])


def _cp(stdout="", returncode=0):
    r = subprocess.CompletedProcess(args=[], returncode=returncode)
    r.stdout = stdout
    r.stderr = ""
    return r


def _install(monkeypatch, run):
    import tincand.call_audio as ca
    monkeypatch.setattr(ca, "subprocess", type("FakeSubproc", (), {
        "run": staticmethod(run),
        "CompletedProcess": subprocess.CompletedProcess,
    })())


@pytest.fixture
def recorder(monkeypatch):
    """Records argv; defaults resolve to iris_aec_sink / iris_aec_src."""
    calls: list[list[str]] = []

    def _run(cmd, **kw):
        calls.append(cmd)
        if cmd[:2] == ["pw-link", "-o"]:
            return _cp(_OUTPUTS)
        if cmd[:2] == ["pw-link", "-i"]:
            return _cp(_INPUTS)
        if cmd[:2] == ["pactl", "get-default-sink"]:
            return _cp("iris_aec_sink\n")
        if cmd[:2] == ["pactl", "get-default-source"]:
            return _cp("iris_aec_src\n")
        # model real pw-link rejecting the invalid long flags: empty stdout
        if cmd[0] == "pw-link" and ("--list-outputs" in cmd or "--list-inputs" in cmd):
            return _cp("")
        return _cp(returncode=0)  # link/unlink and anything else

    _install(monkeypatch, _run)
    return calls


def test_uses_real_pwlink_flags_not_long_forms(recorder):
    """Discovery uses `pw-link -o` / `-i`; the invalid --list-* forms never appear."""
    setup_sco_routing(_MAC)
    assert ["pw-link", "-o"] in recorder
    assert ["pw-link", "-i"] in recorder
    assert not any("--list-outputs" in c or "--list-inputs" in c for c in recorder)


def test_routes_far_party_to_default_sink_and_default_source_to_uplink(recorder):
    """Far party → default sink; the default (cleaned) source → uplink — not raw devices."""
    links = setup_sco_routing(_MAC)
    link_cmds = [c for c in recorder if c[0] == "pw-link" and len(c) == 3 and c[1] != "-d"]
    pairs = {(c[1], c[2]) for c in link_cmds}

    # downlink far party → the default sink (iris_aec_sink), per-channel
    assert (f"bluez_input.{_MAC}.0:capture_FL", "iris_aec_sink:playback_FL") in pairs
    assert (f"bluez_input.{_MAC}.0:capture_FR", "iris_aec_sink:playback_FR") in pairs
    # uplink cleaned mic (default source) → the phone
    assert ("iris_aec_src:capture_FL", f"bluez_output.{_MAC}.1:playback_FL") in pairs
    # never route through the raw analog devices
    assert not any("alsa_output" in inp for _, inp in pairs)
    assert not any("alsa_input" in out for out, _ in pairs)
    # the returned link list matches exactly what was wired
    assert links and set(links) == pairs


def test_returns_empty_when_sco_nodes_absent(monkeypatch):
    """SCO nodes lag call-active: no bluez ports yet → [] so the controller retries."""
    def _run(cmd, **kw):
        if cmd[:2] == ["pw-link", "-o"]:
            return _cp("iris_aec_src:capture_FL")       # no bluez_input
        if cmd[:2] == ["pw-link", "-i"]:
            return _cp("iris_aec_sink:playback_FL")      # no bluez_output
        if cmd[:2] == ["pactl", "get-default-sink"]:
            return _cp("iris_aec_sink\n")
        if cmd[:2] == ["pactl", "get-default-source"]:
            return _cp("iris_aec_src\n")
        return _cp(returncode=0)

    _install(monkeypatch, _run)
    assert setup_sco_routing(_MAC) == []


def test_empty_mac_is_a_noop(recorder):
    """Empty MAC → no wiring, no pw-link calls."""
    assert setup_sco_routing("") == []
    assert not any(c[0] == "pw-link" for c in recorder)
